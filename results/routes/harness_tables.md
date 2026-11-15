### At a glance

| SONIC | GVHMR + GMR: flat ground | harder | pose error (cm) | ViT-H, 3 samples: flat ground | harder | pose error (cm) |
|---|---|---|---|---|---|---|
| Studio dance (Pexels) | finishes | 50/50 | 7.5 | 3/3 finish | 150/150 | 4.4 |
| Hip-hop, filmed from behind (Pexels) | finishes | 49/50 | 11.9 | 3/3 finish | 150/150 | 3.1 |
| Jump and knee kick (Pexels) | fails at 1.0 s (10/10) | 0/50 | 6.4 | 0/3 finish | 0/150 | 6.1 |
| Tennis serve (GVHMR demo video) | fails at 4.5–7.8 s (10/10) | 0/50 | 6.9 | 2/3 finish | 111/150 | 5.0 |
| AIST++ Pop | finishes | 50/50 | 3.7 | 3/3 finish | 150/150 | 2.4 |
| AIST++ Jazz | finishes | 50/50 | 2.0 | 3/3 finish | 150/150 | 2.8 |

### Studio dance (Pexels)

| SONIC | GVHMR + GMR | ViT-H sample 1 | ViT-H sample 2 | ViT-H sample 3 |
|---|---|---|---|---|
| Reference: frames past joint limits (%) | 0.0 | 10.7 | 10.2 | 13.2 |
| Reference: fastest joint (rad/s) | 10 | 20 | 21 | 16 |
| Reference: foot sliding (cm/s) | 10 | 14 | 14 | 14 |
| Flat ground | finishes | finishes | finishes | finishes |
| Never more than 15 cm off | 0/10 | 0/10 | 0/10 | 0/10 |
| Pose error, mean / worst (cm) | 7.5 / 12.8 | 3.9 / 10.7 | 5.0 / 14.8 | 4.4 / 13.1 |
| Position error, mean / worst (cm) | 15.6 / 22.9 | 19.2 / 29.8 | 17.2 / 29.4 | 15.8 / 24.5 |
| Joint error (°) | 5.8 | 5.7 | 5.8 | 6.7 |
| Robot joints past limits (% of time) | 0.0 | 0.0 | 0.0 | 0.0 |
| Power (W) | 35 | 41 | 44 | 44 |
| Time to make the motion (s) | 97 | 31 | 31 | 31 |

| Finishes (of 10 tries) | GVHMR + GMR | ViT-H sample 1 | ViT-H sample 2 | ViT-H sample 3 |
|---|---|---|---|---|
| Low friction | 10/10 | 10/10 | 10/10 | 10/10 |
| Ice | 10/10 | 10/10 | 10/10 | 10/10 |
| Push from the side | 10/10 | 10/10 | 10/10 | 10/10 |
| Hard push from behind | 10/10 | 10/10 | 10/10 | 10/10 |
| Push from the front | 10/10 | 10/10 | 10/10 | 10/10 |

### Hip-hop, filmed from behind (Pexels)

| SONIC | GVHMR + GMR | ViT-H sample 1 | ViT-H sample 2 | ViT-H sample 3 |
|---|---|---|---|---|
| Reference: frames past joint limits (%) | 0.0 | 0.3 | 0.6 | 0.0 |
| Reference: fastest joint (rad/s) | 5 | 13 | 24 | 19 |
| Reference: foot sliding (cm/s) | 5 | 11 | 11 | 11 |
| Flat ground | finishes | finishes | finishes | finishes |
| Never more than 15 cm off | 0/10 | 0/10 | 0/10 | 0/10 |
| Pose error, mean / worst (cm) | 11.9 / 19.5 | 3.2 / 4.8 | 3.0 / 4.4 | 3.1 / 4.5 |
| Position error, mean / worst (cm) | 19.3 / 26.9 | 13.0 / 20.5 | 24.8 / 36.9 | 21.7 / 28.0 |
| Joint error (°) | 5.1 | 4.8 | 4.8 | 4.8 |
| Robot joints past limits (% of time) | 0.0 | 0.0 | 0.0 | 0.0 |
| Power (W) | 38 | 39 | 40 | 43 |
| Time to make the motion (s) | 51 | 22 | 22 | 22 |

