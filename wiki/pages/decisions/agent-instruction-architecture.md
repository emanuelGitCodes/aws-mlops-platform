---
type: decision
title: Agent instructions split into rules, skills, and a completion gate
created: "2026-08-31"
updated: "2026-08-31"
sources: ["../../../AGENTS.md", "../../../scripts/agent_gate.py", "../../../tests/unit/test_agent_gate.py", "../../../.claude/hooks.json", "../../../.claude/skills/house-style/SKILL.md", "../../../.claude/skills/stacked-prs/SKILL.md", "../../../Makefile", "../../../pyproject.toml"]
summary: "AGENTS.md keeps only the rules an agent needs before its first tool call, six skills carry the procedure, and a Stop hook runs the checks that the changed files need."
---
# Agent instructions split into rules, skills, and a completion gate

## Confirmed

- **`AGENTS.md` fell from 4172 words to 2093.** The removed text was mostly
  the phase-status block, which restated
  [the phased hardening roadmap](../architecture/phased-security-hardening.md).
  The file now states no phase status. It keeps four invariants: the website
  hold, the private repository, the two-policy execution boundary, and the
  account-literal ban.
- **Six skills carry the procedure.** `house-style`, `no-duplicate-code`,
  `phase-change-set`, `deploy-verify`, `wiki-record`, and `stacked-prs` live
  under `.claude/skills/`. Each one loads when its trigger matches, so a
  session pays for the text only when the task applies. The repository rules
  for the code graph append to the vendored `graphify` skill.
- **`.agents/skills/` symlinks the host-neutral skills.** The `graphify` skill
  keeps a separate copy there, because three of its lines name the host.
- **`scripts/agent_gate.py` runs from three hooks.** `Stop` reads
  `git status`, selects the Make targets the changed files need, and runs them.
  A failure exits 2, which returns the output to the agent instead of ending
  the turn. `SessionStart` prints whether the code graph matches `HEAD`.
  `PreToolUse` on Bash asks the operator before a `deploy`, `deploy-stack`,
  `destroy`, or `bootstrap` target.
- **The gate blocked a real failure before it shipped.** With an unused import
  added to `src/common/drift.py`, it printed `The completion gate failed: make
  lint`, quoted the F401 and E402 output, and exited 2.
- **A pull request MUST NOT add more than 150 lines of code.** `make pr-size`
  measures it, and the `Stop` gate runs the same check first. The count covers
  `src/`, `infra/`, `scripts/`, and `website/`, and counts added lines only.
- **The coverage floor rose from 94.74 to 95.02** across the change set.
- **Four pull requests merged on 2026-08-31**, in order: the pip advisory fix,
  the instruction split, the completion gate, and the size cap.

## Synthesis

- **The always-on file pays a cost on every session, and status is the worst
  thing to put in it.** A phase-status copy in `AGENTS.md` goes stale between
  edits, and an agent trusts it. The test for keeping a line is whether an
  agent gets something wrong on its first tool call without it. Command names
  and the code map pass that test. Sentence-length rules do not, because they
  matter only once prose is being written.
- **A model that checks its own work produces false positives.** Prose stating
  "report at the granularity your evidence supports" does not enforce itself.
  A Make target passes or fails on its own, so the enforcement moved outside
  the model. This extends the rule that
  [reporting a deployment](../architecture/permissions.md) needs
  resource-level evidence, and applies it to every completion claim.
- **The cap excludes tests and Markdown on purpose.** A cap that counted tests
  would reward writing fewer of them, and the coverage floor pushes the other
  way. Two rules that fight produce the weaker outcome.
- **A gate MUST offer a path to satisfy it.** The gate does not run
  `make synth-all` or `make frontend-check`, which take minutes. It names them
  instead, so a report can say which check did not run. A gate that blocks with
  no way to satisfy it produces a loop.
- **The size check first measured only committed work.** The `base...HEAD`
  form reported zero lines on a branch holding 151 uncommitted lines, which is
  exactly when the number matters. It now measures from `git merge-base` to the
  working tree.

## Tensions or open questions

- **The hooks are inert until an operator installs them.** Git does not track
  `.claude/settings.json`, so `make agent-hooks` is a manual step per clone and
  per machine, the same as `make graph-hooks`. Nothing warns that the hooks are
  missing.
- **The assistant cannot write `.claude/settings.json`.** The harness guards
  the file that carries permissions and hooks. This is why `.claude/hooks.json`
  is tracked and a Make target installs it.
- **The permission allowlist is unchanged.** A narrowed list was proposed and
  not applied. The current list grants `Bash(aws cloudformation *)`, which
  includes `delete-stack`.
- **The cap has no continuous-integration check.** Enforcement is local by
  choice, because a blocking job would fail every Dependabot pull request and
  every approved large refactor. A branch that never runs the gate can still
  open an oversized pull request.
- **`house-style` and `stacked-prs` also exist at the operator's user level**,
  outside this repository, so that they apply to every project. The project
  copies win here and stay complete, because a public release MUST stand on
  its own. The two sets can drift, and no check compares them.
- **The split axes in `stacked-prs` are untested against live work.** No
  feature has yet needed a real split.
