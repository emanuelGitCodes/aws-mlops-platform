# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The primary visitor is a technical interviewer or hiring manager who evaluates
the project during a job application.

## Product Purpose

The website presents the engineering architecture of an AWS MLOps reference
platform. It helps a visitor understand the system before they use its churn
prediction demo.

Success means that the visitor can identify the platform boundaries, follow the
model lifecycle, inspect the engineering evidence, and then test the model.

## Positioning

The infrastructure is the deliverable. The website exposes the full path from
data ingestion and model evaluation to secured inference, drift detection, and
retraining. The churn model stays simple so the engineering decisions remain
the focus.

## Operating Context

The website is a portfolio artifact. A visitor may arrive from a resume, a job
application, or an interview discussion. The visitor needs a fast architecture
overview and a direct path to deeper evidence in the GitHub repository.

The application runs locally before any AWS website deployment. The local setup
uses a React and TypeScript frontend, a FastAPI backend, DynamoDB Local, and
MinIO.

## Capabilities and Constraints

- The architecture view is the primary experience.
- The prediction demo is a secondary interactive proof.
- The frontend reads the model schema at run time.
- The frontend shows the latest evaluation report when one is available.
- The frontend keeps the existing email subscription flow.
- The website links to the current GitHub repository.
- The frontend MUST NOT restate the feature or schema contract.
- The redesign MUST preserve the current API behavior.
- The website stack MUST remain undeployed during the local-first rebuild.

## Brand Commitments

The product uses the name "AWS MLOps Reference Platform." The voice is direct,
technical, and evidence-based. The website does not use unsupported deployment,
performance, or production claims.

## Evidence on Hand

- `README.md` contains the logical architecture and engineering decisions.
- `diagrams/cdk-platform-dev.svg` contains the synthesized platform view.
- `diagrams/cdk-security-cicd-dev.svg` contains the security and CI/CD view.
- `wiki/` records the decisions, implementation status, and evidence limits.
- `website/frontend/src/` contains the schema, evaluation, prediction, and
  subscription experiences.
- The source repository is
  `https://github.com/emanuelGitCodes/aws-mlops-platform`.
- No testimonials, employer endorsements, or commercial benchmarks exist. The
  website MUST NOT fabricate them.

## Product Principles

- Lead with system architecture, not the model.
- Use working behavior as proof.
- Distinguish designed, deployed, and observed states.
- Let a visitor move from overview to source evidence without friction.
- Keep every claim specific and verifiable.

## Accessibility & Inclusion

The website MUST support keyboard navigation, visible focus, reduced motion,
semantic landmarks, and readable contrast on desktop and mobile screens.
