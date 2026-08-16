---
name: "AWS MLOps Reference Platform"
description: "A phosphor trace ledger for inspectable MLOps architecture and evidence."
colors:
  phosphor: "#8dff4d"
  bright: "#d3ffb9"
  dim: "#5ca83c"
  faint: "#264a20"
  ink: "#020603"
  panel: "#061007"
  panel-strong: "#09180b"
  field: "#030904"
  action-active: "#0a1c0c"
  text: "#bafc8c"
  text-muted: "#9cd087"
  text-quiet: "#83c66b"
  text-faint: "#6d9f5c"
  danger: "#ffb4a8"
  danger-line: "#b44136"
  wash-hover: "rgba(141, 255, 77, 0.07)"
  wash-active: "rgba(141, 255, 77, 0.11)"
  bloom-shell: "rgba(141, 255, 77, 0.09)"
  bloom-inset: "rgba(141, 255, 77, 0.07)"
  bloom-cursor: "rgba(141, 255, 77, 0.9)"
  bloom-route: "rgba(141, 255, 77, 0.7)"
  shadow-ambient: "rgba(0, 0, 0, 0.72)"
  shadow-control: "rgba(0, 0, 0, 0.36)"
  rule-soft: "rgba(38, 74, 32, 0.72)"
typography:
  display:
    fontFamily: "VT323, ui-monospace, monospace"
    fontSize: "clamp(2.8rem, 5vw, 4.75rem)"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "-0.03em"
  headline:
    fontFamily: "VT323, ui-monospace, monospace"
    fontSize: "clamp(1.9rem, 2.9vw, 2.7rem)"
    fontWeight: 400
    lineHeight: 0.92
    letterSpacing: "0.03em"
  headline-compact:
    fontFamily: "VT323, ui-monospace, monospace"
    fontSize: "clamp(1.7rem, 2.4vw, 2.2rem)"
    fontWeight: 400
    lineHeight: 0.92
    letterSpacing: "0.03em"
  metric:
    fontFamily: "VT323, ui-monospace, monospace"
    fontSize: "3.2rem"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "normal"
  subhead:
    fontFamily: "VT323, ui-monospace, monospace"
    fontSize: "1.9rem"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "0.04em"
  masthead:
    fontFamily: "VT323, ui-monospace, monospace"
    fontSize: "1.5rem"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "0.06em"
  title:
    fontFamily: "VT323, ui-monospace, monospace"
    fontSize: "1.35rem"
    fontWeight: 400
    lineHeight: 1.1
    letterSpacing: "0.08em"
  label:
    fontFamily: "VT323, ui-monospace, monospace"
    fontSize: "1.25rem"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "0.09em"
  node:
    fontFamily: "VT323, ui-monospace, monospace"
    fontSize: "1.2rem"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "0.07em"
  control:
    fontFamily: "VT323, ui-monospace, monospace"
    fontSize: "1.15rem"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "0.08em"
  lead:
    fontFamily: "SFMono-Regular, Cascadia Code, Liberation Mono, ui-monospace, monospace"
    fontSize: "0.92rem"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  body:
    fontFamily: "SFMono-Regular, Cascadia Code, Liberation Mono, ui-monospace, monospace"
    fontSize: "0.88rem"
    fontWeight: 400
    lineHeight: 1.7
    letterSpacing: "normal"
  data:
    fontFamily: "SFMono-Regular, Cascadia Code, Liberation Mono, ui-monospace, monospace"
    fontSize: "0.82rem"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  detail:
    fontFamily: "SFMono-Regular, Cascadia Code, Liberation Mono, ui-monospace, monospace"
    fontSize: "0.78rem"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  meta:
    fontFamily: "SFMono-Regular, Cascadia Code, Liberation Mono, ui-monospace, monospace"
    fontSize: "0.74rem"
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: "0.08em"
  micro:
    fontFamily: "SFMono-Regular, Cascadia Code, Liberation Mono, ui-monospace, monospace"
    fontSize: "0.72rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "0.08em"
rounded:
  none: "0"
  hair: "1px"
  control: "2px"
  console: "3px"
  shell-compact: "1rem"
  shell: "1.5rem"
  ring: "50%"
