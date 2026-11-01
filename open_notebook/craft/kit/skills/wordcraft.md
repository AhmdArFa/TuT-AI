---
name: wordcraft
description: Editable Word reports from the approved Noir Word masters, checked page by page with WordCraft.
---

# WordCraft skill

To create an editable Word report, call the `generate_document` tool with feature `report` and your detailed `instructions`.
The backend engine automatically:
1. Clones the approved Noir Word master (`MCIT-WSIS-Report-Noir-DARK.docx` or `-LIGHT.docx`).
2. Populates cover, table of contents, executive summary, chapters with figures, and findings.
3. Audits the document page-by-page with WordCraft.
4. Delivers the editable `.docx` and printable `.pdf` directly to the chat and Files library.
