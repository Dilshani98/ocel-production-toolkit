## Toolkit repairs by severity

What the toolkit changed, and how much of it was wrong. Labels and timestamps are shares of the damaged values; the rest are counts.

| repair | held-out 5% | held-out 15% | held-out 30% | dev (seed 42) 5% | dev (seed 42) 15% | dev (seed 42) 30% |
|---|---|---|---|---|---|---|
| Labels: share of distorted labels restored | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 | 1.0000 | 1.0000 |
| Labels: valid labels changed | 0 [0, 0] | 0 [0, 0] | 0 [0, 0] | 0 | 0 | 0 |
| Timestamps: share of drifted events restored exactly | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 [1.0000, 1.0000] | 1.0000 | 1.0000 | 1.0000 |
| Timestamps: untouched events changed | 0 [0, 0] | 0 [0, 0] | 0 [0, 0] | 0 | 0 | 0 |
| Identity: pairs merged | 283 [279, 287] | 691 [664, 718] | 1161.5 [1158, 1165] | 277 | 825 | 1143 |
| Identity: wrong pairs merged | 0 [0, 0] | 1 [0, 2] | 2.5 [1, 4] | 0 | 1 | 4 |
| Identity: true pairs | 295 [295, 295] | 886 [886, 886] | 1773 [1773, 1773] | 295 | 886 | 1773 |
| E2O: links added | 288.5 [279, 298] | 877.5 [876, 879] | 1733.5 [1706, 1761] | 298 | 894 | 1780 |
| E2O: wrong links added | 0 [0, 0] | 0 [0, 0] | 0 [0, 0] | 0 | 0 | 0 |
| E2O: damaged links | 1306.5 [1306, 1307] | 3939.5 [3934, 3945] | 7885.5 [7882, 7889] | 1325 | 3960 | 7914 |
| O2O: links repaired | 1020 [1018, 1022] | 2983.5 [2976, 2991] | 5775.5 [5748, 5803] | 1022 | 3011 | 5780 |
| O2O: repairs with a wrong new target | 0 [0, 0] | 0.5 [0, 1] | 1 [1, 1] | 0 | 0 | 0 |
| O2O: right links broken | 0 [0, 0] | 0 [0, 0] | 0 [0, 0] | 0 | 0 | 0 |
| O2O: damaged links | 1316 [1313, 1319] | 3835.5 [3820, 3851] | 7394.5 [7380, 7409] | 1295 | 3818 | 7420 |