spacing:
  hair: "0.25rem"
  tight: "0.35rem"
  xs: "0.5rem"
  sm: "0.75rem"
  md: "1rem"
  lg: "1.25rem"
  xl: "1.5rem"
  2xl: "2rem"
  3xl: "2.5rem"
  field: "clamp(0.9rem, 1.6vw, 1.5rem)"
  shell: "clamp(1rem, 1.8vw, 1.75rem)"
  section: "clamp(3.5rem, 6vw, 6rem)"
components:
  terminal-key:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.phosphor}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "0.55rem 1rem"
    height: "2.7rem"
  terminal-key-primary:
    backgroundColor: "{colors.action-active}"
    textColor: "{colors.bright}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "0.55rem 1rem"
    height: "2.7rem"
  submit-command:
    backgroundColor: "{colors.phosphor}"
    textColor: "{colors.ink}"
    typography: "{typography.node}"
    rounded: "{rounded.hair}"
    padding: "0.6rem 1rem"
    height: "2.9rem"
    width: "13rem"
  submit-command-hover:
    backgroundColor: "{colors.bright}"
    textColor: "{colors.ink}"
    typography: "{typography.node}"
    rounded: "{rounded.hair}"
    padding: "0.6rem 1rem"
  text-field:
    backgroundColor: "{colors.field}"
    textColor: "{colors.bright}"
    typography: "{typography.data}"
    rounded: "{rounded.hair}"
    padding: "0.5rem 0.6rem"
    height: "2.5rem"
  stage-node:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.text}"
    typography: "{typography.node}"
    rounded: "{rounded.control}"
    padding: "0.6rem 0.4rem 0.55rem"
  stage-node-active:
    backgroundColor: "{colors.panel-strong}"
    textColor: "{colors.bright}"
    typography: "{typography.node}"
    rounded: "{rounded.control}"
    padding: "0.6rem 0.4rem 0.55rem"
  evidence-tab:
    backgroundColor: "transparent"
    textColor: "{colors.dim}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "1rem 0.85rem"
  evidence-tab-active:
    backgroundColor: "{colors.wash-active}"
    textColor: "{colors.bright}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "1rem 0.85rem"
  preset-key:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.text-quiet}"
    typography: "{typography.meta}"
    rounded: "{rounded.control}"
    padding: "0.35rem 0.7rem"
  trace-control:
    backgroundColor: "transparent"
    textColor: "{colors.dim}"
    typography: "{typography.control}"
    rounded: "{rounded.none}"
    padding: "0.38rem 0.35rem"
---

# Design System: AWS MLOps Reference Platform

## Overview

**Creative North Star: "Layered Trace Ledger"**

The page reads as one instrument, not as a document about an instrument. A
near-black field carries a single green signal family. A curved CRT shell holds
the lifecycle schematic, and the same material continues below the shell as a
page-wide scanline and a soft radial bloom. The visitor never crosses from a
themed hero into plain text on black.

Brightness carries the state. Structure sits at the faint step, dormant parts
at the dim step, active parts at the phosphor step, and the current selection
or readout at the bright step. Nothing changes hue to say it is selected. The
one exception is the warm fault pair, which appears only when something failed.

Density is deliberate. Inside the schematic the rhythm is tight, because the
argument is that the parts connect. Between page sections the rhythm is
generous, because each section is a separate claim. Routes are measured, not
approximated: connectors read real element geometry and land on ports at the
node edges.

**Key Characteristics:**

- One green signal family over near-black, with brightness as the state channel.
- A page-wide scanline and radial bloom that keep every section the same
  material.
- Measured routes with arrowheads and edge ports, drawn from real geometry.
- An evidence cursor that runs from the selected stage to its proof lens.
- Bitmap display type against a system monospace stack for body and data.
- Flat frames with hairline rules; depth belongs to the shell.

## Colors

One green signal family sits over near-black surfaces. The warm pair is the
only other hue on the page.

### Primary

- **Live Phosphor** (`colors.phosphor`): Marks active routes, live arrowheads,
  the caret, primary command fills, and selected borders.
- **Signal White** (`colors.bright`): Marks headings, focus outlines, the
  current selection, and every high-value readout.

### Secondary

- **Afterimage Green** (`colors.dim`): Draws dormant routes, resting control
  text, and the heavier section rules.
- **Trace Rule** (`colors.faint`): Draws frames, dividers, corner brackets, and
  structure that carries no state.
