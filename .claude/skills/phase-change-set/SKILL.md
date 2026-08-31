---
name: phase-change-set
description: "The one-phase-per-change-set gate for this repository's phased security-hardening roadmap. Read it before starting any phase or sub-phase work, before flipping a security.services flag in infra/config/*.yaml, and before any scoped dev deploy. Holds the ten-step sequence, the deploy-dependency trap, and the observation-window and go/no-go rules."
---

# One phase per change set

`wiki/pages/architecture/phased-security-hardening.md` is the status board.
**Read it first.** It holds the phase map, the per-phase status, and every
date. Do not trust a phase summary written anywhere else.

Two rules follow from the roadmap's operating rule:

1. **One phase per change set.** Ship one phase, prove it, then start the
   next. Prod is not touched while a phase is validated in dev.
2. **The wiki record ships with the phase.** Write the `wiki/log.md` entry
   and the page updates when the phase lands. Do not wait to be asked.

## The sequence

Every step produces evidence. Do not skip a step because the change looks
small — the roadmap's incidents all came from a skipped step.

1. **Baseline.** Record what exists now. Save the pre-change synth to the
   scratchpad so the diff has something to compare against.
2. **Change one thing.** One phase, one sub-phase, one flag under
   `security.services` in `infra/config/*.yaml`. Prod stays false until a
   deliberate rollout.
3. **`make test`.** Add or update the unit test that pins the new behaviour.
4. **`make synth-all`.** Both environments. This is the cdk-nag gate. A new
   acknowledgement MUST name the phase that removes it.
5. **Read `make diff-stack STACK=…`.** Read every hunk. Read the
   `Including dependency stacks: …` line — see the trap below.
6. **Its own commit.** The phase is one change set. Do not fold unrelated
   work into it.
7. **Scoped dev deploy.** `make deploy-stack STACK=… ENV=dev`. Never
   `make deploy` for phase work.
8. **`make verify-deploy SINCE=<YYYY-MM-DD>`.** Report resources, not stack
   status. The `deploy-verify` skill holds the identity split and the rules.
9. **Live checks, then the observation window.** Prove the control fires.
   An alarm that never evaluated is not proved. A rule that never matched is
   not proved.
10. **Explicit go or no-go**, written to `wiki/log.md` with the date.

## The deploy-dependency trap

**`deploy-stack` is not a single-stack deploy.** CDK deploys the named stack
and every stack it depends on, so a pending change anywhere in that chain
ships with it. A `Mlops-Dev-Monitoring` deploy has already shipped a second
sub-phase this way, because Monitoring imports the alert topic from
`Mlops-Dev-Security`.

The diff announces it on every run:

```
Including dependency stacks: …
```

Read that line before you deploy. Run `make verify-deploy` after, and report
which stacks actually changed. When a dependency shipped with your phase,
say so in the wiki entry — the two phases then share one observation window,
and that is a fact the record MUST carry.

## What proves a control works

An observation window closes as a go only on evidence that the control acted:

- **An alarm** MUST have evaluated and changed state. `TreatMissingData` does
  not cause an evaluation to run. An alarm in `INSUFFICIENT_DATA` proves
  nothing.
- **A notification path** MUST have delivered a real message to the endpoint.
- **A detective rule** MUST have produced a finding, or you MUST state that it
  is deployed and unproved.

State which of the three you have. "Deployed" is not "proved", and the wiki
entry MUST use the word that the evidence supports.

## Cost

Some phases start a bill. Enabling GuardDuty starts a 30-day free trial and
then bills monthly. Name the monthly cost in the change set, and get an
explicit decision before the deploy.
