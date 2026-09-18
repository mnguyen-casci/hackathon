# Context Optimization Strategies

Candidate approaches for improving token efficiency when an LLM agent works
against a project codebase. Two are being implemented and benchmarked for
this hackathon; the rest are documented here as framing/future-work context.

## Selected for implementation

### 1. Structured context file (CLAUDE.md / AGENTS.md pattern)
A single root file summarizing architecture, conventions, build/test
commands, and key entry points, so the agent doesn't rediscover the codebase
from scratch every session.

- **Branch:** `feature/context-file`
- **Reference:** Anthropic, "Effective context engineering for AI agents";
  "On the Impact of AGENTS.md Files on the Efficiency of AI Coding Agents" (2026)

### 2. Just-in-time (JIT) loading
Instead of pasting full file contents into the prompt upfront, the agent is
given lightweight pointers (a file tree, function/class names) and a tool to
fetch specific file contents on demand, only pulling what it actually needs.

- **Branch:** `feature/jit-loading`
- **Reference:** Anthropic, "Effective context engineering for AI agents"
  (just-in-time context loading pattern used by Claude Code)

## Documented, not implemented

### 3. Retrieval over inclusion (RAG-lite for code)
Index the codebase by function/class chunk; retrieve only the relevant chunk
for a given question instead of loading whole files. Stronger for large
codebases, more build effort than JIT loading for a small demo repo.

### 4. Tool-schema lazy loading
Only load full tool JSON schemas on demand (cheap keyword match against the
task) rather than upfront, when an agent has access to many tools. Not
applicable here since the demo only uses one or two tools.

### 5. Context pruning / compaction over a session
Periodically summarize session history and drop stale file contents as a
multi-step task progresses, instead of letting context grow monotonically.

- **Reference:** Anthropic Cookbook, "Automatic context compaction for
  agentic workflows"

### 6. Dependency-graph summarization
Replace raw file dumps with a compressed call/dependency graph (which
classes/files call which) for "explain/debug this feature" style tasks,
letting the model reason about structure without reading everything.

## Supporting research (framing / motivation)

- **LLMLingua / LongLLMLingua** (Microsoft) — token-level prompt compression;
  reports 17.1% better performance with 4x fewer tokens on GPT-3.5-Turbo.
- **NoLiMa benchmark** — "lost in the middle" effect; 11/12 tested models
  dropped below 50% of short-context performance at 32K tokens.
- **ACON (Agent Context Optimization)** — reduces peak token usage 26-54% in
  multi-step agents while maintaining task performance.
- **"Less Context, Better Agents"** (2026) — benchmark methodology isolating
  the efficiency/accuracy trade-off for high-stakes agent workflows.

## Benchmark plan

Same task (find and fix a bug in the sample Java project) run three ways,
measuring input/output tokens, cost, and pass/fail:

1. **Naive baseline** (`main`) — full file contents dumped into the prompt
2. **Context-file variant** (`feature/context-file`)
3. **JIT-loading variant** (`feature/jit-loading`)

Results captured via `benchmark.py` against the Claude API.