- **Soft Rule** (`colors.rule-soft`): Separates rows inside the trace ledger,
  where a full faint rule reads too hard.

### Tertiary

- **Fault Signal** (`colors.danger`): Marks error text and error keys.
- **Fault Rule** (`colors.danger-line`): Marks the border of a failed region.

### Neutral

- **Dossier Ink** (`colors.ink`): Forms the page field, and the text on a filled
  phosphor control.
- **Terminal Panel** (`colors.panel`): Fills nodes, form cells, tables, and
  quiet controls.
- **Active Panel** (`colors.panel-strong`): Lifts a hovered or selected node,
  and fills a sticky table head.
- **Field Black** (`colors.field`): Separates an input from the panel cell that
  holds it.
- **Action Black** (`colors.action-active`): Fills a hovered or primary terminal
  key.

### Text ramp

Four named steps, from the brightest body colour down to the quietest. Each
step names a reading priority, not a place on the page.

- **Body Phosphor** (`colors.text`): The inherited page colour, and table row
  keys.
- **Muted Phosphor** (`colors.text-muted`): Paragraphs inside panels, table
  cells, and the first-person band.
- **Quiet Phosphor** (`colors.text-quiet`): Standfirsts, navigation, captions,
  and secondary readout copy.
- **Faint Phosphor** (`colors.text-faint`): Field labels, unit names, service
  names under a node, and placeholder text.

### Wash and bloom

Six translucent tokens, all derived from the signal family, plus two black
shadows. They are surfaces and light, never text.

- **Hover Wash** (`colors.wash-hover`) and **Active Wash**
  (`colors.wash-active`): Fill a hovered or selected row, tab, or key. The hover
  wash also draws the page scanline.
- **Shell Bloom** (`colors.bloom-shell`): Glows inside the CRT shell edge and
  along the footer's top edge.
- **Inset Bloom** (`colors.bloom-inset`): Glows behind the page, the evidence
  workbench, the footer, and the prediction console.
- **Route Bloom** (`colors.bloom-route`) and **Cursor Bloom**
  (`colors.bloom-cursor`): Light a live route and the evidence cursor.

### Named Rules

**The Single Declaration Rule.** Every colour MUST be declared once in `:root`.
A literal colour anywhere else in the stylesheet is drift.

**The Brightness State Rule.** State MUST travel on brightness. Faint is
structure, dim is dormant, phosphor is active, and bright is the current
selection or readout.

**The Signal Rarity Rule.** Bright phosphor MUST identify a current action,
selection, focus target, or primary readout.

**The Fault Isolation Rule.** The warm fault pair MUST appear only in a real
failure.

**The Dormant Is Not A Fault Rule.** A part that is off by choice MUST read as
structure. It uses a dashed rule and the faint text step. A cold inference
endpoint and an unset profile link both use this state, not the fault pair.

## Typography

**Display Font:** VT323, self-hosted as WOFF2 from `/fonts/`, preloaded in the
document head, with `ui-monospace` and `monospace` as fallbacks.

**Body Font:** SFMono-Regular, with Cascadia Code, Liberation Mono,
`ui-monospace`, and `monospace` as fallbacks.

**Character:** VT323 supplies the bitmap terminal voice. The system monospace
stack keeps explanations, tables, forms, and results easy to read at small
sizes. The pairing is the whole type system; no third face exists.

### Hierarchy

The display voice runs over nine steps and the reading voice over six. Each
step below names its purpose.

- **Display** (400, `clamp(2.8rem, 5vw, 4.75rem)`, 1, `-0.03em`): Opens a major
  page section.
- **Headline** (400, `clamp(1.9rem, 2.9vw, 2.7rem)`, 0.92, `0.03em`): Names the
  platform inside the CRT shell.
- **Headline compact** (400, `clamp(1.7rem, 2.4vw, 2.2rem)`, 0.92, `0.03em`):
  Replaces the headline on a short viewport, so the hero still ends above the
  fold.
- **Metric** (400, `3.2rem`, 1, tabular): Carries one headline number.
- **Subhead** (400, `1.9rem`, 1, `0.04em`): Opens the footer contact block.
- **Masthead** (400, `1.5rem`, 1, `0.06em`): Carries the engineer's name in the
  header and in the footer. One size, so the two read as the same voice.
- **Title** (400, `1.35rem`, 1.1, `0.08em`): Names a story column or an evidence
  panel.
