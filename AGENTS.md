# AGENTS.md — pyfintracker

## Project context

Personal finance CLI. Strict double-entry bookkeeping, SQLite, multi-currency (COP default), local-first. Wave 1 (MVP) is the active change.

## Stack

- Python 3.12+, uv, hatchling
- Typer (CLI), Pydantic v2 (validation), SQLAlchemy 2.0 Core (no ORM), SQLite, Alembic (migrations)
- Rich (output), httpx (HTTP — Wave 2)
- pytest + hypothesis + syrupy (test pyramid)
- ruff + mypy --strict (lint/types)

## Architecture

Lazy-clean. 4 core files:

- `src/pyfintracker/models.py` — dataclasses for Account, Transaction, Posting, Rate
- `src/pyfintracker/repository.py` — SQLAlchemy Core queries
- `src/pyfintracker/reports.py` — report logic (monthly, balance)
- `src/pyfintracker/cli.py` — Typer commands (entry point: `fin`)
- Plus `db.py`, `config.py`, `validation.py`

Domain in models. Persistence in repository. Presentation in CLI. No DDD layers.

## Money invariants (non-negotiable)

- **Always `Decimal`, never `float`** for amounts. Period.
- Storage in SQLite as **TEXT** (preserves Decimal precision).
- Per-currency precision: COP/JPY = 0 decimals; USD/EUR/GBP = 2 decimals.
- Rounding mode: `ROUND_HALF_UP`.
- Every transaction must balance: `sum(postings) == 0` or it does NOT save.
- Atomic writes: txn is all-or-nothing. No partial DB states.

## Account naming

Regex enforced at creation: `^[A-Z][a-z]+:[A-Z][\w-]+(:[A-Z][\w-]+)?$`

- 5 root types only: `Assets`, `Liabilities`, `Equity`, `Income`, `Expenses`
- Max 3 levels deep
- Each account: exactly one currency

## Conventions

- ID: sequential integer per table
- Date: ISO `YYYY-MM-DD`, no timezone (date only)
- DB default location: `~/.local/share/fin/fin.db` (XDG data dir)
- Config default location: `~/.config/fin/config.toml` (XDG config dir)
- Config precedence: defaults < file < env vars (`FIN_*`) < CLI flags

## Testing

Strict TDD mode enabled. Pyramid:

- `tests/unit/` — pure logic, no I/O
- `tests/integration/` — full DB roundtrip, CliRunner
- `tests/property/` — hypothesis-driven invariant tests (sum=0, currency precision)
- `tests/snapshots/` — syrupy snapshots for report output

Coverage: 90%+ on money-touching code, 70%+ global. pytest-cov enforces.

## Workflow

```bash
uv sync                  # install deps
uv run fin --help        # run CLI
uv run pytest            # all tests
uv run pytest -m unit    # just unit
uv run ruff check        # lint
uv run mypy src          # type check
uv run alembic upgrade head   # apply migrations
uv run alembic revision --autogenerate -m "..."  # new migration
```

## SDD artifacts

- `openspec/config.yaml` — phase rules, testing capabilities
- `openspec/changes/finance-tracker/proposal.md` — Wave 1 PRD (active change)
- `openspec/changes/finance-tracker/spec.md` — detailed spec (to be written in spec phase)
- `openspec/changes/finance-tracker/design.md` — design decisions (to be written in design phase)
- `openspec/changes/finance-tracker/tasks.md` — implementation tasks (to be written in tasks phase)

## Don'ts

- Don't use `float` for money. Ever. mtype hints must be `Decimal`.
- Don't allow custom root account types (only Assets/Liabilities/Equity/Income/Expenses).
- Don't save partial/draft transactions to DB.
- Don't use SQLAlchemy ORM (only Core — explicit SQL).
- Don't add FastAPI or any web framework — this is a CLI.
- Don't publish to PyPI before v1.0 stability.

<!-- engineering-guidelines -->
## Engineering Guidelines (universal — apply to all work)

