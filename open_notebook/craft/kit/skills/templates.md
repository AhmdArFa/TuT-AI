---
name: templates
description: The master template system. Read before any document task: pick the approved template, edit a copy for the request, audit it with the engine, deliver.
---

# Templates (master skill)

To generate any document, call the `generate_document` tool with `feature` ('presentation', 'report', 'spreadsheet', or 'infograph') and your `instructions`.

The backend engine automatically executes the complete generation process:
1. Picks the approved template for the requested feature and theme.
2. Clones the template safely on the backend.
3. Generates all slides, sections, data tables, or charts according to your instructions.
4. Audits the document with DeckCraft, WordCraft, GridCraft, or VectorCraft.
5. Saves the resulting file to the user's Files & Docs library and provides ONLYOFFICE preview and download links.

Deliver the returned file links directly to the user in chat.

| Feature | Default template | Engines | Outputs |
|---|---|---|---|
| Presentation | Noir briefing deck (dark or light) | PptxGenJS, DeckCraft | pptx, pdf |
| Report | Noir report: cover, contents, at a glance, chapters with figures, findings, back cover | ReportLab, PdfCraft, WordCraft | pdf, docx |
| Infograph | Sketchnote: speech-bubble title, two columns, doodles, verdict box | VectorCraft, Open Doodles | png, pdf, svg |
| Spreadsheet | Noir monthly report: input columns, formula columns, totals, chart | GridCraft | xlsx |

Covers are constant: hero art on the first slide or page, end art on the last. The
gold ornament lives on the covers only. The logo sits on a white card.

Theme: Midnight Noir. Midnight #010612, Abyss #030F1F, Royal #1E507A, Pulse #16A6E9,
Pale Gold #F7EF8A, White, Silver #B9C2CE. Nohemi headings, Libre Franklin body,
Inter on covers. One accent per page. No gradients, glows, glass or decorative shapes.
No em or en dashes in copy. No source-credit lines.
