# Building the AI CTD Platform with Claude Code

How to use Claude Code to build the authoring and cross-validation platform, following the Technical Build Spec.

---

## 1. Set up the repo once

- **Put the spec in the repo.** Export the Technical Build Spec to `docs/spec.md`. Add the regulatory sources you build against to `docs/reference/`: ICH M4, E3 and Q-series PDFs, FDA eCTD specs and DTDs, a few public EPARs. Claude Code works from files it can read; anything missing it will guess from memory — and regulatory rules are exactly what you can't let it guess.
- **Write `CLAUDE.md`** (run `/init` to draft it, then trim to about a page):

  - Stack and commands: how to run the app, tests, migrations, evals.
  - Hard rules:
    - `platform/` never imports `products/`.
    - Every table has `tenant_id` + row-level security.
    - Only `platform/llm/` calls Claude.
    - No AI in `publishers/` or `validation/`.
    - Never edit applied migrations.
  - "Done means tests pass and `make check` is green."
- **Path-specific rules in `.claude/rules/`**, loaded only when relevant. Example for `products/ectd/**`: "templates and profiles are data; cite the ICH/FDA source file for any rule."
- **Permissions:** allow `pytest`, `ruff`, `alembic`, `pnpm` without prompting; deny anything touching production.

---

## 2. The same loop for every feature

Take the week-by-week rows of the spec one at a time. Each row's "Done when" is the acceptance test.

1. **Explore** — have Claude read the relevant spec section and existing code, and summarise what exists.
2. **Plan** (plan mode) — files, schema changes, tests. Push back here, where changes are cheap.
3. **Tests first** — failing tests from the "Done when" criterion, before any code.
4. **Implement** until tests and `make check` pass.
5. **Review** — a reviewer subagent with a fresh context checks the diff against `CLAUDE.md` and the spec section.
6. **Commit, then `/clear`** — one feature per session keeps the context clean.

**Example first prompt:**

> Read docs/spec.md section 4 and CLAUDE.md. Plan the platform tables (tenant, app_user, document, page, chunk, audit_log) with Alembic migrations, RLS policies, and a test proving tenant A cannot read tenant B's rows. Don't write code until I approve the plan.

---

## 3. Build order for authoring and cross-validation

| Order | Build                                                        | Spec section |
| ----- | ------------------------------------------------------------ | ------------ |
| 1     | Foundations: tenancy, upload, parsing, search, audit         | 4, 6         |
| 2     | Application setup: region profile, wizard, dossier tree      | 5            |
| 3     | Citation checks (quote match, numbers), then the LLM gateway | 7            |
| 4     | Template engine + fact store + the six slot kinds            | 7            |
| 5     | Drafter agent (LangGraph) + section editor + review/sign-off | 7, 9         |
| 6     | M3 templates, then M1, M2.3, M5, M2.5/2.7                    | 7            |
| 7     | Cross-validator + dependency graph                           | 8            |

Build the checker **before** the drafter, so every AI output is verified from its first run.

---

## 4. Custom subagents and skills worth creating

- **`reviewer`** (read-only) — checks diffs for RLS gaps, missing tests, cross-layer imports, and AI calls outside `platform/llm/`.
- **`reg-checker`** (read-only, with access to `docs/reference/`) — checks that a template or profile rule matches its cited ICH/FDA source.
- **`new-template` skill** — the steps for adding a CTD section template: YAML, slots, guideline references, fixture, eval case. You'll repeat this dozens of times.

---

## 5. Where not to trust it

- **Regulatory content.** Section requirements, Module 1 rules and format dates must come from files in `docs/reference/`, and you check them yourself. Treat any rule Claude "knows" without citing a file as wrong until verified.
- **Prompts and verifier thresholds.** Change only with an eval run showing the scores held.
- **Security.** Read every RLS policy and auth change yourself.

---

## 6. Automate the gates

- Run the test suite and eval suite on every PR in GitHub Actions; a drop in scores fails the build.
- Use `claude -p` (headless mode) in scripts, e.g. to regenerate fixtures.
- Use git worktrees to run a second session on the frontend while the main one works on the backend. Solo, two parallel sessions is the practical limit.

---

## Sources

- [Claude Code best practices](https://code.claude.com/docs/en/best-practices.md)
- [Memory / CLAUDE.md](https://code.claude.com/docs/en/memory.md)
- [Subagents](https://code.claude.com/docs/en/sub-agents.md)
- [Skills](https://code.claude.com/docs/en/skills.md)
- [Hooks](https://code.claude.com/docs/en/hooks-guide.md)
- [MCP](https://code.claude.com/docs/en/mcp.md)
- [Permission modes](https://code.claude.com/docs/en/permission-modes.md)
- [Headless mode](https://code.claude.com/docs/en/headless.md)
- [GitHub Actions](https://code.claude.com/docs/en/github-actions.md)