- **Label** (400, `1.25rem`, 1, `0.09em`): Marks terminal keys, readout keys,
  and evidence tab names, in uppercase.
- **Node** (400, `1.2rem`, 1, `0.07em`): Names an architecture stage and the
  submit command.
- **Control** (400, `1.15rem`, 1, `0.07em` to `0.09em`): Names a trace, a
  disclosure summary, and the skip link.
- **Lead** (400, `0.92rem`, 1.6): Carries a section standfirst. The first-person
  band runs one step warmer at `0.95rem` and 1.75.
- **Body** (400, `0.88rem`, 1.7): Carries paragraphs inside panels and story
  columns. Measure stays between 40ch and 70ch.
- **Data** (400, `0.82rem`, 1.6): Carries readouts, input values, and summaries.
- **Detail** (400, `0.78rem`, 1.6): Carries tables, proof copy, and trace
  detail.
- **Meta** (400, `0.74rem`, 1.45, `0.07em` to `0.09em`): Marks field labels,
  unit names, and uppercase keys.
- **Micro** (400, `0.72rem`): Carries the route line and code blocks. Nothing
  meaningful renders below this step.

### Named Rules

**The Two Voice Rule.** Display text and controls MUST use VT323. Body text and
data MUST use the system monospace stack. This rule is load-bearing: a reviewer
proposed one voice, and the build kept two.

**The Text Ramp Rule.** Reading text MUST take its colour from the four-step
text ramp. A new green for a new paragraph is drift.

**The Legibility Floor Rule.** Text MUST NOT render below about 11.5px. The
micro step is the floor.

## Layout

The page centres on `min(100% - clamp(2rem, 7vw, 8rem), 96rem)`. Every section
runs to that edge, so the gutter is the only place that holds the page off the
window: it opens to 4rem on each side on a wide screen and closes to 1rem on a
phone. The header, the main column, and the footer share that one measure.

The first viewport holds a named status line, then the CRT shell. Inside the
shell a continuous lifecycle schematic sits beside a narrow evidence rail
(`minmax(11rem, 13rem)`), with the trace ledger below the schematic in the same
frame. Three terminal keys close the frame. Six stages sit on one row; the
retrain node sits on a second row in the second column.

Below the shell, sections separate with `clamp(3.5rem, 6vw, 6rem)` of vertical
padding and a dashed rule. Section headings pair a wide display column with a
`minmax(20rem, 0.9fr)` standfirst. The story band uses four columns, the
evidence workbench two, the input grid four.

Shipped breakpoints, in order: 1180px folds the heading and the story band, and
the input grid drops to three columns. 1000px moves the evidence rail below the
schematic and stacks the workbench. 820px wraps the header, and the terminal
keys, the console actions, and the footer go to one column. 760px stacks the
stages into one column, keeps the routes drawn, and reduces the input grid to
two columns. 460px gives the input grid, the contact rows, and the header nav
one column.

Two height queries compact the hero. At `min-width: 761px` and
`max-height: 810px` the padding, the node size, and the heading step all
tighten, so the first frame ends above the fold on a short laptop screen. A
second query at `max-height: 745px` tightens the outer padding again. Nothing
is removed at either step.

### Named Rules

**The Above The Fold Rule.** The first viewport MUST end above the fold at
1280x720 and taller. Short viewports MUST tighten the hero rather than drop a
part of it.

**The Mobile Carries The Architecture Rule.** The stacked layout MUST keep the
routes drawn. Hiding them removes the page's whole argument.

## Elevation & Depth

The model is a hybrid, and the light is emissive rather than cast. The page
itself carries an inset bloom and a full-height scanline behind the content. The
CRT shell owns the one real ambient shadow and an inner bloom. The prediction
console repeats that pair at a lower strength. Every other frame stays flat and
separates with a hairline rule. Interaction MAY add one small control shadow and
an inner wash, never a lift.

### Shadow Vocabulary

- **Page bloom** (`box-shadow: inset 0 0 12rem var(--bloom-inset)`): Lights the
  page field from its own edges.
- **Shell ambient** (`box-shadow: 0 18px 55px var(--shadow-ambient)`): Separates
  the CRT shell from the field.
- **Shell inner bloom** (`box-shadow: inset 0 0 4.5rem var(--bloom-shell)`, with
  a `1.25rem` edge repeat): Lights the inside of the shell.
