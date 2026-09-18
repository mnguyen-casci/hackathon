#!/usr/bin/env python3
"""
Context-optimization benchmark harness.

Runs the same bug-fix task against the sample Java project seven ways:
  - naive:            every relevant file dumped verbatim into the prompt, no tools
  - rag-lite:         keyword-retrieval (realistic, non-leading query) picks
                      the top 5 relevant files, no tools
  - many-tools:       jit-loading's file tree, full default toolset described
                      (--tools default) but the heavier/behavior-changing
                      tools denied so it's forced into the same effective
                      5-tool behavior -- isolates tool-schema description
                      cost from behavioral change
  - jit-loading:      a bare file tree + Read/Glob/Grep/Edit/Write tools, agent
                      decides what to load
  - dependency-graph: an auto-generated call graph (textual class-name
                      reference scan, no real parser) as the system prompt + tools
  - context-file:     an auto-generated CLAUDE.md (Javadoc + public method
                      signatures pulled mechanically) as the system prompt + tools
  - compaction:       jit-loading's tools, with --autocompact forced to its
                      minimum (100k tokens) so mid-session compaction has a
                      chance to trigger on this task

All variants run concurrently (each uses its own isolated temp copy of the
project, so there's no shared state), then a separate blind judge call
(a different model than the one being tested, to reduce same-model bias)
scores each variant's diff on correctness/minimality/code quality.

Uses the Claude Code CLI binary in headless mode (`-p --output-format json`)
so no separate Anthropic API key is needed -- it runs against whatever
account is already authenticated in this Claude Code install.
"""

from __future__ import annotations

import concurrent.futures
import difflib
import glob
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_PROJECT = REPO_ROOT / "sample-project"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

FAILING_TEST_OUTPUT = (
    "org.opentest4j.AssertionFailedError: PLATINUM customers should get a "
    "10% loyalty discount, not 5% ==> expected: <50.49> but was: <52.99>"
)

TASK_RULES = (
    "`mvn test` currently fails with:\n"
    f"{FAILING_TEST_OUTPUT}\n\n"
    "(The other test in the same file, bulkOrderWithLowUnitPriceButHighQuantityGetsDiscount, "
    "already passes -- don't break it.)\n\n"
    "Find the bug causing this failure and fix it. Do not modify the test file "
    "(OrderProcessorTest.java)."
)

SOURCE_FILES = [
    "pom.xml",
    "README.md",
    "src/main/java/com/hackathon/orders/Main.java",
    "src/main/java/com/hackathon/orders/model/Order.java",
    "src/main/java/com/hackathon/orders/model/OrderItem.java",
    "src/main/java/com/hackathon/orders/model/Customer.java",
    "src/main/java/com/hackathon/orders/model/LoyaltyTier.java",
    "src/main/java/com/hackathon/orders/model/ShippingAddress.java",
    "src/main/java/com/hackathon/orders/service/DiscountService.java",
    "src/main/java/com/hackathon/orders/service/InventoryService.java",
    "src/main/java/com/hackathon/orders/service/CustomerService.java",
    "src/main/java/com/hackathon/orders/service/LoyaltyService.java",
    "src/main/java/com/hackathon/orders/service/ShippingService.java",
    "src/main/java/com/hackathon/orders/service/PaymentService.java",
    "src/main/java/com/hackathon/orders/service/OrderProcessor.java",
    "src/test/java/com/hackathon/orders/OrderProcessorTest.java",
]


def find_claude_binary() -> str:
    candidates = sorted(
        glob.glob(
            str(
                Path.home()
                / ".vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude"
            )
        )
    )
    if not candidates:
        sys.exit("Could not locate the bundled claude CLI binary.")
    return candidates[-1]


CLAUDE_BIN = find_claude_binary()


def make_temp_copy() -> Path:
    tmp_dir = Path(tempfile.mkdtemp(prefix="ctxbench_"))
    dest = tmp_dir / "sample-project"
    shutil.copytree(
        SAMPLE_PROJECT, dest, ignore=shutil.ignore_patterns("target", ".git")
    )
    return dest


def file_tree(project_dir: Path) -> str:
    paths = []
    for rel in SOURCE_FILES:
        if (project_dir / rel).exists():
            paths.append(rel)
    return "\n".join(sorted(paths))


def dump_files(project_dir: Path) -> str:
    parts = []
    for rel in SOURCE_FILES:
        path = project_dir / rel
        parts.append(f"--- {rel} ---\n{path.read_text()}")
    return "\n\n".join(parts)


