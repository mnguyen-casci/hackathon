# Context Optimization Strategies

Candidate approaches for improving token efficiency when an LLM agent works
against a project codebase. All six were implemented and benchmarked
end-to-end against the sample Java project's bug-fix task; results are on
the [dashboard](https://claude.ai/artifact/LF3GVEzEWiypYVJnmUq8Zq) and in
`benchmark/results/latest.json`.

## Implemented

### 1. Structured context file (CLAUDE.md / AGENTS.md pattern)
A single root file summarizing architecture, conventions, build/test
commands, and key entry points, so the agent doesn't rediscover the codebase
from scratch every session. `sample-project/CLAUDE.md` used as the system
prompt for the `context-file` variant, paired with Read/Glob/Grep/Edit/Write
tools.

- **Reference:** Anthropic, "Effective context engineering for AI agents";
  "On the Impact of AGENTS.md Files on the Efficiency of AI Coding Agents" (2026)

### 2. Just-in-time (JIT) loading
Instead of pasting full file contents into the prompt upfront, the agent is
given a bare file tree and Read/Glob/Grep/Edit/Write tools, fetching only
the specific files it decides it needs.

- **Reference:** Anthropic, "Effective context engineering for AI agents"
  (just-in-time context loading pattern used by Claude Code)

### 3. Retrieval over inclusion (RAG-lite for code)
Chunks the codebase at file granularity and scores each file by keyword
overlap against the failing test's name + assertion message (no embeddings
-- that's the "lite"), feeding only the top 5 files to a single-shot,
no-tools call. Implemented as the `rag-lite` variant.

- **Reference:** none found. General practice in the RAG space, not tied to
  a specific paper or write-up surfaced during this project's research.

### 4. Tool-schema lazy loading
Only load full tool JSON schemas on demand rather than upfront, when an
agent has access to many tools. Tested via a `many-tools` variant: identical
task/file-tree/prompt to `jit-loading`, but with the full default toolset
enabled instead of the 5 tools actually needed -- `jit-loading` itself
already represents the "lazy" side of this comparison.

- **Reference:** reporting on Claude Code's tool lazy-loading (via a Martin
  Fowler / morphllm write-up on the "1M token wall") states it cuts context
  by 95% by discovering and loading tool definitions on demand instead of
  front-loading every MCP tool's schema upfront.

### 5. Context pruning / compaction over a session
Periodically summarize session history and drop stale file contents as a
multi-step task progresses, instead of letting context grow monotonically.
Implemented as the `compaction` variant: same task/tools as `jit-loading`,
but forces `--autocompact 100000` (the CLI's minimum), since the default
1M-token window would never realistically trigger on a task this small.

- **Reference:** Anthropic Cookbook, "Automatic context compaction for
  agentic workflows"
- **Confirmed via `--debug --debug-file`:** the CLI logs explicit
  `autocompact: tokens=... level=... effectiveWindow=80000` events per turn
  (`effectiveWindow` is 80% of the configured `--autocompact` value, i.e.
  the warning threshold). A diagnostic run reached `level=warn` by the
  third turn but the task finished before crossing the full threshold, so
  compaction did **not** actually fire in that run. The task's natural
  token growth (roughly 80,000-135,000 tokens across the tool-based
  variants) sits right around the 100,000-token minimum threshold, so
  whether it triggers is inconsistent run-to-run rather than reliably
  yes or no -- an honest finding in itself, not a gap in the measurement.

### 6. Dependency-graph summarization
Replace raw file dumps with a compressed call/dependency graph (which
classes/files call which) instead of prose or a full dump, letting the
model reason about structure without reading everything. Implemented as the
`dependency-graph` variant: a hand-written call graph as the system prompt,
paired with the same tools as `jit-loading` and `context-file`.

- **Reference:** none found. Not tied to a specific paper or write-up
  surfaced during this project's research.

## Baseline

**Naive** — every relevant file dumped verbatim into the prompt, no tools.
The control group every other strategy is measured against.

## Supporting research (framing / motivation)

- **LLMLingua / LongLLMLingua** (Microsoft) — token-level prompt compression;
  reports 17.1% better performance with 4x fewer tokens on GPT-3.5-Turbo.
- **NoLiMa benchmark** — "lost in the middle" effect; 11/12 tested models
  dropped below 50% of short-context performance at 32K tokens.
- **ACON (Agent Context Optimization)** — reduces peak token usage 26-54% in
  multi-step agents while maintaining task performance.
- **"Less Context, Better Agents"** (2026) — benchmark methodology isolating
  the efficiency/accuracy trade-off for high-stakes agent workflows.

## Benchmark methodology

Same task (fix a cross-file bug in `sample-project`, a ~15-file Java/Maven
order-processing service) run seven ways: the naive baseline plus the six
strategies above. Each variant:

1. Gets its own fresh temp copy of `sample-project` (fully isolated, so all
   seven run concurrently with no shared state)
2. Runs against the bundled Claude Code CLI headlessly
   (`claude -p --output-format json --tools "..."`), authenticating through
   whatever account is already logged into Claude Code -- no separate
   Anthropic API key needed
3. Is checked for correctness via `mvn test` (objective pass/fail, no LLM
   grading needed for that part)
4. Has its fix captured as a unified diff and scored blind (no variant name
   attached) by a separate judge call, 1-10 on correctness, minimality, and
   code quality

Implemented in `benchmark/benchmark.py`. Run it with `python3 benchmark.py`;
results land in `benchmark/results/`, and copying a run over
`benchmark/results/latest.json` updates the published dashboard without
needing to rebuild it (the dashboard fetches that file directly).

## Key finding

On this single, self-contained bug-fix task, RAG-lite was both the cheapest
correct fix and the only strategy that beat the naive baseline outright.
Every tool-based strategy (jit-loading, dependency-graph, context-file,
compaction) landed in a similar, higher cost band than naive or RAG-lite,
because each spends multiple turns exploring and every turn re-sends the
growing conversation; cache reads are cheap per token but not free.
`many-tools` was the clear worst case, same task as `jit-loading` but with
the full default toolset available, isolating the cost of describing every
tool's schema upfront. All seven fixes scored 8/10 or higher on the blind
quality judge, so none of this reflects a correctness trade-off, it's a
genuine cost/turns finding worth presenting as-is rather than smoothing
over.
