# Claude supervision workflow

Read `AGENTS.md` and `.codex/agent-contract.md`. The matching Codex role owns
the domain checklist for both hosts. Read its `developer_instructions` as
review criteria. Claude domain supervisors delegate source edits to Codex.
They MUST NOT apply application or test fixes through Bash, Edit, or Write.

## Dispatch

1. Confirm the checkout and current diff. Read the matching domain role.
2. Write a self-contained task file in a private temporary directory. Include:
   goal, owned files, interfaces, acceptance criteria, base revision, branch,
   existing changes, checks, permitted operations, and explicit exclusions.
3. Tell Codex to read its role file, `AGENTS.md`, and the shared contract.
   State that other workers share the codebase and their edits MUST remain.
4. Pass the task on stdin. Do not interpolate task text into a shell command.
   Use explicit paths. Keep task files and event logs out of tracked source.

```bash
codex exec -C "<checkout>" -s workspace-write --json \
  -o "<report-file>" - < "<task-file>" > "<events-file>"
```

Capture the exact session ID from the JSON event stream. Record it with the
checkout, branch, and assignment. Wait for completion and check the exit status.
When returning a defect, send a focused follow-up on stdin:

```bash
codex exec resume "<session-id>" --json \
  -o "<follow-up-report>" - < "<follow-up-task>" > "<follow-up-events>"
```

Run the resume command from the recorded checkout. If the ID is unavailable,
start a new explicit assignment that describes the existing diff. Do not use
`resume --last`, permission bypass flags, or a guessed session ID.
Role instructions passed through a prompt do not change the CLI sandbox.

## Verify the handoff

- Read the final diff against the actual parent, including uncommitted changes.
  Confirm ownership, acceptance criteria, and compatibility with dependent work.
- Read `pr-verify` for a pull-request review. Run the matching role's checks
  against the proposed revision. Summarize results rather than dumping logs.
- Check the domain's failure and security boundaries, not just happy paths.
  A fingerprint change needs the underlying permission diff.
- A regression demonstration can use a prior revision or a disposable copy.
  Have Codex perform any source mutation there. Never reset a shared file.
- Return precise failures to the same session. Rerun only affected checks after
  a correction. Preserve failed results and report any remaining limit.
- Do not claim a task ran under a native role merely because it read a TOML file.
  Report the dispatch method and what was actually exercised.

## Host and authority boundaries

Claude subagents cannot spawn nested subagents. A tech lead launched as the
main agent can dispatch domain agents; a nested tech lead returns assignments
to its parent. A domain supervisor can use the explicit Codex CLI handoff.
Use available host tools; do not assume a browser or external connector exists.

These tool allowlists reduce accidental edits. Bash remains capable of writes
and network operations; source-write and AWS boundaries also rely on host
permissions and explicit task authority. Do not change permission settings to
make a role work. Keep the user's model choice; role files do not force one.
