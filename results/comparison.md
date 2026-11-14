| Metric | mjlab (training sim) | ROS 2 + MuJoCo (deployment stack) |
|---|---|---|
| Episodes | 1024 | 5 |
| Success rate | 0.931 | 1.000 |
| Strict success (MPKPE ≤ 0.15 m throughout) | 0.000 | 0.000 |
| Joint error, mean (rad) | 0.084 | 0.083 (0.082–0.084) |
| Body position error, MPKPE (m) | 0.109 | 0.281 (0.272–0.289) |
| MPKPE, worst moment (m) | 0.336 | 0.760 (0.743–0.787) |
| Root-relative MPKPE (m) | 0.038 | 0.033 (0.033–0.034) |
| Root-relative MPKPE, worst moment (m) | 0.118 | 0.158 (0.156–0.160) |
| Drift from reference path, mean (m) | 0.100 | 0.280 (0.270–0.288) |
| Drift from reference path, max (m) | 0.329 | 0.752 (0.733–0.779) |
| Drift in the estimator's frame, mean (m) | – | 0.127 (0.112–0.150) |
| Drift in the estimator's frame, max (m) | – | 0.350 (0.333–0.371) |
| State estimator gap, max (m) | – | 0.965 (0.954–0.977) |
