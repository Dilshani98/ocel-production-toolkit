## Realism check (clone detectability)

AUC of a simple score (ID number, row position, number of blank attributes, decimal places) for telling clones from real objects of the same type; 0.5 = no signal. Number and objects-position AUCs are equal because objects are written sorted by ID. Grey band: pass range 0.4-0.6. Not shown (check failed before its AUCs): seed 7 at 5%: SteelSheet: clone numbers outside real range.

| check | held-out 5% | held-out 15% | held-out 30% | dev (seed 42) 5% | dev (seed 42) 15% | dev (seed 42) 30% |
|---|---|---|---|---|---|---|
| SteelSheet number AUC | 0.5280 [0.5280, 0.5280] | 0.5020 [0.5000, 0.5040] | 0.5110 [0.5110, 0.5110] | 0.4910 | 0.5160 | 0.5020 |
| SteelSheet objects position AUC | 0.5280 [0.5280, 0.5280] | 0.5020 [0.5000, 0.5040] | 0.5110 [0.5110, 0.5110] | 0.4910 | 0.5160 | 0.5020 |
| relations position AUC | 0.4920 [0.4920, 0.4920] | 0.4910 [0.4890, 0.4930] | 0.4915 [0.4910, 0.4920] | 0.4920 | 0.4980 | 0.4940 |
| o2o position AUC | 0.4950 [0.4950, 0.4950] | 0.4940 [0.4940, 0.4940] | 0.4935 [0.4890, 0.4980] | 0.5130 | 0.4970 | 0.4930 |
| SteelSheet missing-attribute AUC | 0.4790 [0.4790, 0.4790] | 0.4960 [0.4900, 0.5020] | 0.4995 [0.4970, 0.5020] | 0.4960 | 0.5070 | 0.5000 |
| SteelSheet p_mass[kg] decimals AUC | 0.4950 [0.4950, 0.4950] | 0.5075 [0.4990, 0.5160] | 0.5005 [0.4910, 0.5100] | 0.4940 | 0.4920 | 0.5080 |
| SteelSheet s_co2e[kg] decimals AUC | 0.5000 [0.5000, 0.5000] | 0.5000 [0.5000, 0.5000] | 0.5000 [0.5000, 0.5000] | 0.5000 | 0.5000 | 0.5000 |
