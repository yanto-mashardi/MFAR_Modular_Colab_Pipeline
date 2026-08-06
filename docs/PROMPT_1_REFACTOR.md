# Prompt 1 — Behavior-Preserving Refactor of Stage 01–02

## Scope boundary

Prompt 1 restructures Stage 01 and Stage 02 into testable functions while preserving the frozen MFAR V1 scientific behavior. The refactor does not change cleaning priority, corridor limits, SOG limits, segment criteria, grid interval, bracket-gap limit, interpolation equations, berth/state definitions, output schemas, or downstream Stage 03–07 contracts.

## Structure

- `src/mfar_stage12.py` contains pure transformations and stage orchestration.
- `notebooks/01_AIS_Input_and_Cleaning.ipynb` remains the independent Stage 01 Colab controller.
- `notebooks/02_Time_Grid_and_State_Preparation.ipynb` remains the independent Stage 02 Colab controller.
- `tests/test_stage12_refactor.py` tests rejection priority, segmentation, circular interpolation, bracket rejection, state audit, and notebook independence.
- `tools/verify_prompt1_equivalence.py` compares all canonical Stage 01–07 CSV row counts and SHA-256 hashes with the immutable Prompt 0 baseline.

## Maintenance fixes included

Two compatibility issues are treated separately from scientific logic:

1. deterministic cell IDs are added to notebook cells to remove `MissingIDFieldWarning` under current `nbformat`;
2. deprecated `openpyxl` style-copy calls are replaced with `copy.copy`, preserving the same workbook formatting.

These changes affect notebook metadata and Excel formatting implementation. They do not alter scientific CSV outputs.
