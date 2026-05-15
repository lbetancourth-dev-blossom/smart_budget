# Refinement — DATA-1139

**Date:** 2026-05-15
**Mode:** feature
**Risk:** medium
**Published:** yes · Jira comment ID 280157

## Applied simplifications
(none)

## Created subtasks
(none — documented in comment only)

## AC edits applied
(none — proposed in comment only, not applied in Jira)

## Key findings

1. AC 2 describes the wrong output (predicted amounts = DATA-1138 scope). Needs rewrite.
2. "Quantity TBD" is a logical blocker — N must be agreed before coding.
3. Field names in dev context don't match real codebase (estado vs deletedat, etc.).
4. fact_transactions.csv has no 'source' column — infer from idtransaction prefix.

## Proposed AC edits (not applied)

**AC 2:**
> Two datasets generated: test_internal.csv (OLB SUB + LOAN) and test_external.csv (Plaid/Finicity EXT). Both apply filter_transactions(). Each row: real spend, period, member ID, category.

**AC 4:**
> Files written atomically to data/dough/test/ with chmod 600. Usable as --input for eval_runner.py.

## Suggested subtasks (not created)

1. Acordar N de miembros con DS team
2. Escribir scripts/extract_test_datasets.py
3. Tests unitarios tests/unit/test_extract_test_datasets.py
4. Actualizar AC 2 y AC 4 en Jira
