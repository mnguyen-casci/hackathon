#!/usr/bin/env python3
"""
Context-optimization benchmark harness.

Runs the same bug-fix task against the sample Java project three ways:
  - naive:        every relevant file dumped verbatim into the prompt, no tools
  - jit-loading:  a bare file tree + Read/Glob/Grep/Edit/Write tools, agent
                  decides what to load
  - context-file: same tools as jit-loading, plus a hand-built CLAUDE.md
                  as the system prompt instead of a generic one

Uses the Claude Code CLI binary in headless mode (`-p --output-format json`)
so no separate Anthropic API key is needed -- it runs against whatever
account is already authenticated in this Claude Code install.
"""

from __future__ import annotations

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


DEPENDENCY_GRAPH = """Call graph (who constructs / calls whom):

Main -> OrderProcessor, InventoryService, DiscountService, CustomerService, LoyaltyService, ShippingService
OrderProcessor -> InventoryService, DiscountService, CustomerService, LoyaltyService, ShippingService
DiscountService -> Order, OrderItem
InventoryService -> Order, OrderItem
CustomerService -> Customer, LoyaltyTier
LoyaltyService -> Customer, LoyaltyTier
ShippingService -> Order, ShippingAddress
Order -> OrderItem, ShippingAddress
PaymentService -> (standalone; not called by OrderProcessor or anything else)

OrderProcessor.processOrder pipeline order: inventory check -> bulk discount
(DiscountService) -> loyalty discount (CustomerService + LoyaltyService) ->
shipping cost (ShippingService).
"""

RAG_QUERY = (
    "platinumCustomerGetsTenPercentLoyaltyDiscount PLATINUM customers should "
    "get a 10% loyalty discount, not 5%"
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


def run_claude(prompt: str, cwd: Path, system_prompt: str, tools: str):
    cmd = [
        CLAUDE_BIN,
        "-p",
        prompt,
        "--output-format",
        "json",
        "--system-prompt",
        system_prompt,
        "--model",
        "sonnet",
        "--tools",
        tools,
        "--permission-mode",
        "acceptEdits",
    ]

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
    shutil.rmtree(project_dir.parent, ignore_errors=True)
    return {
        "variant": "naive",
        "fixed_file": fixed_file,
        "test_passed": passed,
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
    shutil.rmtree(project_dir.parent, ignore_errors=True)
    return {
        "variant": "rag-lite",
        "fixed_file": fixed_file,
        "retrieved_files": retrieved,
        "test_passed": passed,
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
    shutil.rmtree(project_dir.parent, ignore_errors=True)
    return {
        "variant": "jit-loading",
        "fixed_file": None,
        "test_passed": passed,
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
        system_prompt=DEPENDENCY_GRAPH,
        tools="Read,Glob,Grep,Edit,Write",
    )
    passed = run_mvn_test(project_dir)
    shutil.rmtree(project_dir.parent, ignore_errors=True)
    return {
        "variant": "dependency-graph",
        "fixed_file": None,
        "test_passed": passed,
        **summarize_usage(cli_json),
    }


def run_context_file() -> dict:
    project_dir = make_temp_copy()
    claude_md = (project_dir / "CLAUDE.md").read_text()
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
    shutil.rmtree(project_dir.parent, ignore_errors=True)
    return {
        "variant": "context-file",
        "fixed_file": None,
        "test_passed": passed,
        **summarize_usage(cli_json),
    }


def main():
    RESULTS_DIR.mkdir(exist_ok=True)
    runs = []
    for label, fn in [
        ("naive", run_naive),
        ("rag-lite", run_rag_lite),
        ("jit-loading", run_jit_loading),
        ("dependency-graph", run_dependency_graph),
        ("context-file", run_context_file),
    ]:
        print(f"Running variant: {label} ...")
        t0 = time.time()
        r = fn()
        r["wall_seconds"] = round(time.time() - t0, 1)
        runs.append(r)
        print(f"  -> {r}")

    out_path = RESULTS_DIR / f"run_{int(time.time())}.json"
    out_path.write_text(json.dumps(runs, indent=2))

    print("\n=== Summary ===")
    header = f"{'variant':14} {'input_tok':>10} {'cache_create':>12} {'output_tok':>10} {'cost_usd':>9} {'turns':>6} {'pass':>5}"
    print(header)
    for r in runs:
        total_input = r["input_tokens"] + r["cache_creation_input_tokens"] + r["cache_read_input_tokens"]
        print(
            f"{r['variant']:14} {total_input:>10} {r['cache_creation_input_tokens']:>12} "
            f"{r['output_tokens']:>10} {r['total_cost_usd']:>9.4f} {r['num_turns']:>6} {str(r['test_passed']):>5}"
        )
    print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    main()