- **Console depth** (`box-shadow: 0 18px 38px var(--shadow-ambient), inset 0 0
  3.5rem var(--bloom-inset)`): Sets the prediction console apart from the page.
- **Control press** (`box-shadow: 0 6px 16px var(--shadow-control), inset 0 0
  1.1rem var(--wash-hover)`): Marks an active node or terminal key.
- **Route glow** (`filter: drop-shadow(0 0 4px var(--bloom-route))`): Lights a
  live route.
- **Cursor glow** (`filter: drop-shadow(0 0 7px var(--bloom-cursor))`): Lights
  the evidence pulse and its landing node.
- **Footer edge** (`box-shadow: 0 0 1.5rem 1px var(--bloom-shell)`): Closes the
  page on the same emissive edge it opened with.

### Named Rules

**The Shell Depth Rule.** The CRT shell MUST own the strongest ambient shadow.
Internal frames MUST use borders at rest.

**The Page Material Rule.** The scanline and the bloom MUST run the whole page.
A section that drops them becomes plain text on black and leaves the world.

## Shapes

Structural frames are square. Radius appears only where a part is a physical
control or a physical screen: `1px` on inputs and the filled command, `2px` on
stage nodes, terminal keys, and preset keys, `3px` on the prediction console.

The CRT shell is the one large radius: `1.5rem`, dropping to `1rem` below 760px.
It is the only curved thing on the page, and the curve is what makes the rest
read as content inside a screen.

The evidence rail's icon holder is a full circle (`50%`). Route ports are small
circles of radius 2.6. Arrowheads are solid triangles. Authored SVG uses square
caps and miter joins at 1.3 to 2.4 stroke width; routes are 1.5, and a live
route is 2.

Corner brackets mark a stage node and a terminal key. They use two opposing
corners, top-left and bottom-right, at `0.45rem` square. They rest at 0.55
opacity and reach full opacity on hover or selection.

### Named Rules

**The Two Corner Rule.** A corner bracket MUST use two opposing corners, and it
MUST brighten with state. Four corners add no information, and a bracket that
never changes is decoration.

**The Square By Default Rule.** A new frame MUST be square. Radius is reserved
for controls and for the shell.

## Components

### Buttons

- **Shape:** Terminal keys use `2px` corners. The filled command button uses
  `1px`.
- **Terminal key:** Panel fill, phosphor text, faint border, `2.7rem` minimum
  height, one inline SVG glyph beside an uppercase label.
- **Primary command:** A filled phosphor block with ink text, `13rem` minimum
  width, and `2.9rem` minimum height.
- **Hover / Focus:** A terminal key takes the phosphor border, the action fill,
  bright text, and the control press shadow. The filled command brightens and
  rises 1px. Focus draws a `2px` bright outline at `3px` offset.
- **Disabled:** Opacity drops to 0.55, the cursor becomes `progress`, and all
  movement stops.

### Inputs / Fields

- **Style:** Field black, a `1px` faint border, `1px` corners, bright text, a
  phosphor caret, and tabular numerals. Labels sit above in the faint text step.
- **Layout:** Cells rule themselves with borders. The grid MUST NOT use a
  coloured gap, because the feature count is not a multiple of the column count
  and the leftover cells would paint as filled tiles.
- **Focus:** Hover and focus both take the phosphor border and one `1px` active
  wash ring.
- **Error / Dormant:** A failed request uses the fault pair. A cold endpoint
  uses the dashed dormant row instead.

### Cards / Containers

- **Corner Style:** Square, except the console (`3px`) and the shell.
- **Background:** Panel for filled regions. Larger regions use a radial bloom
  over the page field rather than a fill.
- **Shadow Strategy:** Flat at rest. See Elevation & Depth.
- **Border:** One-pixel faint rules inside a region, dim rules between regions,
  dashed rules between page sections.
- **Internal Padding:** `clamp(0.9rem, 1.6vw, 1.5rem)` inside the schematic,
  `clamp(1.75rem, 3vw, 3rem)` inside an evidence panel.

### Navigation

The header is one baseline-aligned row: the engineer's name in the masthead
step, the role beside it, then section links in the quiet text step. The source
link keeps phosphor and carries an inline arrow glyph. Links underline on hover
and brighten. Below 820px the header wraps and the identity stacks.