def _java_files(project_dir: Path) -> list[Path]:
    return [project_dir / rel for rel in SOURCE_FILES if rel.endswith(".java")]


def _class_name(content: str) -> str | None:
    m = re.search(r"\b(?:class|enum|interface)\s+(\w+)", content)
    return m.group(1) if m else None


def generate_dependency_graph(project_dir: Path) -> str:
    """Auto-generated call graph: no real Java parser, just a textual scan
    for every other known class's name appearing as a whole word in each
    file. Catches same-package references that don't need an import
    statement, which a naive import-only scan would miss. Deliberately
    mechanical rather than hand-curated, to test realistic tooling output
    rather than a best-case hand-written summary."""
    classes: dict[str, str] = {}
    for path in _java_files(project_dir):
        name = _class_name(path.read_text())
        if name:
            classes[name] = path.read_text()

    lines = ["Call graph (auto-generated by scanning class-name references):", ""]
    for name in sorted(classes):
        content = classes[name]
        refs = sorted(
            other
            for other in classes
            if other != name and re.search(r"\b" + re.escape(other) + r"\b", content)
        )
        lines.append(f"{name} -> {', '.join(refs)}" if refs else f"{name} -> (no references to other project classes)")
    return "\n".join(lines)


def generate_claude_md(project_dir: Path) -> str:
    """Auto-generated context file: pulls each class's Javadoc summary (if
    any) and public method signatures. Reads more mechanically than a
    hand-written CLAUDE.md -- that's the point, this tests realistic
    tooling output, not a curated best case."""
    lines = ["# Auto-generated architecture summary", "", "## Module map", ""]
    for path in _java_files(project_dir):
        content = path.read_text()
        name = _class_name(content)
        if not name:
            continue
        rel = path.relative_to(project_dir)

        doc = ""
        doc_match = re.search(
            r"/\*\*(.*?)\*/\s*(?:public\s+)?(?:final\s+)?(?:class|enum|interface)\s+" + re.escape(name),
            content,
            re.DOTALL,
        )
        if doc_match:
            doc = " ".join(
                line.strip(" *") for line in doc_match.group(1).splitlines() if line.strip(" *")
            )

        methods = sorted(set(re.findall(r"public\s+[\w<>\[\],\s]+?\s(\w+)\s*\([^)]*\)\s*\{", content)))
        methods = [m for m in methods if m != name]
        method_note = f" Public methods: {', '.join(methods)}." if methods else ""

        entry = f"- `{rel}` -- class `{name}`."
        if doc:
            entry += f" {doc}"
        entry += method_note
        lines.append(entry)

    lines += [
        "",
        "## Verifying changes",
        "",
        "```",
        "mvn test",
        "```",
    ]
    return "\n".join(lines)


RAG_QUERY = (
    "A few customers said their order total looked wrong at checkout -- "
    "seemed like they weren't getting the extra savings they expected as "
    "long-time repeat customers, even though the order itself looked normal."
)


def retrieve_relevant_files(project_dir: Path, query: str, top_k: int = 5) -> list[str]:
    """Keyword-overlap retrieval: no embeddings, just shared-token count
    between the query (the failing test's name + assertion message) and
    each file's content. Deliberately simple -- this is the "lite" in
    RAG-lite."""

    def tokenize(text: str) -> set[str]:
        return set(re.findall(r"[a-zA-Z][a-zA-Z0-9]{2,}", text.lower()))

    query_terms = tokenize(query)
    scored = []
    for rel in SOURCE_FILES:
        path = project_dir / rel
        if not path.exists():
            continue
        score = len(query_terms & tokenize(path.read_text()))
        scored.append((score, rel))
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [rel for _, rel in scored[:top_k]]


def run_claude(
    prompt: str,
    cwd: Path,
    system_prompt: str,
    tools: str,
    extra_args: list[str] | None = None,
    model: str = "sonnet",
):
    cmd = [
        CLAUDE_BIN,
        "-p",
        prompt,
        "--output-format",
        "json",
        "--system-prompt",
        system_prompt,
        "--model",
        model,
        "--tools",
        tools,
        "--permission-mode",
        "acceptEdits",
    ]
    if extra_args:
        cmd += extra_args

    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=600
    )
    if result.returncode != 0:
        print("STDERR:", result.stderr[-4000:], file=sys.stderr)
        raise RuntimeError(f"claude CLI exited {result.returncode}")
    return json.loads(result.stdout)