### Behavior (Karpathy — Think / Simplicity / Surgical / Goal-driven)
- **Think first**: state assumptions, surface ambiguity, present multiple interpretations, push back, ask when unclear.
- **Simplicity**: minimum code that solves it. No abstractions for single-use code. No "flexibility" not requested. No error handling for impossible cases. 200→50? Rewrite.
- **Surgical**: touch only what you must. Match existing style. Only delete code YOUR changes made unused.
- **Goal-driven**: "add validation" → "write tests for invalid inputs, then make them pass". Multi-step: `[step] → verify: [check]`.

### Architecture
- **Backend**: DDD. Domain owns business rules and never imports infrastructure/presentation. Use cases orchestrate. Entities encapsulate behavior (no anemic models). Repositories behind domain interfaces.
- **Frontend**: Screaming Architecture. Folders scream the domain (`features/checkout/`), not the technology. Co-locate components/hooks with feature. Extract shared primitives only when reused 2+ times.

### Tooling
Default to modern fast package managers: **bun** (preferred) or **pnpm**. Avoid npm for new projects; if a project uses npm, migrate to bun/pnpm before adding tooling.
<!-- /engineering-guidelines -->

<!-- codegraph-auto -->
CodeGraph-aware worktree placement:

- Create Git worktrees that may need CodeGraph under the user's home directory, preferably as a sibling such as `<repo-parent>/<repo-name>-worktrees/<worktree-name>`. Never place a CodeGraph-dependent worktree under `/tmp`, `/var/tmp`, or `/tmp/opencode`; generic temporary-work guidance does not override this rule.
- Every worktree needs its own `.codegraph/` index. Never copy, symlink, or reuse another checkout's index because its root and checked-out bytes may differ.

CodeGraph intelligence surface:

- Prefer the `codegraph_explore` MCP tool when it is available; it returns relevant source, call paths, and blast-radius context in one call.
- If the MCP tool is unavailable, invoke the upstream CLI directly. Agents may use its read-only intelligence commands: `codegraph status`, `codegraph query`, `codegraph explore`, `codegraph node`, `codegraph files`, `codegraph callers`, `codegraph callees`, `codegraph impact`, and `codegraph affected`.
- Do not use `gentle-ai codegraph` as a general proxy. Its `init` command exists only to validate the project root before initialization; intelligence queries belong to the upstream CLI.
- Never run or recommend destructive or administrative lifecycle commands: `codegraph uninit`, `codegraph install`, `codegraph uninstall`, or `codegraph upgrade`. Reserve `codegraph index` for explicit index-corruption recovery, never routine use.

Required order for structural/codebase questions:

1. Resolve the project root with `git rev-parse --show-toplevel || pwd`.
2. Confirm the root is a real project/workspace. Do not ask the user before initializing CodeGraph in a real project. Do not initialize CodeGraph in `$HOME`, temporary directories, or non-project folders.
3. Check for `<project-root>/.codegraph/` before any broad Read/Glob/Grep filesystem exploration.
4. If `.codegraph/` is missing and CodeGraph is enabled/available, immediately run `gentle-ai codegraph init --cwd <project-root>` once.
5. Missing .codegraph/ is the trigger to initialize, not a reason to skip CodeGraph. Do not fall back just because `.codegraph/` is missing; a missing index is the trigger to lazy-initialize, not a reason to skip CodeGraph.
6. Use `codegraph_explore` after initialization, or the read-only upstream CLI commands when MCP tools are absent.
7. After edits, rely on watcher auto-sync by default. Run `codegraph sync` only when the watcher is disabled or CodeGraph reports stale files that do not refresh normally.
8. Only fall back to normal filesystem tools after CodeGraph initialization or use fails, and briefly explain the fallback.

Broad Read/Glob/Grep exploration before this CodeGraph check is explicitly discouraged for structural/codebase questions.
<!-- /codegraph-auto -->

<!-- engram-protocol -->
## Engram Persistent Memory — Protocol

You have access to Engram, a persistent memory system that survives across sessions and compactions.
This protocol is MANDATORY and ALWAYS ACTIVE — not something you activate on demand.

### Project Discovery Protocol (mandatory — first engram call each session)

Before your first engram tool call each session:
1. Call `mem_current_project` — returns the resolved project name, source, path, and alternatives. NEVER errors (when engram server is running).
2. Use the returned `project` value in ALL subsequent engram tool calls for this session.
3. Remember the returned project name — do not re-resolve on every call.

