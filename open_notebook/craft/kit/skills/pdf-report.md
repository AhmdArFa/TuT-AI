---
name: pdf-report
description: Build the Noir report as a print PDF (ReportLab, figures with real data, PdfCraft) with a matching editable Word file.
---

# Report skill

Call the `generate_document` tool with feature `report` and optional length ('short', 'medium', 'long').

Structure (kept for every report): cover with hero art, contents, at a glance
(key figures), chapters, findings and recommendations, back cover with end art.

| Length | Depth |
|---|---|
| Short | 3 chapters, 1 figure, about 6 to 8 pages |
| Medium | 5 chapters, 2 to 3 figures, about 10 to 14 pages |
| Long | 8 chapters, a figure per data-bearing chapter, sub-sections, about 18 to 26 pages |

- A4 portrait, 22 mm margins, running header on content pages, page numbers.
- Every figure carries real data from the notebook. No placeholder numbers.
- Dark and light share structure; only the surfaces flip. The cover art never changes.
- Audit: every page is rendered and checked for overflow, empty pages, missing
  figures and contents page numbers.