def apply_naive_fix(project_dir: Path, response_text: str) -> str | None:
    match = re.search(
        r"FILE:\s*(\S+)\s*```(?:java)?\n(.*?)```", response_text, re.DOTALL
    )
    if not match:
        return None
    rel_path, content = match.group(1).strip(), match.group(2)
    target = project_dir / rel_path
    if not target.exists():
        return None
    target.write_text(content)
    return rel_path


def compute_diff(original_dir: Path, modified_dir: Path) -> str:
    diffs = []
    for rel in SOURCE_FILES:
        orig_path, mod_path = original_dir / rel, modified_dir / rel
        if not orig_path.exists() or not mod_path.exists():
            continue
        orig_lines = orig_path.read_text().splitlines(keepends=True)
        mod_lines = mod_path.read_text().splitlines(keepends=True)
        if orig_lines != mod_lines:
            diffs.append(
                "".join(difflib.unified_diff(orig_lines, mod_lines, fromfile=rel, tofile=rel))
            )
    return "\n".join(diffs) if diffs else "(no changes detected)"


JUDGE_SYSTEM_PROMPT = (
    "You are an impartial code reviewer scoring a bug fix. You do not know "
    "which method or tool produced it, judge only the diff itself. Score it "
    "1-10 on: (a) correctness -- does it fix the root cause rather than "
    "patch a symptom, (b) minimality -- does it change only what's "
    "necessary, (c) code quality -- readable, consistent with the "
    "surrounding style. Respond with ONLY:\n"
    "SCORE: <integer 1-10>\n"
    "RATIONALE: <one sentence>"
)


def judge_fix(diff_text: str) -> dict:
    """Scored with a different model than the one being tested (opus, not
    sonnet), so the judge isn't the same model family marking its own
    homework -- reduces, doesn't eliminate, same-model self-consistency
    bias in the scores."""
    prompt = f"Here is a unified diff of a bug fix:\n\n{diff_text}\n\nScore it."
    cli_json = run_claude(
        prompt, cwd=REPO_ROOT, system_prompt=JUDGE_SYSTEM_PROMPT, tools="", model="opus"
    )
    result_text = cli_json.get("result", "")
    score_match = re.search(r"SCORE:\s*(\d+)", result_text)
    rationale_match = re.search(r"RATIONALE:\s*(.+)", result_text, re.DOTALL)
    return {
        "quality_score": int(score_match.group(1)) if score_match else None,
        "quality_rationale": (
            rationale_match.group(1).strip() if rationale_match else result_text.strip()
        ),
    }


def run_mvn_test(project_dir: Path) -> bool:
    result = subprocess.run(
        ["mvn", "-q", "test"], cwd=project_dir, capture_output=True, text=True, timeout=180
    )
    return result.returncode == 0


def summarize_usage(cli_json: dict) -> dict:
    usage = cli_json.get("usage", {})
    return {
        "input_tokens": usage.get("input_tokens", 0),
        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
        "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "total_cost_usd": cli_json.get("total_cost_usd", 0),
        "num_turns": cli_json.get("num_turns", 0),
    }


def run_naive() -> dict:
    project_dir = make_temp_copy()
    prompt = (
        "You are working on a small Java Maven project. Here are all of its "
        f"source files.\n\n{dump_files(project_dir)}\n\n{TASK_RULES}\n\n"
        "Respond with ONLY the following, no other text:\n"
        "FILE: <path to the file you changed, relative to the project root>\n"
        "```java\n<the complete corrected contents of that file>\n```"
    )
    cli_json = run_claude(
        prompt,
        cwd=project_dir,
        system_prompt="You are a precise software engineer. Follow the output format exactly.",
        tools="",
    )
    fixed_file = apply_naive_fix(project_dir, cli_json.get("result", ""))
    passed = run_mvn_test(project_dir) if fixed_file else False
    diff_text = compute_diff(SAMPLE_PROJECT, project_dir)
    shutil.rmtree(project_dir.parent, ignore_errors=True)
    return {
        "variant": "naive",
        "fixed_file": fixed_file,
        "test_passed": passed,
        "diff": diff_text,
        **summarize_usage(cli_json),
    }


