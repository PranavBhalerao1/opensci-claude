# Scientific review history

| Review | Verdict | Decision | Fatal | Major | Repair level | Re-run tasks | Cost |
|---|---|---|---|---|---|---|---|
| 1 | major_revision | repair | 0 | 2 | report | — | $2.53 |
| 2 | major_revision | repair | 0 | 1 | report | — | $1.32 |
| 3 | major_revision | repair | 0 | 1 | report | — | $0.00 |
| 4 | major_revision | unresolved | 0 | 1 | — | — | $2.21 |

## Issues

- T-001 [resolved] MAJOR literature: kang2024game mischaracterized as using Mixup and CutOut (seen in reviews 1)
- T-002 [resolved] MAJOR literature: kumar2025enhancing mischaracterized as concluding training budget is a key moderating factor (seen in reviews 1)
- T-003 [refuted] MAJOR controls_confounds: build_loaders uses test set as validation loader; possible test-set leakage into per-epoch monitoring (seen in reviews 1)
- T-004 [open] MAJOR figures_tables: Sub-figure caption for N=60,000 incorrectly reads N=500 (seen in reviews 2, 3, 4)
- T-005 [refuted] MAJOR reproducibility: Training scripts not provided; shown build_loaders code uses test set as validation, contradicting the plan and the numerical record (seen in reviews 4)
