# Experiments

Problems we hit, what we thought caused them, how we tested it, and what we concluded.

## 1. GVHMR + GMR fails the tennis serve with SONIC

- **Problem.** SONIC falls on the GVHMR + GMR tennis motion in 10 of 10 tries (at 4.5 or 7.8 s), but
  finishes two of three ViT-H motions of the same video.
- **Hypothesis.** The motion floats. After the serve jump (~4.3 s) its feet never come back down:
  the lowest foot stays 12–20 cm above the floor for the rest of the clip, against ~4 cm when
  standing. A robot on the floor can't follow it, and the hand/foot height rule fires (it is the
  rule that fires in all 10 tries).
- **Test.** Put the feet back on the floor (`scripts/ground_motion.py`): shift the whole motion
  down by a slowly varying floor estimate (lowest ankle over a 1 s window, smoothed), so jumps
  shorter than 1 s stay. Same fix for every motion of both methods; SONIC rerun, 10 tries per
  condition.
- **Result.**

  | SONIC finishes: flat ground · harder | Raw | Grounded |
  |---|---|---|
  | GVHMR + GMR | 0/10 · 0/50 | 10/10 · 45/50 |
  | ViT-H, 3 samples | 26/30 · 111/150 | 30/30 · 133/150 |
  | Other 5 clips, both methods | no change | no change |

  The fix moved GVHMR + GMR's motions down by 4–7 cm on average on the Pexels clips and the tennis
  serve (up to 17 cm), and ViT-H's up by 0–5 cm: GVHMR + GMR floats, ViT-H sits slightly low.

- **Conclusion.** Hypothesis confirmed. GVHMR + GMR's tennis failure is its height, not
  its pose, and it is cheap to fix. The comparison tables use the raw motions; the grounded results
  are reported next to them (`results/routes/harness_tables.md`). The jump and knee kick still fails
  for every motion.

## 2. Clipping joints into the soft limits (BeyondMimic training)

- **Problem.** BeyondMimic trained on the tennis motions didn't learn: 0% success in mjlab, and the
  mean episode length fell from 8–11 steps to ~3.
- **Hypothesis.** Video motions keep the knees almost straight: 42–52% of tennis frames have a knee
  below mjlab's soft joint limit (0.06 rad), against 0% for the LAFAN1 dance. BeyondMimic penalises
  soft-limit violations (weight −10), so the reward goes negative, and the policy learns to end
  episodes early.
- **Test.** Clip every joint into the soft limits (`scripts/clip_to_limits.py`; GMR: 76% of frames
  changed, at most 11°; ViT-H: 55%, at most 17°) and retrain.
- **Result.** The joint-limit penalty dropped to ~0, but training collapsed the same way
  (episode length 9 → 5). Every episode ended on the hand/foot height rule.
- **Conclusion.** Hypothesis rejected. The real cause: mjlab's `--env.scene.num-envs` defaults to
  **1**, so PPO trained on a single environment (24 steps per iteration). With 4096 environments,
  episode length went from 3 to 450+ steps in ~1500 iterations, on both raw and clipped motions.
- **Follow-up test: does clipping still matter?** Trained raw and clipped side by side (4096
  environments), and ran SONIC on both.

  | Tennis serve | GVHMR + GMR, raw | clipped | ViT-H sample 1, raw | clipped |
  |---|---|---|---|---|
  | BeyondMimic, mjlab (1024 tries) | finishes 97% | 97% | 100% | 100% |
  | BeyondMimic, flat ground · harder | 10/10 · 50/50 | 10/10 · 42/50 | 10/10 · 49/50 | 10/10 · 45/50 |
  | BeyondMimic, pose error (cm) | 9.3 | 9.5 | 4.5 | 4.6 |
  | SONIC, flat ground · harder | 0/10 · 0/50 | 0/10 · 0/50 | 10/10 · 49/50 | 10/10 · 50/50 |

  (BeyondMimic at 3000 iterations.)

  Clipping doesn't help either tracker (BeyondMimic is slightly worse under the harder conditions),
  so results use the raw motions: the same reference for both trackers.

## 3. The LAFAN1 cartwheel depends on the robot model

- **Problem.** BeyondMimic's demo policy finishes the LAFAN1 dance in mjlab (93% of 1024) and in the
  ROS 2 stack (5 of 5), but fails at the cartwheel (106.9 s) every time on the harness's original
  robot model (`unitree_rl_gym`).
- **Hypothesis.** Motor inertia: that model gives every joint the same armature (0.01, from Unitree's
  12-joint walking model), while BeyondMimic trained with per-joint values from the motor specs
  (0.0036–0.025).
- **Test.** Swapped one thing at a time between the two models: the `unitree_rl_gym` model with the
  per-joint armature, and the `ros2` model with 0.01 for every joint. BeyondMimic,
  flat ground, 3 tries each (the unswapped models: 10 tries).
- **Result.**

  | Contact shapes | Motor inertia | Cartwheel |
  |---|---|---|
  | `unitree_rl_gym` (4 spheres per foot, mesh hands) | 0.01 for every joint | fails at 106.9 s, 10/10 |
  | `unitree_rl_gym` | per joint | fails at 106.9 s, 3/3 |
  | `ros2` (capsule soles and hands) | 0.01 for every joint | finishes, 3/3 |
  | `ros2` | per joint | finishes, 10/10 |
- **Conclusion.** Hypothesis rejected: contact shapes decide the cartwheel, not motor inertia. The
  harness now defaults to the ROS 2 stack's model (`ros2`), the one BeyondMimic's
  sim-to-sim and the real-robot stack use, and results are reported on both models. SONIC fails the
  cartwheel on both, as it does in its own `g1_tracker`.

## 4. Every tracker fails the jump and knee kick at 1.0 s

- **Problem.** SONIC fails all 4 motions of the jump and knee kick at 1.0 s, raw or grounded.
- **Finding.** The robot never takes off. At 0.96 s the reference pelvis is in the air (1.01–1.03 m)
  while the robot's stays at 0.78–0.86 m, so a foot or knee ends up 26 cm below the reference and
  the hand/foot height rule fires. Up to take-off it tracks within 3 cm.
- **Open question.** Is the jump beyond the robot, or only beyond SONIC? Next test: a BeyondMimic
  policy trained on this motion.

## 5. The robots in the videos were seen from the wrong side

- **Problem.** The harness films every run from one fixed world angle. GVHMR + GMR and ViT-H put the
  robot at headings 90° apart, so one robot was shown edge-on, and neither matched the video.
- **Fix.** `scripts/render_run.py` re-renders runs from the harness logs with a camera that keeps
  the same angle to the body as the real camera has to the person in each frame (from GVHMR's
  in-camera body orientation), smoothed over 1 s.
- **Check.** On the fixed-camera studio dance, the person's turn in the video and the robot's
  heading move together (correlation 0.94). On the hip-hop clip, filmed from behind, the robots are
  seen from behind with the right hand on the image's right, as in the video.