| Finishes (of 10 tries) | GVHMR + GMR | ViT-H sample 1 | ViT-H sample 2 | ViT-H sample 3 |
|---|---|---|---|---|
| Low friction | 10/10 | 10/10 | 10/10 | 10/10 |
| Ice | 10/10 | 10/10 | 10/10 | 10/10 |
| Push from the side | 9/10 | 10/10 | 10/10 | 10/10 |
| Hard push from behind | 10/10 | 10/10 | 10/10 | 10/10 |
| Push from the front | 10/10 | 10/10 | 10/10 | 10/10 |

### Jump and knee kick (Pexels)

| SONIC | GVHMR + GMR | ViT-H sample 1 | ViT-H sample 2 | ViT-H sample 3 |
|---|---|---|---|---|
| Reference: frames past joint limits (%) | 0.0 | 5.4 | 6.3 | 9.9 |
| Reference: fastest joint (rad/s) | 16 | 24 | 27 | 25 |
| Reference: foot sliding (cm/s) | 31 | 14 | 22 | 19 |
| Flat ground | fails at 1.0 s (10/10) | fails at 1.0 s (10/10) | fails at 1.0 s (10/10) | fails at 1.0 s (10/10) |
| Never more than 15 cm off | 0/10 | 0/10 | 0/10 | 0/10 |
| Pose error, mean / worst (cm) | 6.4 / 20.0 | 6.1 / 22.8 | 6.0 / 21.5 | 6.2 / 22.5 |
| Position error, mean / worst (cm) | 8.7 / 26.8 | 12.1 / 35.1 | 11.7 / 33.0 | 11.2 / 31.1 |
| Joint error (°) | 7.5 | 6.5 | 6.7 | 6.4 |
| Robot joints past limits (% of time) | 0.0 | 2.9 | 0.2 | 3.9 |
| Power (W) | 340 | 257 | 245 | 255 |
| Time to make the motion (s) | 23 | 17 | 17 | 17 |

| Finishes (of 10 tries) | GVHMR + GMR | ViT-H sample 1 | ViT-H sample 2 | ViT-H sample 3 |
|---|---|---|---|---|
| Low friction | 0/10 | 0/10 | 0/10 | 0/10 |
| Ice | 0/10 | 0/10 | 0/10 | 0/10 |
| Push from the side | 0/10 | 0/10 | 0/10 | 0/10 |
| Hard push from behind | 0/10 | 0/10 | 0/10 | 0/10 |
| Push from the front | 0/10 | 0/10 | 0/10 | 0/10 |

### Tennis serve (GVHMR demo video)

| SONIC | GVHMR + GMR | ViT-H sample 1 | ViT-H sample 2 | ViT-H sample 3 |
|---|---|---|---|---|
| Reference: frames past joint limits (%) | 0.0 | 5.6 | 4.4 | 11.3 |
| Reference: fastest joint (rad/s) | 20 | 25 | 44 | 50 |
| Reference: foot sliding (cm/s) | 17 | 18 | 15 | 20 |
| Flat ground | fails at 4.5–7.8 s (10/10) | finishes | fails at 8.0 s (4/10) | finishes |
| Never more than 15 cm off | 0/10 | 0/10 | 0/10 | 0/10 |
| Pose error, mean / worst (cm) | 6.9 / 18.8 | 4.5 / 13.7 | 5.1 / 15.6 | 5.3 / 16.4 |
| Position error, mean / worst (cm) | 25.4 / 51.6 | 20.5 / 40.9 | 21.8 / 49.0 | 36.9 / 73.7 |
| Joint error (°) | 7.4 | 6.6 | 6.7 | 7.3 |
| Robot joints past limits (% of time) | 0.0 | 0.0 | 0.0 | 1.2 |
| Power (W) | 121 | 133 | 128 | 152 |
| Time to make the motion (s) | 49 | 43 | 43 | 43 |

