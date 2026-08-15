# Media manifest

| Output | Dimensions | Format | Transparency | Crop and use |
| --- | --- | --- | --- | --- |
| `website/frontend/src/assets/crt-hero-field.webp` | 1672 x 941 px | WebP | Opaque | Native 16:9 output with no crop. Use it as the first-viewport CRT material field behind semantic HTML and SVG. A cover fit MAY trim only the outer bloom on narrow screens. Keep the quiet center aligned with the lifecycle linework. |
| `website/frontend/src/assets/fonts/VT323-Regular.ttf` | 149 KB | TrueType font | Not applicable | Self-host the narrow bitmap display voice. Use it for headings, stage labels, and controls. |

## Provenance

The built-in image-generation tool produced the field from the approved
`.impeccable/mocks/phosphor-layouts/option-3.webp` comp as a material reference.
The generator returned a native 1672 x 941 px PNG. `cwebp` converted it to
WebP at quality 95 with sharp YUV conversion. The exact generation prompt is
stored in `website/frontend/src/assets/crt-hero-field.webp.json`.

Fine scanlines cover the full frame. The bloom stays in the outer 12 percent.
Sparse afterimages cross less than 5 percent of the field. The central 60
percent remains dark and low contrast.

## Semantic-code boundary

The raster contains only curved CRT glass, scanlines, perimeter bloom,
micrograin, and faint non-semantic horizontal afterimages. The lifecycle
topology, nodes, routes, evidence cursor, evidence rail, trace ledger, text,
icons, controls, focus states, and interactions MUST remain semantic HTML,
CSS, or authored SVG. The asset MUST NOT replace UI content or encode product
evidence.

## Font source

Google Fonts supplies `VT323-Regular.ttf` under the SIL Open Font License 1.1.
The matching license is stored at
`website/frontend/src/assets/fonts/OFL.txt`. Body copy stays in the readable
system monospace stack; VT323 owns the display voice only.
