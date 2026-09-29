# eklabs — AI CTD authoring & cross-validation platform

Full spec: `docs/spec.md`. Regulatory sources: `docs/reference/`. Read the relevant
spec section before working on a feature — don't rely on memory for CTD/eCTD rules.

## Stack

- Backend: Python 3.12, FastAPI, Pydantic, SQLAlchemy + Alembic
- Database: Postgres 16 + pgvector (row-level security per tenant); Neo4j for the
  regulatory knowledge graph
- Frontend: Next.js + TypeScript + shadcn/ui, TipTap editor, react-pdf viewer
- Agents: LangGraph + Postgres checkpoints
- LLMs: Claude via the Anthropic API — only `platform/llm/` calls it
- Background jobs: Redis + Arq; files in S3 (supabase)
- Ops: Docker Compose locally, GitHub Actions CI, Sentry, Langfuse

## Commands

- Full stack (local): `docker compose up`
- Backend tests: `pytest`
- Lint/format (Python): `ruff check .` / `ruff format .`
- Migrations: `alembic upgrade head` (new revision: `alembic revision --autogenerate -m "..."`)
- Frontend: `pnpm install`, `pnpm dev`, `pnpm test`
- Eval suite: `pytest evals/` (also runs in CI on any prompt/agent/check change)
- Everything CI checks: `make check` (lint + type check + tests + platform/product import rule)

## Hard rules

- `platform/` never imports from `products/`. This is what keeps it a platform;
  it's enforced by a CI check, not just convention.
- Every table has `tenant_id`, enforced by Postgres row-level security.
- Only `platform/llm/` calls Claude. No AI code anywhere else.
- No AI in `publishers/` or `validation/` — publishing and technical validation
  are plain code, zero AI, by design (see spec §10).
- Never edit an applied migration. Write a new one.
- Nothing is edited in place in the data model — a change is a new version row
  (see spec §4). This is what gives the audit trail for free.
- Regulatory content (section requirements, Module 1 rules, format dates) must
  cite a file in `docs/reference/`. Treat any rule Claude states without a
  citation as wrong until verified against a source file.

## Repo layout

See spec §3. Key boundary: `platform/` (shared) vs `products/` (per-product,
e.g. `products/ectd/`). One repo, `src/`-layout (`src/eklabs_platform/`,
`src/products/`).

**Python package name is `eklabs_platform`, not `platform`.** `platform` is a
Python stdlib module name — installing a top-level package under that exact
name makes it permanently unreachable (`import platform` always resolves to
the stdlib module; no layout or install method changes that). Every doc,
including this one, still says "`platform/`" for the conceptual layer per
spec §3 — only the actual directory and every Python import use
`eklabs_platform` instead.

## Done means

Tests pass and `make check` is green. For anything touching prompts, agents,
or checks, the eval suite must also hold its scores — a drop fails CI.