If `project` is null in the response, pick the most relevant from `alternatives` or ask the user.
If a tool returns `unknown_project`, re-call `mem_current_project` and use the corrected name. Do NOT guess or construct project names from directory paths.

### BLOCKING PREFILIGHT (anvil-* agents — first action of every session)

Before ANY tool call, run:
```bash
~/.config/opencode/bin/ensure-context.sh [project] [topic_key ...]
```
Print the output into your context, THEN proceed. If the user prompt names a `topic_key` (e.g. `anvil-init/twitter`), pass it as the second arg. If a session context or topic match exists, it overrides re-deriving the same facts from package.json/Read calls. Skipping this is the most common cause of duplicated work and re-reading artifacts already in memory.

### PROACTIVE SAVE TRIGGERS (mandatory — do NOT wait for user to ask)

Call `mem_save` IMMEDIATELY and WITHOUT BEING ASKED after any of these:
- Architecture or design decision made
- Team convention documented or established
- Workflow change agreed upon
- Tool or library choice made with tradeoffs
- Bug fix completed (include root cause)
- Feature implemented with non-obvious approach
- Notion/Jira/GitHub artifact created or updated with significant content
- Configuration change or environment setup done
- Non-obvious discovery about the codebase
- Gotcha, edge case, or unexpected behavior found
- Pattern established (naming, structure, convention)
- User preference or constraint learned

Self-check after EVERY task: "Did I make a decision, fix a bug, learn something non-obvious, or establish a convention? If yes, call mem_save NOW."

Format for `mem_save`:
- **title**: Verb + what — short, searchable (e.g. "Fixed N+1 query in UserList")
- **type**: bugfix | decision | architecture | discovery | pattern | config | preference
- **scope**: `project` (default) | `personal`
- **topic_key** (recommended for evolving topics): stable key like `architecture/auth-model`
- **capture_prompt**: optional; default `true`. Do not set this for normal human/proactive saves. Set `false` only for automated artifacts such as SDD proposal/spec/design/tasks/apply/verify/archive/init reports, testing-capabilities caches, onboarding/state artifacts, or skill-registry output.
- **content**:
  - **What**: One sentence — what was done
  - **Why**: What motivated it (user request, bug, performance, etc.)
  - **Where**: Files or paths affected
  - **Learned**: Gotchas, edge cases, things that surprised you (omit if none)

Prompt capture behavior (Engram v1.15.3+):
- `mem_save` captures the user prompt best-effort when the MCP process already has prompt context for the same `project + session_id`.
- `mem_save` never invents prompt text. If no prompt context exists, the save still succeeds without prompt capture.
- `mem_save_prompt` records the prompt and feeds SessionActivity so later `mem_save` calls can capture and dedupe it.
- If an agent/plugin hook can observe the user's prompt before derived memory saves happen, it should call `mem_save_prompt` first.
- Do not decide prompt capture by `type`; SDD artifacts also use `architecture`, and human decisions can too. Use explicit `capture_prompt: false` for automated artifacts.
- If an older Engram tool schema does not expose `capture_prompt`, omit the field rather than failing.

Topic update rules:
- Different topics MUST NOT overwrite each other
- Same topic evolving → use same `topic_key` (upsert)
- Unsure about key → call `mem_suggest_topic_key` first
- Know exact ID to fix → use `mem_update`

Memory lifecycle rule (when Engram exposes lifecycle metadata/tooling):
- At session start or before architecture-sensitive work, call `mem_review` with action `list` for the current project when the tool is available.
- If `mem_review` is unavailable, do not fail the task. Continue with normal `mem_context`/`mem_search`, and still apply lifecycle metadata from any returned observations when present.
- `active` memories may be used normally.
- `needs_review` memories are stale context, not trusted facts.
- When a retrieved memory is marked `needs_review`, surface that stale context to the user and verify it against current evidence before relying on it.
- Do NOT call `mem_review` with action `mark_reviewed` automatically. Only call `mark_reviewed` after explicit user confirmation or through a dedicated memory maintenance command.