| Finishes (of 10 tries) | GVHMR + GMR | ViT-H sample 1 | ViT-H sample 2 | ViT-H sample 3 |
|---|---|---|---|---|
| Low friction | 0/10 | 10/10 | 6/10 | 10/10 |
| Ice | 0/10 | 10/10 | 6/10 | 10/10 |
| Push from the side | 0/10 | 9/10 | 6/10 | 6/10 |
| Hard push from behind | 0/10 | 10/10 | 2/10 | 3/10 |
| Push from the front | 0/10 | 10/10 | 8/10 | 5/10 |

### AIST++ Pop

| SONIC | GVHMR + GMR | ViT-H sample 1 | ViT-H sample 2 | ViT-H sample 3 |
|---|---|---|---|---|
| Reference: frames past joint limits (%) | 0.0 | 9.2 | 11.0 | 8.5 |
| Reference: fastest joint (rad/s) | 5 | 12 | 10 | 84 |
| Reference: foot sliding (cm/s) | 2 | 11 | 10 | 16 |
| Flat ground | finishes | finishes | finishes | finishes |
| Never more than 15 cm off | 5/10 | 0/10 | 10/10 | 0/10 |
| Pose error, mean / worst (cm) | 3.7 / 6.8 | 2.2 / 6.3 | 2.3 / 3.8 | 2.8 / 13.6 |
| Position error, mean / worst (cm) | 7.7 / 15.0 | 9.0 / 16.2 | 8.9 / 14.2 | 8.3 / 20.2 |
| Joint error (°) | 4.5 | 4.2 | 4.3 | 5.8 |
| Robot joints past limits (% of time) | 0.0 | 0.0 | 0.0 | 0.3 |
| Power (W) | 26 | 28 | 29 | 59 |
| Time to make the motion (s) | 58 | 43 | 43 | 43 |

| Finishes (of 10 tries) | GVHMR + GMR | ViT-H sample 1 | ViT-H sample 2 | ViT-H sample 3 |
|---|---|---|---|---|
| Low friction | 10/10 | 10/10 | 10/10 | 10/10 |
| Ice | 10/10 | 10/10 | 10/10 | 10/10 |
| Push from the side | 10/10 | 10/10 | 10/10 | 10/10 |
| Hard push from behind | 10/10 | 10/10 | 10/10 | 10/10 |
| Push from the front | 10/10 | 10/10 | 10/10 | 10/10 |

### AIST++ Jazz

| SONIC | GVHMR + GMR | ViT-H sample 1 | ViT-H sample 2 | ViT-H sample 3 |
|---|---|---|---|---|
| Reference: frames past joint limits (%) | 0.0 | 0.0 | 0.0 | 0.0 |
| Reference: fastest joint (rad/s) | 16 | 14 | 12 | 16 |
| Reference: foot sliding (cm/s) | 1 | 4 | 4 | 3 |
| Flat ground | finishes | finishes | finishes | finishes |
| Never more than 15 cm off | 10/10 | 10/10 | 10/10 | 10/10 |
| Pose error, mean / worst (cm) | 2.0 / 3.7 | 2.9 / 3.8 | 2.7 / 3.5 | 2.7 / 3.4 |
| Position error, mean / worst (cm) | 3.2 / 5.0 | 4.9 / 7.2 | 4.8 / 7.2 | 4.9 / 6.7 |
| Joint error (°) | 5.9 | 4.9 | 5.0 | 5.2 |
| Robot joints past limits (% of time) | 0.0 | 0.0 | 0.0 | 0.0 |
| Power (W) | 10 | 11 | 12 | 11 |
| Time to make the motion (s) | 58 | 44 | 44 | 44 |

| Finishes (of 10 tries) | GVHMR + GMR | ViT-H sample 1 | ViT-H sample 2 | ViT-H sample 3 |
|---|---|---|---|---|
| Low friction | 10/10 | 10/10 | 10/10 | 10/10 |
| Ice | 10/10 | 10/10 | 10/10 | 10/10 |
| Push from the side | 10/10 | 10/10 | 10/10 | 10/10 |
| Hard push from behind | 10/10 | 10/10 | 10/10 | 10/10 |
| Push from the front | 10/10 | 10/10 | 10/10 | 10/10 |