def run_rag_lite() -> dict:
    project_dir = make_temp_copy()
    retrieved = retrieve_relevant_files(project_dir, RAG_QUERY, top_k=5)
    dumped = "\n\n".join(
        f"--- {rel} ---\n{(project_dir / rel).read_text()}" for rel in retrieved
    )
    prompt = (
        "You are working on a small Java Maven project. A retrieval step "
        f"selected the {len(retrieved)} files judged most relevant to the "
        f"failing test below, out of {len(SOURCE_FILES)} files in the project; "
        f"only those are shown here.\n\n{dumped}\n\n{TASK_RULES}\n\n"
        "Respond with ONLY the following, no other text:\n"
        "FILE: <path to the file you changed, relative to the project root>\n"
        "```java\n<the complete corrected contents of that file>\n```"
    )
    cli_json = run_claude(
        prompt,
        cwd=project_dir,
        system_prompt="You are a precise software engineer. Follow the output format exactly.",
        tools="",
    )
    fixed_file = apply_naive_fix(project_dir, cli_json.get("result", ""))
    passed = run_mvn_test(project_dir) if fixed_file else False
    diff_text = compute_diff(SAMPLE_PROJECT, project_dir)
    shutil.rmtree(project_dir.parent, ignore_errors=True)
    return {
        "variant": "rag-lite",
        "fixed_file": fixed_file,
        "retrieved_files": retrieved,
        "test_passed": passed,
        "diff": diff_text,
        **summarize_usage(cli_json),
    }


def run_jit_loading() -> dict:
    project_dir = make_temp_copy()
    prompt = (
        "You are working on a Java Maven project. Here is its file tree "
        f"(relative to the current directory):\n\n{file_tree(project_dir)}\n\n"
        f"{TASK_RULES} Use the available tools to read whatever files you need "
        "before editing."
    )
    cli_json = run_claude(
        prompt,
        cwd=project_dir,
        system_prompt="You are a careful software engineer. Make the minimal correct fix.",
        tools="Read,Glob,Grep,Edit,Write",
    )
    passed = run_mvn_test(project_dir)
    diff_text = compute_diff(SAMPLE_PROJECT, project_dir)
    shutil.rmtree(project_dir.parent, ignore_errors=True)
    return {
        "variant": "jit-loading",
        "fixed_file": None,
        "test_passed": passed,
        "diff": diff_text,
        **summarize_usage(cli_json),
    }


def run_compaction() -> dict:
    """Same task/tools as jit-loading, but with a forced low auto-compact
    window (100k tokens, the CLI's minimum) so mid-session compaction
    actually has a chance to trigger on this task, rather than relying on
    the default 1M-token window that this small a task would never reach."""
    project_dir = make_temp_copy()
    prompt = (
        "You are working on a Java Maven project. Here is its file tree "
        f"(relative to the current directory):\n\n{file_tree(project_dir)}\n\n"
        f"{TASK_RULES} Use the available tools to read whatever files you need "
        "before editing."
    )
    cli_json = run_claude(
        prompt,
        cwd=project_dir,
        system_prompt="You are a careful software engineer. Make the minimal correct fix.",
        tools="Read,Glob,Grep,Edit,Write",
        extra_args=["--autocompact", "100000"],
    )
    passed = run_mvn_test(project_dir)
    diff_text = compute_diff(SAMPLE_PROJECT, project_dir)
    shutil.rmtree(project_dir.parent, ignore_errors=True)
    return {
        "variant": "compaction",
        "fixed_file": None,
        "test_passed": passed,
        "diff": diff_text,
        **summarize_usage(cli_json),
    }


def run_many_tools() -> dict:
    """Counter-example for tool-schema lazy loading: identical to
    jit-loading (same file tree, same system prompt, same task) except the
    full default toolset is described (--tools default) instead of just the
    5 tools actually needed. To isolate the cost of describing every tool's
    schema from the cost of the agent actually behaving differently with
    more capabilities available, the heavier/behavior-changing tools are
    denied via --disallowedTools, forcing the same effective 5-tool
    behavior as jit-loading while still paying the full schema-description
    cost. Not a perfectly airtight isolation (the deny list may not cover
    every default tool), but a much cleaner one than tools=default alone."""
    project_dir = make_temp_copy()
    prompt = (
        "You are working on a Java Maven project. Here is its file tree "
        f"(relative to the current directory):\n\n{file_tree(project_dir)}\n\n"
        f"{TASK_RULES} Use the available tools to read whatever files you need "
        "before editing."
    )
    cli_json = run_claude(
        prompt,
        cwd=project_dir,
        system_prompt="You are a careful software engineer. Make the minimal correct fix.",
        tools="default",
        extra_args=[
            "--disallowedTools",
            "Bash,WebFetch,WebSearch,Task,NotebookEdit,TodoWrite,ExitPlanMode,SlashCommand,BashOutput,KillBash",
        ],
    )
    passed = run_mvn_test(project_dir)
    diff_text = compute_diff(SAMPLE_PROJECT, project_dir)
    shutil.rmtree(project_dir.parent, ignore_errors=True)
    return {
        "variant": "many-tools",
        "fixed_file": None,
        "test_passed": passed,
        "diff": diff_text,
        **summarize_usage(cli_json),
    }


