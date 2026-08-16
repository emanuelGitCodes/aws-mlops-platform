---
version: 1
slug: "website-frontend-src-app-tsx"
primary_target: "website/frontend/src/App.tsx"
related_targets: ["website/frontend/src/components/ArchitectureMap.tsx","website/frontend/src/components/useNodeBoxes.ts","website/frontend/src/components/PredictForm.tsx","website/frontend/src/components/SiteHeader.tsx","website/frontend/src/components/SiteFooter.tsx","website/frontend/src/profile.ts"]
---

# Frontend surface brief

## Scope

- Target: `website/frontend/src/App.tsx`
- Mode: Experience
- Audience: Engineering interviewers and hiring managers assessing the engineer
  through the system he built.
- Job: Say whose work this is, explain the platform architecture and its
  evidence, then offer the model demo.
- Primary actions: Trace the architecture, open the GitHub source, and reach
  the engineer.
- Secondary action: Score one customer.

## Product truth

- The platform uses AWS CDK, SageMaker Pipelines, serverless inference, and a
  drift-to-retrain loop.
- The model is a simple Telco churn model. The engineering system is the
  deliverable.
- The frontend MUST preserve the current schema, results, and prediction API
  flows. The subscription route stays intact and the page no longer calls it.
- Evidence labels are stage-specific proof lenses. They MUST NOT imply that
  every part has the same proof level.
- The page targets MLOps and ML platform, cloud and platform engineering, and
  data and ML engineering roles at once, so AWS service names belong on the
  diagram and not only in body copy.
- The current GitHub repository remains the source link.
- This task is local-only. It MUST NOT deploy the website stack or create AWS
  resources.

## Approved direction

- Name: Layered Trace Ledger
- Approved comp: `.impeccable/mocks/phosphor-layouts/option-3.webp`
- World: Near-black CRT glass with vivid phosphor green and restrained
  afterimages. A page-wide scanline carries the material past the hero shell.
- First viewport: A status line naming the engineer, then one continuous
  arrowed lifecycle schematic with an evidence rail on the right and a trace
  ledger below it. Three terminal keys close the frame above the fold.
- Visitor path: Learn whose work this is, read the lifecycle, inspect proof
  boundaries, open the source, and MAY score a customer at the end.
- Signature moment: A luminous cursor runs from the active stage to its
  selected proof lens and lands on a lit node on the rail.
- Motion: One stage-to-proof signal. Reduced-motion users receive static paths.
- Memorable detail: The cursor connects architecture to proof instead of
  turning proof into badges.

## Durable rules this surface established

- **Identity is content.** `src/profile.ts` is the one source of the name,
  role, and contact links. An empty value renders nothing rather than a dead
  link, and `missingLinks()` names the empty ones in development only.
- **The first viewport MUST end above the fold at 1280x720 and taller.** A
  `max-height: 810px` block tightens the hero for short laptop viewports.
- **Routes MUST be drawn from measured element boxes.** `useNodeBoxes.ts` reads
  real geometry, so connectors touch their nodes at every width and one set of
  path builders serves both the desktop row and the stacked mobile column. Each
  ref callback MUST keep one identity per key, or the measurement loop never
  settles.
- **The mobile page MUST carry the architecture.** Hiding the routes below a
  breakpoint removes the surface's whole argument.
- **Nothing on the page may imply a measurement the platform does not take.**
  The ledger renders the real AWS component chain; a decorative track that
  looks like instrumentation is a defect.
- **The form MUST open on a real record.** `/api/schema` publishes `examples`
  and `numeric_bounds`, both derived from the shared contract, so the frontend
  seeds and bounds its inputs without restating a feature or a range.
- **A cold inference endpoint MUST read as a cost decision, not a fault.** The
  warm fault pair is reserved for a real failure.
- **Body text and data keep the system monospace stack**, per DESIGN.md's Two
  Voice Rule. Only the display voice is self-hosted.
- **Corner brackets use two opposing corners.** The comp's four are decorative
  past that point, and the brief forbids copying marks that add no information.
  The two that remain brighten with selection, so the device carries state.

The comp is a north star, not a bitmap specification. The implementation MUST
keep real text, controls, focus states, and responsive reading order. It MUST
NOT invent metrics, timestamps, commands, or universal completion claims.

## Component grammar

- Corners: 0 to 4px on structural frames. Small controls MAY use 2px corners.
- Lines: 1px dim-green rules; 1.5px routes with arrowheads and edge ports; one
  brighter cursor line.
- Elevation: No floating cards. The CRT shell uses one soft outer shadow and an
  inset edge.
- Type: Self-hosted VT323 supplies the bitmap display voice. System monospace
  carries body and data. Nothing meaningful renders below about 11.5px.
- Spacing: Dense inside the schematic. Major page sections use generous
  vertical separation.
- Controls: Rectangular terminal keys with explicit hover, focus, loading,
  disabled, error, and selected states.

## Unresolved decisions

- `PROFILE.linkedin` and `PROFILE.resume` are empty, and `PROFILE.email` holds
  a personal address. The owner MUST set all three before the site is public.
- The local API data determines the exact evaluation and schema content at
  runtime.