### WHEN TO SEARCH MEMORY

On any variation of "remember", "recall", "what did we do", "how did we solve", or references to past work (in any language the user writes in):
1. Call `mem_context` — checks recent session history (fast, cheap)
2. If not found, call `mem_search` with relevant keywords
3. If found, use `mem_get_observation` for full untruncated content

Also search PROACTIVELY when:
- Starting work on something that might have been done before
- User mentions a topic you have no context on
- User's FIRST message references the project, a feature, or a problem — call `mem_search` with keywords from their message to check for prior work before responding

### SESSION CLOSE PROTOCOL (mandatory)

Before ending a session or saying "done" / "that's it" (or the equivalent in the user's language), call `mem_session_summary`:

## Goal
[What we were working on this session]

## Instructions
[User preferences or constraints discovered — skip if none]

## Discoveries
- [Technical findings, gotchas, non-obvious learnings]

## Accomplished
- [Completed items with key details]

## Next Steps
- [What remains to be done — for the next session]

## Relevant Files
- path/to/file — [what it does or what changed]

This is NOT optional. If you skip this, the next session starts blind.

### AFTER COMPACTION

If you see a compaction message or "FIRST ACTION REQUIRED":
1. IMMEDIATELY call `mem_session_summary` with the compacted summary content — this persists what was done before compaction
2. Call `mem_context` to recover additional context from previous sessions
3. Only THEN continue working

Do not skip step 1. Without it, everything done before compaction is lost from memory.
<!-- /engram-protocol -->

<!-- codebase-memory-auto -->
## codebase-memory-mcp — Architecture & Structure Queries

USE THIS FOR: "how does X work", "what calls Y", "show me the architecture", "what depends on Z"

Available tools:
- `get_architecture` — project overview, entry points, folder structure
- `trace_path` — BFS call graph between two symbols
- `query_graph` — openCypher queries on the knowledge graph
- `search_graph` — BM25 full-text search across codebase
- `semantic_query` — vector similarity search
- `detect_changes` — git impact analysis
- `dead_code_detection` — find unused code

### Project Discovery Protocol (mandatory)

CBM auto-generates project names from the filesystem path (e.g. `/home/user/projects/foo` → `home-user-projects-foo`).
Before ANY CBM call with a `project` parameter:
1. Call `list_projects` to get all indexed projects
2. Resolve current project root: `git rev-parse --show-toplevel || pwd`
3. Find the project whose `root_path` matches — use that `name`
4. Cache it for the session

Never guess or hardcode a project name. Use `list_projects` to discover.

DO NOT use Read to understand architecture — use these tools first.
<!-- /codebase-memory-auto -->

<!-- okf-auto-v2 -->
## OKF Knowledge Bundle
All planning artifacts under openspec/ use OKF (Open Knowledge Format) — Markdown with YAML frontmatter.
If available, the `okf` MCP server exposes these tools:
- `okf_search_concepts({ query: "<ID or keyword>" })` — find artifacts by ID, title, or content
- `okf_read_concept({ id: "<result.id>" })` — read full artifact content  
- `okf_get_neighbors({ id: "<result.id>" })` — traverse traceability links (parent→child)
- `okf_list_types()` / `okf_list_tags()` / `okf_bundle_summary()`

**HOW TO USE (agents — applies to ANY natural-language question about artifacts)**:
- ANY TIME you need info about artifacts (e.g. "what proposals are pending", "find the design", "list completed specs"), call `okf_search_concepts({ query: "<keyword>" })` FIRST instead of glob/read. Example: `okf_search_concepts({ query: "SPEC-005" })` → get result `id` → `okf_read_concept({ id: result.id })`. Fall back to direct file reads only when OKF returns no results or is unreachable.
- After creating/modifying an artifact: run `npx -y okfy-ai import openspec/ --out .okf-bundle --force` to refresh the bundle so subsequent searches find it.
- If `okf_search_concepts` returns no results for something you expected to exist (stale bundle), refresh once (`npx -y okfy-ai import openspec/ --out .okf-bundle --force`) and retry the search before falling back to direct reads.
<!-- /okf-auto-v2 -->