A skip link sits above the page. It is hidden by transform and slides in on
focus.

### Architecture Stage

A stage is a semantic button holding one authored line icon, an uppercase name,
and the AWS service under it. It carries three visual states: resting, on the
selected trace (`is-trace-active`, dim border and phosphor text), and selected
(`is-active`, phosphor border, active panel, bright text, control press
shadow). Below 760px the node turns into an icon-beside-text row.

### Route Layer

Routes are an absolutely positioned SVG behind the nodes, drawn in the
container's own pixel space.

- Geometry comes from measured element boxes, so a connector touches its nodes
  at every width.
- Every segment ends in an arrowhead and leaves a 5px gap before the node.
- Every segment contributes port circles at the edges it joins.
- A route on the selected trace switches to phosphor at `2px` with the route
  glow.
- The stacked layout re-routes the retrain loop up a side lane instead of
  through the column.

**The Measured Route Rule.** A route MUST be drawn from measured geometry.
Percentage coordinates cannot land on a node whose grid gap and font metrics
change at runtime.

### Evidence Cursor

The signature moment. When a stage and a proof lens are both selected and the
rail sits beside the field, four marks draw at once: a blurred halo, a dashed
phosphor line, one bright pulse that runs the path over 900ms, and a lit node
with a glow where the path lands on the rail. The pulse settles to 0.4 opacity
and does not loop. When the rail stacks below the field, the cursor does not
draw, and the readout carries the pairing in text.

### Trace Ledger

Three rows, each a semantic button: pipeline, signed API, and drift. A row pairs
a display-step name and icon with the real AWS component chain. Each hop is a
bordered token, joined by a drawn rule and a small rotated arrow. Selecting a
row lights its stages and its routes; selecting a stage selects its row. Below
760px the chain scrolls sideways rather than wrapping, so it stays one readable
sequence.

**The Real Chain Rule.** The ledger MUST render the platform's real component
chain. A decorative track that looks like instrumentation is a defect.

### Evidence Rail

Three tabs, stacked as equal rows beside the schematic. A tab holds a circled
icon, an uppercase name, and a short focus line. The selected tab takes the
active wash, bright text, and a `3px` inset phosphor edge. Below 1000px the rail
becomes three columns under the schematic and the edge moves to the top; below
760px it stacks again and the edge returns to the left.

### Data Readouts

Tables, definition lists, and count blocks share one treatment: panel fill,
hairline faint rules, an uppercase faint key, and a bright tabular value. Table
heads stick to the top of a scrolling region and take the strong panel.

A rate readout adds a 2px track under the row. The track takes the faint step
and the fill takes phosphor, so the row reads as a number first and a length
second. The number MUST carry the value; the track repeats it and stays out of
the accessibility tree.

A count matrix drops the panel fill and keeps the hairline rules. The cells the
model called right take phosphor, and the rest stay at the muted step.

A verdict line pairs one display-voice word with a sentence of context. The word
takes phosphor when the gate passed and the fault signal when it stopped. This
is the one place a readout states an outcome instead of a value.

## Do's and Don'ts

### Do:

- **Do** declare every new colour once in `:root`, and reference it by
  variable.
- **Do** carry state on brightness: faint for structure, dim for dormant,
  phosphor for active, bright for the current selection.
- **Do** keep the two type voices: VT323 for display and controls, system
  monospace for body and data.
- **Do** draw a connector from measured element geometry, with an arrowhead and
  ports at both ends.
- **Do** keep the scanline and the bloom under every section, so the lower page
  stays the same material as the hero.
- **Do** give a part that is off by choice the dashed dormant treatment and an
  explanation of the cost decision.
- **Do** resolve every animation to a static path under
  `prefers-reduced-motion: reduce`.

### Don't:

- **Don't** write a literal colour value below the `:root` block.
- **Don't** use the warm fault pair for anything but a real failure.
- **Don't** round a structural frame. Radius belongs to controls and to the
  shell.
- **Don't** draw four corner brackets, and don't leave a bracket that never
  changes with state.
- **Don't** hide the routes at a small width. The stacked page still MUST carry
  the architecture.
- **Don't** show an active state with glow alone. A border, a route, or a label
  MUST carry it too.
- **Don't** place semantic evidence inside a raster image.
- **Don't** state a metric, a timestamp, or a completion claim the platform does
  not measure.
