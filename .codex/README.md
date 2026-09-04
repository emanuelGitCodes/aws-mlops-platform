# Project agents

The project defines eleven roles under `.codex/agents/` and matching Claude
roles under `.claude/agents/`. These are repository-local definitions.
Use them from the checkout containing these files.

| Role | Assign it when the task concerns |
|---|---|
| `tech-lead` | Decomposition, shared interfaces, dependencies, and delivery order |
| `cdk-infra` | CDK resources, IAM, configuration, encryption, and stack dependencies |
| `devops` | CI, dependencies, operational scripts, hooks, and agent configuration |
| `lambda-backend` | Ingestion, inference, deployment, drift, and retrain handlers |
| `ml-pipeline` | Training, evaluation, data lineage, features, and promotion criteria |
| `frontend` | Local React UI, accessibility, browser security, and visual verification |
| `website-backend` | Local FastAPI routes, storage access, API security, and resilience |
| `test-engineer` | Behavioral tests, failure injection, fixtures, and regression proof |
| `security-reviewer` | Read-only review of trust, permission, data, and release boundaries |
| `deploy-operator` | Authorized AWS operations, live evidence, rollback, and observation |
| `wiki-scribe` | Evidence-backed decisions, status records, and review prose |

## Assign a task

A useful assignment states the goal, owned paths, acceptance criteria, and
permitted operations. For example:

> Use the ml-pipeline agent to inspect baseline ownership. Read the current
> pipeline and wiki first. Return the failure path and a bounded implementation
> plan. Do not edit files or start a training run.

For implementation, explicitly release the intended work item and name the
behavior that proves completion. Use `tech-lead` only when decomposition or
coordination adds value. Each worker follows the
[shared contract](agent-contract.md).

Start a Claude supervisor from the repository root:

```bash
claude --agent devops
```

Claude domain supervisors invoke the matching Codex writer through the
[supervision workflow](../.claude/agent-workflow.md). The workflow uses stdin
task files and explicit session IDs. A nested Claude tech lead returns its
assignments to its parent instead of trying to spawn more subagents.

## Limits

- Existing sessions can retain previously loaded definitions. Start a fresh
  session in this checkout after changes; reload Claude agents where supported.
- These files do not install global agents or update another checkout.
- Models follow the user's selection. No role forces a model or reasoning level.
- The Codex security reviewer uses a read-only sandbox. Other roles inherit
  host controls. Tool access and written instructions are different boundaries.
- Agent expertise does not authorize deployment, billing changes, publication,
  permission changes, or work outside the assignment.
- The website remains local-first and on hold for AWS deployment.

See the [decision record](../wiki/pages/decisions/agent-instruction-architecture.md)
for the relationship between roles, skills, hooks, and verification.
