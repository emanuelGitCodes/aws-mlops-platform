---
type: decision
title: The SageMaker SDK advisory stays open until the v3 migration
created: "2026-08-16"
updated: "2026-08-16"
sources: ["../../../pyproject.toml", "../../../uv.lock", "../../../src/pipeline/pipeline.py", "../../../infra/stacks/lambda_code.py", "../../../.github/workflows/ci.yml", "https://github.com/aws/sagemaker-python-sdk/security/advisories/GHSA-5r2p-pjr8-7fh7"]
summary: "Dependabot reports a high advisory against the SageMaker SDK. The vulnerable function is never called, the SDK never reaches a Lambda runtime, and the patch is a major version, so the fix belongs to a planned migration."
---
# The SageMaker SDK advisory stays open until the v3 migration

## Confirmed

- **The alert.** Dependabot opened alert 1 on 2026-08-10 against `uv.lock`.
  It cites `GHSA-5r2p-pjr8-7fh7`, "SageMaker Python SDK replaced eval() with
  safe parser in JumpStart search functionality". GitHub labels the severity
  high. The advisory carries no CVSS score and no CVSS vector. It maps to
  CWE-184.
- **The vulnerable code.** The advisory names `search_hub()` in the JumpStart
  search path. That function passed a query parameter to `eval()`. An actor
  who controls the query can run arbitrary commands. AWS released the fix, a
  recursive descent parser, in SageMaker Python SDK 3.4.0 on 2026-01-23. AWS
  states in the advisory that it is "informational" and a "defense-in-depth
  enhancement" under the shared responsibility model.
- **The affected range is every version below 3.4.0.** `pyproject.toml` pins
  `sagemaker>=2.220,<3`, and `uv.lock` resolves 2.257.5.
- **This repository never calls the vulnerable function.** A search over
  `src/`, `infra/`, `scripts/`, `website/`, and `tests/` for `search_hub`,
  `JumpStart`, and `jumpstart` returns no match. `src/pipeline/pipeline.py`
  holds every SageMaker SDK import: Pipelines, Processing, the SKLearn
  estimator, Model, ModelMetrics, and the workflow types.
- **The SDK never reaches a deployed runtime.** `sagemaker` belongs to the
  `pipeline` extra, which builds the pipeline definition from a workstation or
  from CI. `_RUNTIME_DEPS` in `infra/stacks/lambda_code.py` is
  `["pydantic==2.*"]`, so no Lambda bundle carries the SDK.
- **`make audit` passes.** pip-audit reports "No known vulnerabilities found"
  against the same lock file. The CI `audit` job is green.

## Synthesis

**The alert is true and unreachable.** Three conditions have to hold for the
advisory to describe a risk here: the code calls `search_hub()`, an attacker
reaches its query parameter, and the SDK runs where that attacker can act.
None of the three holds. The platform uses the SDK to describe a pipeline, and
the pipeline definition takes its values from `infra/config/*.yaml` and from
the repository, never from a request.

**pip-audit and Dependabot disagree because they read different feeds.**
pip-audit reads the PyPI advisory database, which does not carry this record.
Dependabot reads the GitHub Advisory Database, which does. A green `make audit`
is not evidence that the alert is wrong, and the open alert is not evidence
that CI missed something. Both tools are correct about their own source.

**The patch is a migration, not a bump.** The first patched version is 3.4.0,
and the pin stops below 3. SageMaker Python SDK v3 changed the estimator,
processor, and workflow API surface that `src/pipeline/pipeline.py` depends on.
Moving the pin means revalidating the pipeline definition and running training
end to end against the deployed account. That is its own change set under the
one-phase-per-change-set rule, and it is maintenance work worth doing on a
planned schedule rather than under the urgency of a high label.

**A public repository shows this alert.** Going public turns on GitHub secret
scanning and code scanning, and it also makes the security tab visible. A
reader who sees an open high alert and no written triage cannot tell the
difference between a considered decision and an ignored warning. This page is
the difference.

## Decision

The alert stays **open**, and the SDK stays on the 2.x pin. The dismissal is
available and defensible — GitHub's `vulnerable_code_not_actually_used` reason
matches the evidence above — and the open alert was kept as a standing marker
for the migration. Whoever changes this decision SHOULD record the reason here.

The migration to SageMaker Python SDK v3 is not scheduled. It carries the same
gate as any other phase: baseline, tests, synth, reviewed `cdk diff`, its own
commit, a scoped dev deploy, live checks, an observation window, and an
explicit go or no-go.

## Tensions or open questions

- **No end-to-end proof of the v3 API gap.** The claim that v3 breaks this
  pipeline comes from the major version boundary and the pin, not from a trial
  upgrade. A branch that installs 3.4.0 and runs `make test` would measure the
  real size of the migration. Nobody has run it.
- **The severity label is unresolved.** GitHub says high; AWS says
  informational and supplies no CVSS vector. This page treats the reachability
  analysis as the deciding evidence, not either label.
- **The alert count grows silently.** Dependabot alerts arrive on a push, and
  the message is easy to read past. No check fails when a new alert opens, so
  a second alert would need the same manual triage. See
  [phased security hardening](../architecture/phased-security-hardening.md)
  for the services that do gate on a check.
