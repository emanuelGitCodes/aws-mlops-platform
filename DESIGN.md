---
name: "AWS MLOps Reference Platform"
description: "A phosphor trace ledger for inspectable MLOps architecture and evidence."
colors:
  phosphor: "#8dff4d"
  phosphor-bright: "#d3ffb9"
  phosphor-dim: "#5ca83c"
  phosphor-faint: "#264a20"
  ink: "#020603"
  panel: "#061007"
  panel-strong: "#09180b"
  field-background: "#030904"
  action-active: "#0a1c0c"
  body-copy: "#bafc8c"
  danger: "#ffb4a8"
  danger-line: "#b44136"
typography:
  display:
    fontFamily: "VT323, monospace"
    fontSize: "clamp(3.2rem, 6vw, 6rem)"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "-0.04em"
  headline:
    fontFamily: "VT323, monospace"
    fontSize: "clamp(2.2rem, 3vw, 3.35rem)"
    fontWeight: 400
    lineHeight: 0.95
    letterSpacing: "0.035em"
  title:
    fontFamily: "VT323, monospace"
    fontSize: "1.4rem"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "0.1em"
  body:
    fontFamily: "SFMono-Regular, Cascadia Code, Liberation Mono, monospace"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "normal"
  label:
    fontFamily: "VT323, monospace"
    fontSize: "1.2rem"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "0.1em"
  data:
    fontFamily: "SFMono-Regular, Cascadia Code, Liberation Mono, monospace"
    fontSize: "0.78rem"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "normal"
rounded:
  none: "0"
  field: "1px"
  control: "2px"
  shell-compact: "1rem"
  shell-wide: "2rem"
spacing:
  xs: "0.5rem"
  sm: "0.75rem"
  md: "1rem"
  lg: "1.5rem"
  xl: "2rem"
  section: "clamp(4rem, 7vw, 7rem)"
components:
  terminal-key:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.phosphor}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "0.75rem 1rem"
    height: "3.4rem"
  terminal-key-active:
    backgroundColor: "{colors.action-active}"
    textColor: "{colors.phosphor-bright}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "0.75rem 1rem"
    height: "3.4rem"
  command-button:
    backgroundColor: "{colors.phosphor}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.field}"
    padding: "0.65rem 1rem"
    height: "3rem"
  text-field:
    backgroundColor: "{colors.field-background}"
    textColor: "{colors.phosphor-bright}"
    typography: "{typography.data}"
    rounded: "{rounded.field}"
    padding: "0.55rem 0.65rem"
    height: "2.65rem"
  stage-node:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.body-copy}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "clamp(0.75rem, 1.4vw, 1.25rem) 0.4rem 0.65rem"
  evidence-tab:
    backgroundColor: "transparent"
    textColor: "{colors.phosphor-dim}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "1.25rem"
---

# Design System: AWS MLOps Reference Platform

## Overview

**Creative North Star: "Layered Trace Ledger"**

The system presents architecture as a near-black phosphor dossier. A curved
CRT shell contains exact routes, authored line icons, and evidence boundaries.

The visual voice stays technical, calm, and dense. Bright signals mark active
relationships. Dim rules preserve the structure without competing with content.

**Key Characteristics:**

- Near-black CRT glass with restrained scanlines and perimeter bloom.
- Phosphor linework that links architecture stages with evidence categories.
- Bitmap display type paired with readable system monospace text.
- Flat evidence frames with precise borders and controlled state depth.
- One routed trace pulse and one stage-to-proof signal, with static
  reduced-motion states.

## Colors

The palette uses one green signal family over near-black surfaces. Warm error
tones appear only when a process fails.

### Primary

- **Live Phosphor** (`colors.phosphor`): Marks active routes, primary commands,
  carets, and selected borders.
- **Signal White** (`colors.phosphor-bright`): Marks headings, focus outlines,
  active text, and high-value readouts.

### Neutral

- **Dossier Ink** (`colors.ink`): Forms the page field and command text on
  filled controls.
- **Terminal Panel** (`colors.panel`): Fills nodes, fields, tables, and quiet
  controls.
- **Active Panel** (`colors.panel-strong`): Adds a small tonal shift to active
  architecture nodes.
- **Field Black** (`colors.field-background`): Separates form fields from their
  panel cells.
- **Afterimage Green** (`colors.phosphor-dim`): Draws routes and secondary
  labels.
- **Trace Rule** (`colors.phosphor-faint`): Draws frames, dividers, and dormant
  linework.
- **Readable Phosphor** (`colors.body-copy`): Supplies the inherited text color.

### Tertiary

- **Fault Signal** (`colors.danger`): Marks error text.
- **Fault Rule** (`colors.danger-line`): Marks error boundaries.

### Named Rules

**The Signal Rarity Rule.** Bright phosphor MUST identify a current action,
selection, focus target, or primary readout.

**The Fault Isolation Rule.** Warm fault colors MUST appear only in error
states.

## Typography

**Display Font:** VT323 with a monospace fallback.

**Body Font:** SFMono-Regular with Cascadia Code, Liberation Mono, and monospace
fallbacks.

**Character:** VT323 supplies the bitmap display voice. System monospace keeps
descriptions, data, forms, and reports easy to read.

### Hierarchy

- **Display** (400, `clamp(3.2rem, 6vw, 6rem)`, 1): Leads major sections.
- **Headline** (400, `clamp(2.2rem, 3vw, 3.35rem)`, 0.95): Names the platform.
- **Title** (400, `1.4rem`, 1): Names evidence panels and system stories.
- **Body** (400, `1rem`, 1.55): Carries explanations and supporting copy.
- **Label** (400, `1.2rem`, `0.1em`): Marks controls and readout keys in
  uppercase.