def run_dependency_graph() -> dict:
    project_dir = make_temp_copy()
    prompt = (
        "You are working on a Java Maven project. Here is its file tree "
        f"(relative to the current directory):\n\n{file_tree(project_dir)}\n\n"
        f"{TASK_RULES} Use the available tools to read whatever files you need "
        "before editing."
    )
    cli_json = run_claude(
        prompt,
        cwd=project_dir,
        system_prompt=generate_dependency_graph(project_dir),
        tools="Read,Glob,Grep,Edit,Write",
    )
    passed = run_mvn_test(project_dir)
    diff_text = compute_diff(SAMPLE_PROJECT, project_dir)
    shutil.rmtree(project_dir.parent, ignore_errors=True)
    return {
        "variant": "dependency-graph",
        "fixed_file": None,
        "test_passed": passed,
        "diff": diff_text,
        **summarize_usage(cli_json),
    }


def run_context_file() -> dict:
    project_dir = make_temp_copy()
    claude_md = generate_claude_md(project_dir)
    prompt = (
        "You are working on a Java Maven project. Here is its file tree "
        f"(relative to the current directory):\n\n{file_tree(project_dir)}\n\n"
        f"{TASK_RULES} Use the available tools to read whatever files you need "
        "before editing."
    )
    cli_json = run_claude(
        prompt,
        cwd=project_dir,
        system_prompt=claude_md,
        tools="Read,Glob,Grep,Edit,Write",
    )
    passed = run_mvn_test(project_dir)
    diff_text = compute_diff(SAMPLE_PROJECT, project_dir)
    shutil.rmtree(project_dir.parent, ignore_errors=True)
    return {
        "variant": "context-file",
        "fixed_file": None,
        "test_passed": passed,
        "diff": diff_text,
        **summarize_usage(cli_json),
    }


VARIANTS = [
    ("naive", run_naive),
    ("rag-lite", run_rag_lite),
    ("many-tools", run_many_tools),
    ("jit-loading", run_jit_loading),
    ("dependency-graph", run_dependency_graph),
    ("context-file", run_context_file),
    ("compaction", run_compaction),
]


def _timed(label: str, fn):
    print(f"Running variant: {label} ...")
    t0 = time.time()
    r = fn()
    r["wall_seconds"] = round(time.time() - t0, 1)
    print(f"  -> {label} done in {r['wall_seconds']}s")
    return r


def main():
    RESULTS_DIR.mkdir(exist_ok=True)

    # Each variant spins up its own isolated temp copy of sample-project and
    # makes an independent CLI call -- no shared mutable state -- so they're
    # safe to run concurrently. This is I/O-bound (subprocess calls), so
    # threads are enough; no need for multiprocessing.
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(VARIANTS)) as pool:
        futures = {pool.submit(_timed, label, fn): label for label, fn in VARIANTS}
        runs = [f.result() for f in concurrent.futures.as_completed(futures)]

    # Judge each fix blind, after the run itself finishes. Also independent
    # per-run, so also parallelized.
    print("\nScoring fixes with the quality judge ...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(runs)) as pool:
        judged = {pool.submit(judge_fix, r["diff"]): r for r in runs}
        for future in concurrent.futures.as_completed(judged):
            judged[future].update(future.result())

    order = {label: i for i, (label, _) in enumerate(VARIANTS)}
    runs.sort(key=lambda r: order[r["variant"]])

    out_path = RESULTS_DIR / f"run_{int(time.time())}.json"
    out_path.write_text(json.dumps(runs, indent=2))

    print("\n=== Summary ===")
    header = (
        f"{'variant':16} {'input_tok':>10} {'cache_create':>12} {'output_tok':>10} "
        f"{'cost_usd':>9} {'turns':>6} {'pass':>5} {'quality':>7}"
    )
    print(header)
    for r in runs:
        total_input = r["input_tokens"] + r["cache_creation_input_tokens"] + r["cache_read_input_tokens"]
        print(
            f"{r['variant']:16} {total_input:>10} {r['cache_creation_input_tokens']:>12} "
            f"{r['output_tokens']:>10} {r['total_cost_usd']:>9.4f} {r['num_turns']:>6} "
            f"{str(r['test_passed']):>5} {str(r['quality_score']):>7}"
        )
    print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    main()
