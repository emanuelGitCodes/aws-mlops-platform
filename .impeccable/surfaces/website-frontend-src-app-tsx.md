---
version: 1
slug: "website-frontend-src-app-tsx"
primary_target: "website/frontend/src/App.tsx"
related_targets: ["website/frontend/src/components/ArchitectureMap.tsx","website/frontend/src/components/PredictForm.tsx","website/frontend/src/components/LatestEvaluation.tsx","website/frontend/src/components/SchemaTable.tsx","website/frontend/src/components/SubscribeForm.tsx"]
---

# Frontend surface brief

## Scope

- Target: `website/frontend/src/App.tsx`
- Mode: Experience
- Audience: Engineering interviewers who need to assess the system quickly.
- Job: Explain the platform architecture and its evidence before offering the model demo.
- Primary actions: Trace the architecture and open the GitHub source.
- Secondary action: Run the prediction demo.

## Product truth

- The platform uses AWS CDK, SageMaker Pipelines, serverless inference, and a drift-to-retrain loop.
- The model is a simple Telco churn model. The engineering system is the deliverable.
- The frontend MUST preserve the current schema, results, prediction, and subscription API flows.
- Evidence labels are stage-specific proof lenses. They MUST NOT imply that
  every part has the same proof level.
- The current GitHub repository remains the source link.
- This task is local-only. It MUST NOT deploy the website stack or create AWS resources.

## Approved direction

- Name: Layered Trace Ledger
- Approved comp: `.impeccable/mocks/phosphor-layouts/option-3.webp`
- World: Near-black CRT glass with vivid phosphor green and restrained afterimages.
- First viewport: One continuous lifecycle schematic on the left, a three-line trace ledger below, and an evidence rail on the right.
- Visitor path: Read the lifecycle, inspect proof boundaries, open source, then try the prediction demo.
- Signature moment: A luminous signal travels from the active architecture
  stage to its selected proof lens and resolves an exact proof readout.
- Motion: One slow trace pulse follows the route. One short signal connects a
  selected stage to its proof lens. Reduced-motion users receive static paths.
- Memorable detail: The evidence cursor connects architecture to proof instead of turning proof into badges.

The comp is a north star, not a bitmap specification. The implementation MUST keep real text, controls, focus states, and responsive reading order. It MUST NOT copy the comp's decorative corner marks where they add no information. It MUST NOT invent metrics, timestamps, commands, or universal completion claims.

## Component grammar

- Corners: 0 to 4px on structural frames. Small controls MAY use 2px corners.
- Lines: 1px dim-green rules; 2px active routes; one brighter cursor line.
- Elevation: No floating cards. The CRT shell uses one soft outer shadow and an inset edge.
- Type: Self-hosted VT323 supplies the narrow bitmap display voice. Readable system monospace remains for body and data. Headings are uppercase with open tracking. Body copy stays sentence case.
- Spacing: Dense inside the schematic. Major page sections use generous vertical separation.
- Controls: Rectangular terminal keys with explicit hover, focus, loading, disabled, error, and selected states.

## Fidelity inventory

| Comp ingredient | Commitment | Medium |
| --- | --- | --- |
| CRT shell and scan texture | A visible curved-glass, scanline, bloom, and afterimage field covers the first viewport | Generated 16:9 raster field plus CSS shell |
| Lifecycle topology | Ingest to train to evaluate to register to serve to monitor, with retrain loop | Semantic HTML and authored SVG routes |
| Architecture nodes | Six equal stages and one subordinate retrain stage | Semantic buttons with authored SVG icons |
| Evidence cursor | A routed line and one-shot signal couple the active stage with the selected proof lens | Authored SVG on desktop; luminous coupled readout on mobile |
| Display type | Narrow bitmap terminal lettering across headings and controls | Self-hosted VT323 from Google Fonts |
| Evidence rail | Implemented, deployed, and observed resolve the selected stage to a source, infrastructure boundary, or runtime signal | Semantic buttons and a stage-specific proof readout |
| Trace ledger | Pipeline, signed API, and drift select exact stages and name the AWS component chain; no invented metrics | Semantic button list, authored SVG route marks, and an accessible live readout |
| Header | Compact project title, architecture-led description | Semantic HTML |
| Primary action | Open the current GitHub source | Semantic anchor with authored SVG icon |
| Secondary action | Scroll to the prediction demo | Semantic anchor with authored SVG icon |
| Evaluation, schema, prediction, subscription | Preserve all existing data and action states | Existing React components, extended in place |
| Responsive form | Rail stacks after the schematic; stages become a readable vertical trace | CSS media queries and semantic order |

## Unresolved decisions

- The local API data determines the exact evaluation and schema content at runtime.
