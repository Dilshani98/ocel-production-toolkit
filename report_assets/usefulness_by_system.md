## Process-mining usefulness by system

Directly-follows edges of the output against the clean log (per object type); frequency difference = mean absolute difference of edge shares; object count difference = objects too many or too few (lower is better).

| area | metric | system | held-out 5% | held-out 15% | held-out 30% | dev (seed 42) 5% | dev (seed 42) 15% | dev (seed 42) 30% |
|---|---|---|---|---|---|---|---|---|
| usefulness | edge_precision | B0 (as-is) | 0.3071 [0.3010, 0.3131] | 0.2344 [0.2322, 0.2366] | 0.2004 [0.1914, 0.2095] | 0.3116 | 0.2541 | 0.2160 |
| usefulness | edge_precision | B1 (hygiene) | 0.3071 [0.3010, 0.3131] | 0.2344 [0.2322, 0.2366] | 0.2004 [0.1914, 0.2095] | 0.3116 | 0.2541 | 0.2160 |
| usefulness | edge_precision | B2 (pair-only) | 0.3033 [0.2981, 0.3085] | 0.2279 [0.2271, 0.2288] | 0.1954 [0.1862, 0.2046] | 0.3010 | 0.2470 | 0.2102 |
| usefulness | edge_precision | B3 (closest in time) | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 | 1.0000 | 1.0000 |
| usefulness | edge_precision | B4 (B3 + eager links) | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 | 1.0000 | 1.0000 |
| usefulness | edge_precision | B5 (toolkit, delete O2O) | 0.9841 [0.9841, 0.9841] | 0.9841 [0.9841, 0.9841] | 0.9841 [0.9841, 0.9841] | 0.9841 | 0.9841 | 0.9841 |
| usefulness | edge_precision | Toolkit | 0.9841 [0.9841, 0.9841] | 0.9841 [0.9841, 0.9841] | 0.9841 [0.9841, 0.9841] | 0.9841 | 0.9841 | 0.9841 |
| usefulness | edge_recall | B0 (as-is) | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 | 1.0000 | 1.0000 |
| usefulness | edge_recall | B1 (hygiene) | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 | 1.0000 | 1.0000 |
| usefulness | edge_recall | B2 (pair-only) | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 | 1.0000 | 1.0000 |
| usefulness | edge_recall | B3 (closest in time) | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 | 1.0000 | 1.0000 |
| usefulness | edge_recall | B4 (B3 + eager links) | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 | 1.0000 | 1.0000 |
| usefulness | edge_recall | B5 (toolkit, delete O2O) | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 | 1.0000 | 1.0000 |
| usefulness | edge_recall | Toolkit | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 | 1.0000 | 1.0000 |
| usefulness | edge_f1 | B0 (as-is) | 0.4698 [0.4627, 0.4769] | 0.3798 [0.3769, 0.3827] | 0.3338 [0.3212, 0.3464] | 0.4751 | 0.4052 | 0.3553 |
| usefulness | edge_f1 | B1 (hygiene) | 0.4698 [0.4627, 0.4769] | 0.3798 [0.3769, 0.3827] | 0.3338 [0.3212, 0.3464] | 0.4751 | 0.4052 | 0.3553 |
| usefulness | edge_f1 | B2 (pair-only) | 0.4654 [0.4593, 0.4715] | 0.3713 [0.3701, 0.3724] | 0.3268 [0.3139, 0.3397] | 0.4627 | 0.3962 | 0.3473 |
| usefulness | edge_f1 | B3 (closest in time) | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 | 1.0000 | 1.0000 |
| usefulness | edge_f1 | B4 (B3 + eager links) | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 | 1.0000 | 1.0000 |
| usefulness | edge_f1 | B5 (toolkit, delete O2O) | 0.9920 [0.9920, 0.9920] | 0.9920 [0.9920, 0.9920] | 0.9920 [0.9920, 0.9920] | 0.9920 | 0.9920 | 0.9920 |
| usefulness | edge_f1 | Toolkit | 0.9920 [0.9920, 0.9920] | 0.9920 [0.9920, 0.9920] | 0.9920 [0.9920, 0.9920] | 0.9920 | 0.9920 | 0.9920 |
| usefulness | edge_frequency_difference | B0 (as-is) | 0.0387 [0.0345, 0.0430] | 0.1129 [0.1017, 0.1242] | 0.2158 [0.1975, 0.2342] | 0.0425 | 0.1015 | 0.1979 |
| usefulness | edge_frequency_difference | B1 (hygiene) | 0.0387 [0.0345, 0.0430] | 0.1129 [0.1017, 0.1242] | 0.2158 [0.1975, 0.2342] | 0.0425 | 0.1015 | 0.1979 |
| usefulness | edge_frequency_difference | B2 (pair-only) | 0.0389 [0.0347, 0.0432] | 0.1132 [0.1019, 0.1244] | 0.2160 [0.1977, 0.2343] | 0.0428 | 0.1018 | 0.1982 |
| usefulness | edge_frequency_difference | B3 (closest in time) | 0.0060 [0.0060, 0.0061] | 0.0180 [0.0179, 0.0181] | 0.0362 [0.0361, 0.0362] | 0.0060 | 0.0180 | 0.0360 |
| usefulness | edge_frequency_difference | B4 (B3 + eager links) | 0.0000 [0.0000, 0.0000] | 0.0001 [0.0001, 0.0001] | 0.0002 [0.0002, 0.0002] | 0.0000 | 0.0001 | 0.0003 |
| usefulness | edge_frequency_difference | B5 (toolkit, delete O2O) | 0.0038 [0.0038, 0.0038] | 0.0133 [0.0131, 0.0135] | 0.0303 [0.0299, 0.0306] | 0.0038 | 0.0113 | 0.0298 |
| usefulness | edge_frequency_difference | Toolkit | 0.0038 [0.0038, 0.0038] | 0.0133 [0.0131, 0.0135] | 0.0303 [0.0299, 0.0306] | 0.0038 | 0.0113 | 0.0298 |
| usefulness | object_count_abs_difference | B0 (as-is) | 295 [295, 295] | 886 [886, 886] | 1773 [1773, 1773] | 295 | 886 | 1773 |
| usefulness | object_count_abs_difference | B1 (hygiene) | 295 [295, 295] | 886 [886, 886] | 1773 [1773, 1773] | 295 | 886 | 1773 |
| usefulness | object_count_abs_difference | B2 (pair-only) | 285 [284, 286] | 875.5 [874, 877] | 1763 [1762, 1764] | 279 | 870 | 1757 |
| usefulness | object_count_abs_difference | B3 (closest in time) | 1 [0, 2] | 0 [0, 0] | 4.5 [4, 5] | 0 | 4 | 11 |
| usefulness | object_count_abs_difference | B4 (B3 + eager links) | 1 [0, 2] | 0 [0, 0] | 4.5 [4, 5] | 0 | 4 | 11 |
| usefulness | object_count_abs_difference | B5 (toolkit, delete O2O) | 12 [8, 16] | 195 [168, 222] | 611.5 [608, 615] | 18 | 61 | 630 |
| usefulness | object_count_abs_difference | Toolkit | 12 [8, 16] | 195 [168, 222] | 611.5 [608, 615] | 18 | 61 | 630 |