- **Data** (400, `0.78rem`, 1.55): Carries tables, results, and form values.

### Named Rules

**The Two Voice Rule.** Display text and controls MUST use VT323. Body text and
data MUST use the system monospace stack.

## Layout

The page uses a centered container with a maximum width of 104.5rem. Major
sections use generous vertical spacing between dense technical regions.

The first viewport uses a continuous schematic beside a narrow evidence rail.
The trace ledger stays below the schematic inside the same framed system.

At 1100px, the evidence rail moves below the schematic. At 760px, the stages
form a two-column trace and the evidence categories stack. At 460px, stages and
fields use one column.

Wide forms use four columns. They move to three columns at 1100px, two columns
at 760px, and one column at 460px.

## Elevation & Depth

The system uses a hybrid depth model. The CRT shell has the strongest ambient
shadow and an inset glow. Internal frames stay flat until interaction.

### Shadow Vocabulary

- **CRT ambient** (`0 18px 55px rgba(0, 0, 0, 0.72)`): Separates the curved
  shell from the page field.
- **CRT inset** (`inset 0 0 4.5rem rgba(61, 186, 66, 0.1)`): Adds restrained
  phosphor bloom inside the shell.
- **Active control** (`0 8px 18px rgba(0, 0, 0, 0.36)`): Marks a hovered or
  selected interactive frame.
- **Cursor bloom** (`0 0 0.9rem rgba(141, 255, 77, 0.95)`): Locates the active
  evidence category.

### Named Rules

**The Shell Depth Rule.** The CRT shell MUST own the strongest ambient shadow.
Internal frames MUST use borders at rest.

## Shapes

Structural frames use square corners or very small corner radii. Fields use a
1px radius. Interactive nodes and terminal keys use a 2px radius.

The CRT shell is the deliberate exception. It uses a 2rem radius on wide
screens and a 1rem radius below 760px.

Authored SVG lines use square caps and miter joins. Small corner marks reinforce
the technical frame without replacing labels or state.

## Components

### Buttons

- **Shape:** Terminal keys use a precise 2px radius. Filled command buttons use
  a 1px radius.
- **Primary:** Command buttons use live phosphor over dossier ink with
  `0.65rem 1rem` padding.
- **Hover / Focus:** Hover changes the border or fill and MAY add one low
  shadow. Focus uses a 2px bright outline with a 4px offset.
- **Disabled:** Disabled controls reduce opacity to 0.55 and remove movement.

### Inputs / Fields

- **Style:** Fields use Field Black, a 1px Trace Rule border, and bright text.
- **Focus:** Hover and focus change the border to Live Phosphor. They add one
  1px outer signal line.
- **Error / Disabled:** Error messages use the fault pair. Pending actions use
  the shared disabled state.

### Cards / Containers

- **Corner Style:** Evidence frames stay square. Interactive nodes use 2px
  corners. The CRT shell uses the large shell radius.
- **Background:** Panels use Terminal Panel. Selected nodes use Active Panel.
- **Shadow Strategy:** Containers stay flat. Interaction MAY add the active
  control shadow.
- **Border:** One-pixel dim or faint green rules separate content regions.
- **Internal Padding:** Dense controls use 0.75rem to 1.25rem. Large evidence
  panels use responsive 2rem to 4rem spacing.

### Navigation

The three terminal keys close the first viewport. They use equal columns on
wide screens and one column below 760px.

The active key uses the brighter panel and border treatment. Every key keeps a
visible focus outline and an explicit text label.

### Architecture Stage

Each stage is a semantic button with one authored line icon and one uppercase
label. The active stage changes its border, panel tone, and text color.

Desktop stages follow one connected route. Mobile stages use a readable
vertical trace and keep the selected-stage readout.

### Evidence Cursor

The cursor links the selected stage to implemented, deployed, or observed
evidence. Each category acts as a proof lens for the selected stage. The
readout names the exact source, infrastructure boundary, or runtime signal.

Desktop uses an authored SVG route, one luminous rail marker, and one
stage-to-proof signal. The signal runs once after a stage or proof lens changes.

Mobile removes the routed overlay. A bright vertical rule couples the selected
stage readout with the stacked evidence rail. The proof readout stays visible.

### Trace Ledger

The ledger uses three semantic buttons for pipeline, signed API, and drift.
Each button pairs a bitmap label with a dashed route and two circular marks.

Selecting a trace highlights its stages, runs one route pulse, and names the
AWS component chain. Selecting a stage also selects its related trace. Native
button behavior provides keyboard access. Reduced motion keeps the selected
route visible without a loop.

## Do's and Don'ts

### Do:

- **Do:** New screens MUST preserve the two-voice type system.
- **Do:** Evidence relationships MUST use semantic HTML or authored SVG.
- **Do:** Responsive layouts MUST keep the content order readable without the
  desktop route overlay.
- **Do:** Motion MUST resolve to a static path when the visitor requests reduced
  motion.

### Don't:

- **Don't:** New screens MUST NOT place semantic evidence inside a raster image.
- **Don't:** Active states MUST NOT use glow without a border, route, or label.
- **Don't:** Sequential architecture MUST NOT become isolated tiles when the
  route relationship carries meaning.
- **Don't:** Error colors MUST NOT decorate neutral or successful states.
