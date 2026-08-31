---
name: deploy-verify
description: "How to report what an AWS deployment actually changed in this repository, and why a stack status cannot tell you. Read it after any cdk deploy, before writing a deploy report or a wiki entry, and when make verify-deploy fails with AccessDenied. Holds the two-identity split between deploying and verifying."
---

# Reporting what a deployment changed

**Never state what a deployment changed based on a summary status.** A stack
reaches `UPDATE_COMPLETE` even when CloudFormation resolved the template to a
no-op and modified no resource at all. Asserting resource changes from stack
status has already produced two incorrect reports.

## The command

```bash
AWS_PROFILE=${AWS_SECURITY_AUDITOR_USER_NAME} make verify-deploy SINCE=<YYYY-MM-DD>
```

It lists, per stack, the last-updated timestamp and the resources that
actually changed. It says so explicitly when a stack changed nothing. Report
from its output, and quote the lines you are reporting.

## The two identities

Deploying and verifying use different identities, and this surprises every
new session:

| Task | Identity | Why |
|---|---|---|
| Deploy | `${MLOPS_DEPLOYER_USER_NAME}` | Holds the deploy grants |
| Verify | `${AWS_SECURITY_AUDITOR_USER_NAME}` or `${AWS_ADMIN_USER_NAME}` | Holds `cloudformation:ListStacks` |

`make verify-deploy` under the deploy identity fails with AccessDenied. That
is the identity split, not a broken target. Switch the profile and rerun.

## Three traps

1. **`cdk diff` is intent, not outcome.** CloudFormation resolves intrinsics
   such as `Ref: AWS::Partition` and then skips resources whose resolved form
   is unchanged. A diff hunk does **not** mean the resource was modified.
2. **The console stack list's default `Created time` column never changes on
   update.** It cannot tell you whether a stack was deployed today. Use the
   `Updated time` column or the per-stack Events tab.
3. **A dependency stack ships with its dependent.** `make deploy-stack`
   deploys the named stack and its dependencies. `verify-deploy` is how you
   learn which ones actually changed.

## The general rule

Report at the granularity your evidence supports. If the claim is about
resources, the evidence MUST be resource-level. When you have only a stack
status, say "the stack updated" and nothing more.