### Tennis serve: BeyondMimic vs SONIC

| Tennis serve | GVHMR + GMR | GVHMR + GMR, clipped | ViT-H sample 1 | ViT-H sample 1, clipped |
|---|---|---|---|---|
| BeyondMimic: mjlab (1024 tries) | finishes 97% | finishes 97% | finishes 100% | finishes 100% |
| BeyondMimic: flat ground | finishes | finishes | finishes | finishes |
| BeyondMimic: harder (of 50) | 50/50 | 42/50 | 49/50 | 45/50 |
| BeyondMimic: pose error (cm) | 9.3 | 9.5 | 4.5 | 4.6 |
| SONIC: flat ground | fails at 4.5–7.8 s (10/10) | fails at 4.5–7.8 s (10/10) | finishes | finishes |
| SONIC: harder (of 50) | 0/50 | 0/50 | 49/50 | 50/50 |
| SONIC: pose error (cm) | 6.9 | 5.1 | 4.5 | 4.5 |

### Feet put back on the floor (grounded)

| SONIC finishes: flat ground · harder | GVHMR + GMR, raw | GVHMR + GMR, grounded | ViT-H, raw | ViT-H, grounded |
|---|---|---|---|---|
| Studio dance (Pexels) | 10/10 · 50/50 | 10/10 · 50/50 | 30/30 · 150/150 | 30/30 · 150/150 |
| Hip-hop, filmed from behind (Pexels) | 10/10 · 49/50 | 10/10 · 50/50 | 30/30 · 150/150 | 30/30 · 150/150 |
| Jump and knee kick (Pexels) | 0/10 · 0/50 | 0/10 · 0/50 | 0/30 · 0/150 | 0/30 · 0/150 |
| Tennis serve (GVHMR demo video) | 0/10 · 0/50 | 10/10 · 45/50 | 26/30 · 111/150 | 30/30 · 133/150 |
| AIST++ Pop | 10/10 · 50/50 | 10/10 · 50/50 | 30/30 · 150/150 | 30/30 · 150/150 |
| AIST++ Jazz | 10/10 · 50/50 | 10/10 · 50/50 | 30/30 · 150/150 | 30/30 · 150/150 |

### LAFAN1 dance: BeyondMimic vs SONIC

| LAFAN1 dance (131 s, motion capture) | BeyondMimic | SONIC |
|---|---|---|
| Flat ground | finishes | fails at 106.7 s (10/10) |
| Harder conditions | 40/50 | 0/50 |
| Pose error, mean (cm) | 3.5 | 4.2 |
| Position error, mean (cm) | 7.6 | 185.0 |
| Policy time per step (ms) | 0.05 | 1.34 |
| mjlab (training simulator, 1024 tries) | finishes 93% | – |
| ROS 2 deployment stack (5 tries) | finishes 5/5 | – |
| SONIC's own tracker (g1_tracker) | – | fails at 106.7 s |

### Notes

- **Flat ground:** 10 tries that differ only by tiny start noise (±0.02 rad per joint), so they
  nearly always agree; the harder conditions are where tries really differ.
- **Fails:** torso height, torso tilt or a hand/foot height more than 0.25 m from the reference
  (BeyondMimic's rules). **Never more than 15 cm off:** PHUMA's strict success.
- **Pose error (r-MPKPE):** body-part error after placing the reference on the robot: how well the
  pose is copied. **Position error (MPKPE):** the same without moving it: pose plus drift.
- **SONIC's drift is partly by design:** it follows the reference relative to itself, not a world
  position, so its position error grows on long motions while its pose error stays low.
- **ViT-H samples:** ViT-H generates a motion from random noise; samples 1-3 are three draws
  (seeds 42, 1, 2) from the same video.
- **Robot model:** the harness default, `ros2`: the G1 of the ROS 2 stack that runs the real robot.
