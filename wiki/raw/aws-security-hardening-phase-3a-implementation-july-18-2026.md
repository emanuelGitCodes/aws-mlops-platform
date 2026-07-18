# AWS security hardening Phase 3A implementation — July 18, 2026

## Boundary and pre-state

Phase 3A is limited to the account-level IAM Access Analyzer external-access
analyzer in `us-east-1`. GuardDuty, AWS Config, Security Hub, account-level S3
Block Public Access, and security-finding EventBridge routing remain outside
this change.

The repository began clean on branch `issue/3-phase-3` at `de345a8`. The last
verified AWS record from Phase 3-prep showed a metadata-only
`Mlops-Dev-SecurityMonitoring` stack and no enabled Phase 3 services. A fresh
live inventory could not be completed because the configured AWS session had
no credentials. An interactive temporary-login flow was cancelled before
authorization, so no AWS resource was read or changed in this implementation
checkpoint.

## Implemented scope

1. `infra/stacks/security_monitoring_stack.py` now creates one
   `AWS::AccessAnalyzer::Analyzer` when the existing `access_analyzer` flag is
   true. The deterministic name is `mlops-dev-external-access`, its type is
   `ACCOUNT`, and its tags identify the project, dev environment, and Phase 3A.
2. The analyzer has no `AnalyzerConfiguration` and no `ArchiveRules`. This
   keeps the rollout on external-access analysis only and prevents automatic
   suppression before findings receive human review. AWS documents external
   access analysis as available at no additional charge.
3. `infra/config/dev.yaml` enables only `access_analyzer`. Production and the
   other five Phase 3 service flags remain false.
4. The Makefile gains guarded `diff-stack` and `deploy-stack` targets so later
   live work can operate only on the named SecurityMonitoring stack while
   preserving the repository command contract.
5. CDK assertions prove the exact analyzer properties and tags, absence of
   paid or archive configuration, dev-only enablement, and the production
   metadata-only shell. The IAM fingerprint remains unchanged because this
   resource creates no workload or deployment role.

## Local verification

- The stale untracked virtual environment was moved to a recoverable temporary
  location and recreated with `make install`; console-script paths now point
  to this checkout.
- `make lint`: passed; 47 files are formatted.
- `make test`: passed; 52 tests.
- `make security`: lock check passed with 108 packages, dependency audit found
  no known vulnerabilities, and all eight dev stacks synthesized with cdk-nag.
- Dry runs of the two named-stack Make targets render only the requested
  SecurityMonitoring stack commands.
- The synthesized SecurityMonitoring template contains exactly the new
  external-access analyzer plus `AWS::CDK::Metadata`. It has no outputs, IAM
  resources, archive rules, or paid analyzer configuration.

## Rollback and next checkpoint

This is implemented locally but not deployed. After temporary credentials are
available, re-run the complete read-only Phase 3 inventory. If an analyzer or
another unexpected Phase 3 resource already exists, stop without deleting or
adopting it. Otherwise review the no-change-set diff, require hosted CI for the
implementation commit, and deploy only `Mlops-Dev-SecurityMonitoring`.

Rollback is a revert of the Phase 3A implementation commit followed by the
same named-stack deployment. Do not delete the analyzer directly in the AWS
console. Phase 3B does not begin until the analyzer is active, its initial scan
is complete, every public or cross-account finding is explained, alarms and
application health are unchanged, and a separate completion record is
accepted.

## External references

- AWS IAM Access Analyzer pricing:
  https://aws.amazon.com/iam/access-analyzer/pricing/
- AWS CloudFormation `AWS::AccessAnalyzer::Analyzer` reference:
  https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-accessanalyzer-analyzer.html
