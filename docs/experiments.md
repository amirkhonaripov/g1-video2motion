# Experiments

Problems we hit, what we thought caused them, how we tested it, and what we concluded.

## 1. GVHMR + GMR fails the tennis serve with SONIC (ViT-H)

- **Problem.** SONIC (ViT-H) falls on the GVHMR + GMR tennis motion in 10 of 10 tries (at 4.5 or 7.8 s), but
  finishes two of three ViT-H motions of the same video.
- **Hypothesis.** The motion floats. After the serve jump (~4.3 s) its feet never come back down:
  the lowest foot stays 12–20 cm above the floor for the rest of the clip, against ~4 cm when
  standing. A robot on the floor can't follow it, and the hand/foot height rule fires (it is the
  rule that fires in all 10 tries).
- **Test.** Put the feet back on the floor (`scripts/ground_motion.py`): shift the whole motion
  down by a slowly varying floor estimate (lowest ankle over a 1 s window, smoothed), so jumps
  shorter than 1 s stay. Same fix for every motion of both methods; SONIC (ViT-H) rerun, 10 tries per
  condition.
- **Result.**

  | SONIC (ViT-H) finishes: flat ground · harder | Raw | Grounded |
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
  environments), and ran SONIC (ViT-H) on both.

  | Tennis serve | GVHMR + GMR, raw | clipped | ViT-H sample 1, raw | clipped |
  |---|---|---|---|---|
  | BeyondMimic, mjlab (1024 tries) | finishes 97% | 97% | 100% | 100% |
  | BeyondMimic, flat ground · harder | 10/10 · 50/50 | 10/10 · 42/50 | 10/10 · 49/50 | 10/10 · 45/50 |
  | BeyondMimic, pose error (cm) | 9.3 | 9.5 | 4.5 | 4.6 |
  | SONIC (ViT-H), flat ground · harder | 0/10 · 0/50 | 0/10 · 0/50 | 10/10 · 49/50 | 10/10 · 50/50 |

  (BeyondMimic at 3000 iterations.)

  Clipping doesn't help either tracker (BeyondMimic is slightly worse under the harder conditions),
  so results use the raw motions: the same reference for both trackers.

## 3. The jump and knee kick

- **Problem.** SONIC (ViT-H) fails all 4 motions of the jump and knee kick at 1.0 s, raw or
  grounded. The robot never takes off: at 0.96 s the reference pelvis is in the air (1.01–1.03 m)
  while the robot's stays at 0.78–0.86 m, so a foot or knee ends up 26 cm below the reference and
  the hand/foot height rule fires. Up to take-off it tracks within 3 cm.
- **Hypothesis 1.** The jump is beyond the robot, or our harness gets something wrong.
- **Test.** The same 4 motions through ViT-H's own tracker script (`g1_tracker`), and a BeyondMimic
  policy trained on each method's motion (3000 iterations, as for tennis).
- **Result.** ViT-H's script fails the same way (0.92–0.98 s; the robot's pelvis peaks at
  0.79 m for ViT-H's samples, against 1.00–1.03 m in the reference). BeyondMimic does ViT-H's jump:

  | Jump and knee kick | GVHMR + GMR | GVHMR + GMR, grounded | ViT-H sample 1 |
  |---|---|---|---|
  | BeyondMimic, mjlab (1024 tries) | finishes 0% | 0% | 93% |
  | BeyondMimic, flat ground · harder | fails at 0.9 s, 10/10 · 0/50 | fails at 0.9 s, 10/10 · 0/50 | finishes 10/10 · 50/50 |
  | SONIC (ViT-H), flat ground | fails at 1.0 s, 10/10 | fails at 1.0 s, 10/10 | fails at 1.0 s, 10/10 |

  GVHMR + GMR still fails after 18500 iterations.
- **Conclusion.** Rejected: the robot can do the jump, and the harness agrees with ViT-H's own
  script. SONIC (ViT-H) doesn't jump. GVHMR + GMR's motion fails for a different reason.
- **Hypothesis 2.** GVHMR + GMR's motion floats, as on the tennis serve: after take-off its feet
  never come back down (the lowest ankle stays at least 9 cm above flat-foot height).
- **Test.** BeyondMimic on the grounded motion (`scripts/ground_motion.py`), 3000 iterations.
- **Result.** Still 0% in mjlab, failing at 0.8–0.9 s on the hand/foot height rule.
- **Conclusion.** Rejected: grounding makes it land, but it still fails at take-off.
- **Hypothesis 3.** GVHMR + GMR's jump breaks physics. Once both feet are off the floor, the pelvis
  can only slow down at g (9.8 m/s²), so the take-off speed sets how high it can go.
- **Test.** Pelvis speed at take-off, the rise that speed allows (v²/2g), the rise in the motion,
  and the pelvis's mean vertical acceleration in the air.
- **Result.**

  | | Take-off speed (m/s) | Rise it allows (m) | Rise in the motion (m) | Acceleration in the air (m/s²) |
  |---|---|---|---|---|
  | GVHMR + GMR | 1.60 | 0.13 | 0.23 | −1.0 |
  | GVHMR + GMR, grounded | 1.53 | 0.12 | 0.18 | −6.5 |
  | ViT-H, samples 1-3 | 2.21–2.26 | 0.25–0.26 | 0.19–0.23 | −8.6 to −9.3 |

- **Conclusion.** Confirmed. ViT-H's jumps obey gravity; GVHMR + GMR's keeps rising after
  take-off as if it hangs in the air. No tracker can follow that: the robot can only follow a
  jump it can push off for.

## 4. The robots in the videos were seen from the wrong side

- **Problem.** The harness films every run from one fixed world angle. GVHMR + GMR and ViT-H put the
  robot at headings 90° apart, so one robot was shown edge-on, and neither matched the video.
- **Fix.** `scripts/render_run.py` re-renders runs from the harness logs with a camera that keeps
  the same angle to the body as the real camera has to the person in each frame (from GVHMR's
  in-camera body orientation), smoothed over 1 s.
- **Check.** On the fixed-camera studio dance, the person's turn in the video and the robot's
  heading move together (correlation 0.94). On the hip-hop clip, filmed from behind, the robots are
  seen from behind with the right hand on the image's right, as in the video.
