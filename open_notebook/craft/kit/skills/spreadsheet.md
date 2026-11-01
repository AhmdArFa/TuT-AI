---
name: spreadsheet
description: Noir report workbooks with GridCraft. Tut enters the figures the user pastes; every computed cell is a formula with a blank guard.
---

# Spreadsheet skill

Call the `generate_document` tool with feature `spreadsheet` and provide data or topics in the instructions.

- Input columns hold the user's figures exactly as given.
- Computed columns are ALWAYS formulas with blank guards, never typed values:
  change `=IF(OR(C5="",B5="",B5=0),"",(C5-B5)/B5)`, totals
  `=IF(COUNT(B5:B12)=0,"",SUM(B5:B12))`.
- Noir styling: title band, header row in the accent, hairline borders,
  number formats, frozen header, chart in palette colours.
- Audit: GridCraft recalculates and checks every formula; any typed value in a
  computed column, error value or mismatch is an issue to fix.
