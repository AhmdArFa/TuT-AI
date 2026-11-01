---
name: powerpoint
description: Build Midnight Noir decks. PptxGenJS constructs the pptx, DeckCraft renders every slide for the audit loop.
---

# Presentation skill

Call the `generate_document` tool with feature `presentation`. PptxGenJS and DeckCraft build and audit the deck on the backend and deliver the .pptx and .pdf.

- Layout 16:9 (13.33 x 7.5 in). One idea per slide, at most 6 body lines.
- Slide 1: full-bleed hero cover art, eyebrow top-left, Nohemi Bold title,
  Libre Franklin subtitle, logo on a white rounded card.
- Last slide: full-bleed end cover art, "Thank You" centred in Nohemi,
  MCIT line in Pale Gold.
- Content slides: solid Midnight (dark) or White (light). Never the cover art.
- Vary layouts: agenda, section opener, hero stat, chart, two column, findings,
  timeline, table. Never two identical layouts in a row.
- Charts are native charts in the palette with value labels and quiet axes.
- Banned: title underlines, edge stripes, gradients, gradient text, glass,
  glowing pills, generic icon grids, text-only walls.
- Audit: every slide is rendered; overflow, clipping, empty slides, repeated
  layouts and missing covers are issues to fix before delivery.
