# Entity extraction evaluation

30 hand-labelled notes, 133 entities. Strict = exact match after normalisation; relaxed = one contains the other.


## Strict matching

| System | Category | Precision | Recall | F1 |
|---|---|---|---|---|
| BERT pipeline | medications | 0.94 | 0.94 | 0.94 |
| BERT pipeline | symptoms | 0.67 | 0.62 | 0.65 |
| BERT pipeline | diagnoses | 0.75 | 0.64 | 0.69 |
| BERT pipeline | **overall (micro)** | 0.76 | 0.71 | 0.73 |
| Keyword baseline | medications | 1.00 | 0.03 | 0.06 |
| Keyword baseline | symptoms | 0.93 | 0.20 | 0.33 |
| Keyword baseline | diagnoses | 0.60 | 0.09 | 0.16 |
| Keyword baseline | **overall (micro)** | 0.85 | 0.13 | 0.22 |

## Relaxed matching

| System | Category | Precision | Recall | F1 |
|---|---|---|---|---|
| BERT pipeline | medications | 0.97 | 0.97 | 0.97 |
| BERT pipeline | symptoms | 0.93 | 0.86 | 0.90 |
| BERT pipeline | diagnoses | 0.96 | 0.82 | 0.89 |
| BERT pipeline | **overall (micro)** | 0.95 | 0.88 | 0.91 |
| Keyword baseline | medications | 1.00 | 0.03 | 0.06 |
| Keyword baseline | symptoms | 1.00 | 0.21 | 0.35 |
| Keyword baseline | diagnoses | 1.00 | 0.15 | 0.26 |
| Keyword baseline | **overall (micro)** | 1.00 | 0.15 | 0.26 |
