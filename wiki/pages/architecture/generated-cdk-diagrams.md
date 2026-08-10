---
type: architecture
title: Generated CDK infrastructure diagrams
created: 2026-08-08
updated: 2026-08-09
sources: ["../../../infra/app.py", "../../../Makefile", "../../../scripts/prepare_cdk_diagrams.py", "../../../README.md", "https://github.com/pistazie/cdk-dia"]
summary: "Three generated views provide PNG previews, editable SVG files, and DOT sources for the synthesized dev resource graph."
---

# Generated CDK infrastructure diagrams

## Confirmed

`make diagrams ENV=dev` synthesizes the current CDK app and renders three
diagram sets with `cdk-dia` 0.12.3. Each set contains a PNG preview, an editable
SVG file, and a Graphviz DOT source. The dev assembly contains nine stacks.
The files show constructs and references from `infra/cdk.out/tree.json`.

### Complete CDK app

[![Complete synthesized dev CDK app](../../assets/architecture/cdk-full-dev.png)](../../assets/architecture/cdk-full-dev.png)

[Editable SVG](../../assets/architecture/cdk-full-dev.svg) ·
[Graphviz DOT source](../../assets/architecture/cdk-full-dev.dot)

### ML platform stacks

This view contains `Data`, `Ingestion`, `Registry`, `Training`, `Serving`, and
`Monitoring`.

[![Synthesized dev ML platform stacks](../../assets/architecture/cdk-platform-dev.png)](../../assets/architecture/cdk-platform-dev.png)

[Editable SVG](../../assets/architecture/cdk-platform-dev.svg) ·
[Graphviz DOT source](../../assets/architecture/cdk-platform-dev.dot)

### Security and CI/CD stacks

This view contains `Security`, `SecurityMonitoring`, and `Cicd`.

[![Synthesized dev security and CI/CD stacks](../../assets/architecture/cdk-security-cicd-dev.png)](../../assets/architecture/cdk-security-cicd-dev.png)

[Editable SVG](../../assets/architecture/cdk-security-cicd-dev.svg) ·
[Graphviz DOT source](../../assets/architecture/cdk-security-cicd-dev.dot)

## Synthesis

The complete view supports inventory and cross-stack reference review. The
focused views keep resource labels readable. The Mermaid diagram in the
[repository README](../../../README.md) describes the logical data, model,
serving, and drift flow.

The [resource and permission boundaries](permissions.md) page documents access
boundaries. The [phased security status board](phased-security-hardening.md)
documents deployment status.

## Tensions or open questions

- The images show synthesized desired state. They do not prove that AWS
  deployed a stack or changed a resource.
- The SDK upserts the SageMaker Pipeline after CDK deployment. The CDK tree
  does not contain the pipeline steps or promotion behavior.
- A construct reference shows an infrastructure dependency. It does not prove
  that a runtime event path was exercised.
- `cdk-dia` diagram decorators support TypeScript and JavaScript projects. This
  Python project generates the views with stack filters.
- The DOT source controls graph structure and automatic layout. A vector editor
  can change the SVG directly. A later `make diagrams` run replaces that edit.

## Regeneration

Install Graphviz once, then use the repository target:

```bash
brew install graphviz
make install
make diagrams ENV=dev
```

`DIAGRAM_DIR=/path/to/output` overrides the default
`wiki/assets/architecture` destination. `ENV=prod` produces the equivalent
prod design without deploying it.

Edit an SVG in a vector editor such as Figma or Inkscape. Edit a DOT file when
the change must preserve graph structure. After a DOT edit, rebuild its
self-contained SVG from the repository root:

```bash
uv run --locked python scripts/prepare_cdk_diagrams.py \
  wiki/assets/architecture/cdk-platform-dev.dot
```

The helper copies the required `cdk-dia` icons into `cdk-dia-icons`. It replaces
workstation paths in DOT files. It embeds each icon once in the SVG file.
