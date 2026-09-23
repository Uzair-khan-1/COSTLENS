# Detailed Material Schedule (Master Material Database)

This feature adds a **complete, material-by-material take-off** to Step 5.
It is additive: the existing Steps 1-5, the MTO/BOQ Excel and the PDF
report are unchanged. The panel appears under the existing export buttons
as **"Detailed Material Schedule (every material)"** with its own download.

## How it works

```
Drawings (vector PDF) ──► package_analyzer (existing)  ─┐
                     └──► detailed_mto/text_scanner    ─┤
Step 3 verified parameters ─────────────────────────────┤
Room_Finish_Defaults (knowledge base) ──────────────────┘
                              │
                              ▼
            detailed_mto/builder.py  → DetailedProject (every input with source + confidence)
                              │
                              ▼
     detailed_mto/quantities.py (101 work items)   +   Recipes (coefficients) from the Excel DB
                              │
                              ▼
            detailed_mto/engine.py → all 309 materials, each with a status
                              │
                              ▼
            detailed_mto/export.py → Excel workbook (10 sheets, live formulas, blank rates)
```

**Material quantity = Σ (work-item quantity × recipe coefficient) × (1 + wastage).**
Materials that are counts, lump sums or stand-alone areas use
`detailed_mto/direct.py`.

### What is read from the drawings (no AI)

| Source | Facts |
|---|---|
| `package_analyzer` (existing) | rooms with sizes per floor, wall lengths by thickness (9" / 4.5"), footprint and perimeter, levels (plinth, floor height, slab), strip foundation width and depth, column sizes, door/window totals, area statement, plot size, drawing conflicts |
| `text_scanner` (new) | plumbing labels on plumbing sheets (F.T, M.H, G.T, C.O, VANITY, CONCEALED WC, SHOWER AREA, SUMP), door/chogath schedule rows (size, chogath width, single/double, qty), overhead tank capacity, septic / UG / OH tank sizes, WARDROBE / BALCONY / TERRACE / DB labels |

Everything else (electrical point counts, finishes, window widths when not
given) comes from `Room_Finish_Defaults` and is marked **Assumed** so the user
can correct it in the review tables.

### Status of every line

| Status | Meaning |
|---|---|
| Calculated | from drawing / verified inputs |
| Calculated (assumed inputs) | at least one input is a default - verify |
| Provisional | owner-supplied / PC items (e.g. split AC units, decorative lights) |
| Counted elsewhere (reference) | assembly or duplicate line, quantity shown for information only |
| Option - not included | optional/alternative material; "If-selected Qty" shows what it would be |
| Needs input | cannot be calculated without a user value |
| Not required / Not in scope | zero for this project / outside selected scope |

## Editing the knowledge base

`data/master_material_database.xlsx` is the single source of truth. Edit
coefficients (blue cells), wastage, mixes, room defaults or add materials
in Excel, save, then run:

```
python scripts/validate_knowledge_base.py
```

The loader evaluates the workbook's own formulas in Python (it does not rely
on cached Excel values), so edits take effect on the next app run. Keep
`Mat_ID`, `WI_ID` and `Coeff_ID` values stable - they are the keys.

To add a new work item: add it to `Work_Items`, add its recipe lines in
`Recipes`, and add a calculator function decorated with `@wi("WI-XX-NN")`
in `detailed_mto/quantities.py`.

## Accuracy notes

* Areas, finishes, doors, plumbing fixtures: close to measured (±2-10%) on
  vector CAD PDFs.
* Masonry / plaster: ±5-10% (wall-pair detection).
* Steel: ratio method (±15-30%) until a structural BBS is provided.
* Electrical wiring/conduit, pipe lengths: per-point allowances (±15-25%).
* Scanned drawings give no vector facts; the schedule then relies on Step 3
  values and defaults (flagged as assumed).

The Benchmarks sheet flags cement, steel, bricks, sand and crush ratios per
sft that fall outside typical ranges.

## Files added

```
data/master_material_database.xlsx   knowledge base (21 sheets)
knowledge/loader.py                  Excel loader + formula evaluator + integrity checks
detailed_mto/model.py                project model with provenance
detailed_mto/text_scanner.py         extra text-layer extraction
detailed_mto/builder.py              app state + drawing facts → project model
detailed_mto/quantities.py           101 work-item calculators
detailed_mto/direct.py               non-recipe material calculators
detailed_mto/engine.py               roll-up, statuses, scope/options
detailed_mto/edits.py                apply review-table edits
detailed_mto/export.py               Excel export
ui/detailed_mto_panel.py             Step 5 panel
scripts/validate_knowledge_base.py   DB validation CLI
tests/test_detailed_mto.py           12 tests
```

Only change to existing code: a 9-line, try/except-guarded call to the panel
at the end of Step 5 in `app.py`.
