#!/usr/bin/env python3
"""
RAG-lite stress test: does keyword retrieval survive a bug whose symptom
shares no vocabulary with the buggy code?

The main benchmark's bug (LoyaltyService giving PLATINUM the same discount
as GOLD) is inherently easy for keyword retrieval: a bug report about
"loyalty" and "discounts" naturally overlaps with a file called
LoyaltyService. This script builds a harder case on the same codebase: a
one-line rounding bug (floor instead of round-to-nearest-cent) in a small
CurrencyUtil class. The failing assertion is just two numbers
(`expected: <115.5> but was: <115.49>`) -- no descriptive words connecting
the symptom to the file -- and the realistic bug report ("finance flagged a
batch of totals that don't quite match") shares no vocabulary with
CurrencyUtil.round()/Math.floor either.

Patches a temp copy at runtime rather than changing the committed source:
the LoyaltyService PLATINUM bug is fixed in the patched copy (so only one
bug is live for this scenario) and the CurrencyUtil floor bug is
introduced. The actual repo source is untouched -- the main benchmark's
premise stays exactly as published.

Runs naive, rag-lite, and jit-loading (not all seven -- this is a targeted
stress test of retrieval specifically, not a full re-run) and reports
whether rag-lite's retrieval step actually included the buggy file.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark as bm

RESULTS_DIR = Path(__file__).resolve().parent / "results"

STRESS_SOURCE_FILES = bm.SOURCE_FILES + [
    "src/main/java/com/hackathon/orders/util/CurrencyUtil.java"
]

STRESS_FAILING_TEST_OUTPUT = (
    "org.opentest4j.AssertionFailedError: expected: <115.5> but was: <115.49>"
)

STRESS_TASK_RULES = (
    "`mvn test` currently fails with:\n"
    f"{STRESS_FAILING_TEST_OUTPUT}\n"
    "(in grandTotalMatchesExactPipelineComputation)\n\n"
    "Find the bug causing this failure and fix it. Do not modify the test file "
    "(OrderProcessorTest.java)."
)

STRESS_RAG_QUERY = (
    "Finance flagged that a batch of order totals don't quite match what "
    "our pricing formula should produce -- off by a small figure, and it's "
    "hard to tell which orders are affected."
)


def make_patched_temp_copy() -> Path:
    """Same as bm.make_temp_copy(), but on top of that: fixes the
    LoyaltyService PLATINUM bug (so only the rounding bug is live) and
    introduces the CurrencyUtil floor bug."""
    project_dir = bm.make_temp_copy()

    loyalty_path = project_dir / "src/main/java/com/hackathon/orders/service/LoyaltyService.java"
    content = loyalty_path.read_text()
    fixed = content.replace(
        "case PLATINUM:\n                return 0.05;",
        "case PLATINUM:\n                return 0.10;",
    )
    if fixed == content:
        sys.exit("Could not patch LoyaltyService.java -- source text has changed.")
    loyalty_path.write_text(fixed)

    currency_path = project_dir / "src/main/java/com/hackathon/orders/util/CurrencyUtil.java"
    content = currency_path.read_text()
    buggy = content.replace(
        "return Math.round(amount * 100.0) / 100.0;",
        "return Math.floor(amount * 100.0) / 100.0;",
    )
    if buggy == content:
        sys.exit("Could not patch CurrencyUtil.java -- source text has changed.")
    currency_path.write_text(buggy)

    return project_dir


def stress_dump_files(project_dir: Path) -> str:
    parts = []
    for rel in STRESS_SOURCE_FILES:
        path = project_dir / rel
        parts.append(f"--- {rel} ---\n{path.read_text()}")
    return "\n\n".join(parts)


def stress_file_tree(project_dir: Path) -> str:
    return "\n".join(sorted(rel for rel in STRESS_SOURCE_FILES if (project_dir / rel).exists()))


def run_stress_naive() -> dict:
    project_dir = make_patched_temp_copy()
    prompt = (
        "You are working on a small Java Maven project. Here are all of its "
        f"source files.\n\n{stress_dump_files(project_dir)}\n\n{STRESS_TASK_RULES}\n\n"
        "Respond with ONLY the following, no other text:\n"
        "FILE: <path to the file you changed, relative to the project root>\n"
        "```java\n<the complete corrected contents of that file>\n```"
    )
    cli_json = bm.run_claude(
        prompt,
        cwd=project_dir,
        system_prompt="You are a precise software engineer. Follow the output format exactly.",
        tools="",
    )
    fixed_file = bm.apply_naive_fix(project_dir, cli_json.get("result", ""))
    passed = bm.run_mvn_test(project_dir) if fixed_file else False
    shutil.rmtree(project_dir.parent, ignore_errors=True)
    return {
        "variant": "naive",
        "fixed_file": fixed_file,
        "test_passed": passed,
        **bm.summarize_usage(cli_json),
    }


def run_stress_rag_lite() -> dict:
    project_dir = make_patched_temp_copy()
    retrieved = []
    scored = []
    for rel in STRESS_SOURCE_FILES:
        path = project_dir / rel
        if not path.exists():
            continue

        def tokenize(text):
            import re

            return set(re.findall(r"[a-zA-Z][a-zA-Z0-9]{2,}", text.lower()))

        score = len(tokenize(STRESS_RAG_QUERY) & tokenize(path.read_text()))
        scored.append((score, rel))
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    retrieved = [rel for _, rel in scored[:5]]

    found_buggy_file = "src/main/java/com/hackathon/orders/util/CurrencyUtil.java" in retrieved

    dumped = "\n\n".join(
        f"--- {rel} ---\n{(project_dir / rel).read_text()}" for rel in retrieved
    )
    prompt = (
        "You are working on a small Java Maven project. A retrieval step "
        f"selected the {len(retrieved)} files judged most relevant to the "
        f"failing test below, out of {len(STRESS_SOURCE_FILES)} files in the "
        f"project; only those are shown here.\n\n{dumped}\n\n{STRESS_TASK_RULES}\n\n"
        "Respond with ONLY the following, no other text:\n"
        "FILE: <path to the file you changed, relative to the project root>\n"
        "```java\n<the complete corrected contents of that file>\n```"
    )
    cli_json = bm.run_claude(
        prompt,
        cwd=project_dir,
        system_prompt="You are a precise software engineer. Follow the output format exactly.",
        tools="",
    )
    fixed_file = bm.apply_naive_fix(project_dir, cli_json.get("result", ""))
    passed = bm.run_mvn_test(project_dir) if fixed_file else False
    shutil.rmtree(project_dir.parent, ignore_errors=True)
    return {
        "variant": "rag-lite",
        "fixed_file": fixed_file,
        "retrieved_files": retrieved,
        "found_buggy_file_in_retrieval": found_buggy_file,
        "test_passed": passed,
        **bm.summarize_usage(cli_json),
    }


def run_stress_jit_loading() -> dict:
    project_dir = make_patched_temp_copy()
    prompt = (
        "You are working on a Java Maven project. Here is its file tree "
        f"(relative to the current directory):\n\n{stress_file_tree(project_dir)}\n\n"
        f"{STRESS_TASK_RULES} Use the available tools to read whatever files you "
        "need before editing."
    )
    cli_json = bm.run_claude(
        prompt,
        cwd=project_dir,
        system_prompt="You are a careful software engineer. Make the minimal correct fix.",
        tools="Read,Glob,Grep,Edit,Write",
    )
    passed = bm.run_mvn_test(project_dir)
    shutil.rmtree(project_dir.parent, ignore_errors=True)
    return {
        "variant": "jit-loading",
        "fixed_file": None,
        "test_passed": passed,
        **bm.summarize_usage(cli_json),
    }


def main():
    RESULTS_DIR.mkdir(exist_ok=True)
    runs = []
    for label, fn in [
        ("naive", run_stress_naive),
        ("rag-lite", run_stress_rag_lite),
        ("jit-loading", run_stress_jit_loading),
    ]:
        print(f"Running variant: {label} ...")
        t0 = time.time()
        r = fn()
        r["wall_seconds"] = round(time.time() - t0, 1)
        runs.append(r)
        print(f"  -> {r}")

    out_path = RESULTS_DIR / f"rag_stress_test_{int(time.time())}.json"
    out_path.write_text(json.dumps(runs, indent=2))

    print("\n=== RAG-lite stress test summary ===")
    for r in runs:
        print(f"{r['variant']:12} test_passed={r['test_passed']}", end="")
        if r["variant"] == "rag-lite":
            print(f"  found_buggy_file_in_retrieval={r['found_buggy_file_in_retrieval']}", end="")
            print(f"  retrieved={r['retrieved_files']}", end="")
        print()
    print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    main()
