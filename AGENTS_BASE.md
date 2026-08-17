# AI agent guidance (repository baseline)

This file is the **shared baseline** for anyone using AI coding assistants (Cursor, Claude Code, OpenAI Codex, or similar) on this repository. Most tools do **not** auto-read this filename; keep it accurate and **mirror** it into each tool’s native location (see below).

## Rules

Read and follow all rules in `.cursor/rules/`. Treat rules with `alwaysApply: false` as on-demand (only apply when explicitly asked).

---

## How to use this file in your agent setup

| Tool / ecosystem | Typical location | Suggested pattern |
|------------------|------------------|-------------------|
| **Cursor** | `.cursor/rules/*.mdc` or project rules in Cursor settings | Copy or summarize sections you care about into rules, or add one rule: “Follow `AGENTS_BASE.md` in the repo root.” |
| **Claude Code** | `CLAUDE.md` (repo root) | Generate or maintain `CLAUDE.md` from this file; keep Claude-only overrides there. |
| **OpenAI Codex** | `AGENTS.md` (repo root) | Generate or maintain `AGENTS.md` from this file; keep Codex-only overrides there. |
| **Other agents** | Varies | Point the agent at this file in the first message, or add a one-line `AGENTS.md` that says: “Read and follow `AGENTS_BASE.md`.” |

---

## Agent skills

Before handling domain-specific or repetitive workflows, check **`.agents/skills/`** (if present). Each skill is usually a directory with a `SKILL.md` (instructions, examples, constraints).

---

## Project context (short)

**Isaac Mission Control** — lightweight fleet manager: coordinates Isaac Cloud Services, builds behavior trees for missions, uses maps / graphs / routing (SWAGGER, cuOpt) and Mission Dispatch / VDA5050. API details: `docs/api.md`. Tutorials: `docs/tutorial/tutorial.md`, config: `docs/config_tutorial.md`.

---

## Development tips

- Prefer the **developer Docker** workflow from `README.md` (`./scripts/run_dev.sh`) so Bazel and dependencies match CI and the team.
- Default app config: `app/config/defaults.yaml`.
- For API or mission behavior, cross-check `docs/api.md` and existing endpoints under `app/api/` before inventing new contracts.
- Keep changes **focused**: match existing style, types, and patterns; avoid unrelated refactors in the same change.

---

## Tests

Follow **`README.md`** for the canonical commands. In the dev container, the usual check is:

```bash
bazel test ...
```

If image pulls time out, `README.md` documents `PULLER_TIMEOUT` and `--test_timeout` options.

Run tests (or the smallest relevant target) **before** opening a merge request.

---

## Merge requests / pull requests

- **Title format:** `[<project_name>] <short descriptive title>`  
  Example: `[mission-control] Fix multi-object pickplace validation`
- **Size:** Prefer changes **under ~1000 lines** per MR/PR; split large work by feature or reviewable chunk.
- **Quality bar:** Run the appropriate tests; describe what changed and why in the MR/PR description (complete sentences, no unnecessary scope creep).
