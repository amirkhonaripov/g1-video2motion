"""Score ROS 2 + MuJoCo runs (.npz from bag_to_npz.py) against the reference motion with BeyondMimic's rules.

Policy start (`start_method`): `override` (--policy-start-s), else `sim_log`, when the launch log activated the
policy controller, placed in sim time through the recorder's receive times of /joint_states, else `alignment`, the
lag in [0, 0.3] s after the first joint sample that best matches the reference's first 2 s. Times in the output are
seconds after the policy start. `complete` only means that the recording covers the whole motion.

In ROS 2 the robot starts in its standby stance, not in the reference's first frame as in mjlab and the harness, so
the termination rules are checked from --grace-s (0.5 s) on. Left out of the summary: `startup_drop` (head below
1.15 m at the first joint sample: the robot was falling before the controllers were up) and `invalid_recording`
(first joint sample over 1 s after the simulator started at sim time 0: the recorder joined late).
"""

import argparse
import json
import re
from pathlib import Path

import mujoco
import numpy as np

from scripts.g1 import (
  G1_XML,
  REAL_FALL_HEAD_HEIGHT_M,
  REAL_FALL_TIME_S,
  STARTUP_DROP_HEAD_M,
  STRICT_MPKPE_M,
  TRACKING_ANCHOR_BODY,
  TRACKING_ANCHOR_GRAVITY,
  TRACKING_ANCHOR_HEIGHT_M,
  TRACKING_END_EFFECTOR_HEIGHT_M,
  TRACKING_END_EFFECTORS,
  gravity_z,
  turn_xy,
  yaw,
)

FPS = 50.0  # reference motion rate
GRACE_S = 0.5  # time to move from the standby stance onto the reference
LATE_RECORDING_S = 1.0  # first joint sample later than this (sim time): the recorder joined late
MAX_START_LAG_S = 0.3  # alignment: policy start at most this long after the first joint sample...
ALIGN_S = 2.0  # ...matching this much of the reference
POLICY_SWITCH = re.compile(r"\[(\d+\.\d+)\] \[controller_manager\]: Activating controllers: \[ walking_controller \]")
MEAN_KEYS = ("mpkpe_m", "r_mpkpe_m", "pre_failure_r_mpkpe_m", "joint_mae_rad", "drift_mean_m")


def parse_args():
  parser = argparse.ArgumentParser(description="Analyze ROS 2 sim-to-sim runs")
  parser.add_argument("runs", nargs="+", help="run .npz files")
  parser.add_argument("--reference", default="runs/onnx/demo/reference.npz", help="reference.npz from export_onnx")
  parser.add_argument("--output", help="write the results as JSON")
  parser.add_argument("--model-xml", default=G1_XML, help="G1 MuJoCo model with the mid360 lidar site")
  parser.add_argument(
    "--policy-start-s", type=float, nargs="+",
    help="sim time of the policy start: one for all runs, or one per run (default: from the sim log or alignment)",
  )
  parser.add_argument("--logs-dir", help="folder of <run>.sim.log launch logs, for the policy start")
  parser.add_argument("--tries-dir", help="folder of <run>.tries files (launches per run; 1 if absent)")
  parser.add_argument("--grace-s", type=float, default=GRACE_S, help="check the termination rules from this time on")
  args = parser.parse_args()
  if args.policy_start_s and len(args.policy_start_s) not in (1, len(args.runs)):
    parser.error("--policy-start-s takes one value, or one per run")
  return args


def resample(times, values, new_times):
  return np.stack(
    [np.interp(new_times, times, values[:, k]) for k in range(values.shape[1])],
    axis=1,
  )


def pose_matrix(pos, rot):
  m = np.eye(4)
  m[:3, :3], m[:3, 3] = rot, pos
  return m


def set_pose(model, data, run, adr, base_pos, base_quat, joint_pos):
  data.qpos[adr] = joint_pos
  if str(run["base_frame"]) == "pelvis":
    data.qpos[:3], data.qpos[3:7] = base_pos, base_quat
    return
  # the bags hold the head lidar pose; place the pelvis under it
  data.qpos[:3], data.qpos[3:7] = 0, [1, 0, 0, 0]
  mujoco.mj_kinematics(model, data)
  site = model.site("mid360").id
  pelvis_to_site = pose_matrix(data.site_xpos[site], data.site_xmat[site].reshape(3, 3))
  world_rot = np.zeros(9)
  mujoco.mju_quat2Mat(world_rot, np.asarray(base_quat, dtype=float))
  world_to_site = pose_matrix(base_pos, world_rot.reshape(3, 3))
  world_to_pelvis = world_to_site @ np.linalg.inv(pelvis_to_site)
  quat = np.zeros(4)
  mujoco.mju_mat2Quat(quat, world_to_pelvis[:3, :3].flatten())
  data.qpos[:3], data.qpos[3:7] = world_to_pelvis[:3, 3], quat


def robot_bodies(model, run, times, body_names):
  """Body positions and the anchor's orientation, by forward kinematics on the true base and the joints."""
  data = mujoco.MjData(model)
  adr = [model.joint(name).qposadr[0] for name in run["joint_names"]]
  ids = [model.body(name).id for name in body_names]
  anchor = model.body(TRACKING_ANCHOR_BODY).id
  joints = resample(run["joint_time"], run["joint_pos"], times)
  base = resample(run["base_time"], run["base_pos"], times)
  k = np.minimum(np.searchsorted(run["base_time"], times), len(run["base_time"]) - 1)

  pos, anchor_quat = [], []
  for i in range(len(times)):
    set_pose(model, data, run, adr, base[i], run["base_quat"][k[i]], joints[i])
    mujoco.mj_kinematics(model, data)
    pos.append(data.xpos[ids].copy())
    anchor_quat.append(data.xquat[anchor].copy())
  return np.array(pos), np.array(anchor_quat)


def load_run(path, joint_names):
  run = dict(np.load(path))
  if str(run["base_frame"]) != "mid360":
    raise ValueError(f"{path}: the fall rules need the head (mid360) pose, got {run['base_frame']}")
  order = [list(run["joint_names"]).index(n) for n in joint_names]
  run["joint_pos"], run["joint_names"] = run["joint_pos"][:, order], joint_names
  return run


def log_start(run, log):
  """Sim time when the launch log activated the policy controller (None if unknown)."""
  if "joint_wall_time" not in run or not log.exists():
    return None
  switches = POLICY_SWITCH.findall(log.read_text())
  if not switches:
    return None
  wall, sim, t = run["joint_wall_time"], run["joint_time"], float(switches[-1])
  if wall[0] <= t <= wall[-1]:
    return float(np.interp(t, wall, sim))
  near = slice(0, 500) if t < wall[0] else slice(-500, None)  # the recorder missed it: extrapolate
  return float(np.polyfit(wall[near] - t, sim[near], 1)[1])


def aligned_start(run, ref):
  """First joint sample plus the lag in [0, MAX_START_LAG_S] that best matches the reference's first ALIGN_S."""
  i = np.arange(min(int(ALIGN_S * FPS), len(ref["joint_pos"])))
  t0 = run["joint_time"][0]
  lags = np.arange(0, MAX_START_LAG_S + 1e-9, 0.005)
  q = [resample(run["joint_time"], run["joint_pos"], t0 + lag + i / FPS) for lag in lags]
  errors = [np.abs(qi - ref["joint_pos"][i]).mean() for qi in q]
  return float(t0 + lags[int(np.argmin(errors))])


def policy_start(run, ref, override, log):
  """Sim time of the policy start, and how it was found."""
  if override is not None:
    return override, "override"
  start = log_start(run, log) if log else None
  if start is not None:
    return start, "sim_log"
  return aligned_start(run, ref), "alignment"


def tracking_failure(ref, robot, anchor_quat, grace_s):
  """First frame after grace_s where one of BeyondMimic's termination rules fires, and the rule (None, "" if none)."""
  n, names = len(robot), list(ref["body_names"])
  a, ee = names.index(TRACKING_ANCHOR_BODY), [names.index(b) for b in TRACKING_END_EFFECTORS]
  ref_z = ref["body_pos_w"][:n, :, 2]
  rules = {
    "tracking:anchor_height": np.abs(ref_z[:, a] - robot[:, a, 2]) > TRACKING_ANCHOR_HEIGHT_M,
    "tracking:anchor_orientation":
      np.abs(gravity_z(ref["body_quat_w"][:n, a]) - gravity_z(anchor_quat)) > TRACKING_ANCHOR_GRAVITY,
    "tracking:end_effector_height": np.any(np.abs(ref_z[:, ee] - robot[:, ee, 2]) > TRACKING_END_EFFECTOR_HEIGHT_M, 1),
  }
  failed = np.any(list(rules.values()), axis=0)
  failed[: round(grace_s * FPS)] = False
  if not failed.any():
    return None, ""
  i = int(np.argmax(failed))
  return i, next(rule for rule, fired in rules.items() if fired[i])


def down_spells(t, low):
  """(start, end) of each stretch of `low`; end is the first sample back up, or the last sample."""
  edges = np.flatnonzero(np.diff(np.concatenate([[0], low.astype(int), [0]])))
  return [(t[a], t[min(b, len(t) - 1)]) for a, b in zip(edges[::2], edges[1::2])]


def real_fall(t, head_z, motion_end):
  """When the head went down (None if never) and whether that was after the motion."""
  low = head_z < REAL_FALL_HEAD_HEIGHT_M
  for down, up in down_spells(t, low):
    held = up - down > REAL_FALL_TIME_S or (up == t[-1] and low[-1])
    if down <= motion_end and (held or up > motion_end):
      return down, False
    if down > motion_end and held:
      return down, True
  return None, False


def tracking_errors(run, ref, times, robot, anchor_quat):
  """Per-frame MPKPE, r-MPKPE (as mjlab), joint error and drift."""
  n = len(times)
  joint_err = np.abs(resample(run["joint_time"], run["joint_pos"], times) - ref["joint_pos"][:n]).mean(axis=1)

  # align the reference with the robot's anchor at the start
  a = list(ref["body_names"]).index(TRACKING_ANCHOR_BODY)
  ref_pos, ref_quat = ref["body_pos_w"][:n], ref["body_quat_w"][:n, a]
  flat = np.array([1, 1, 0])  # move in x, y only; keep the reference heights
  turn = yaw(anchor_quat[0]) - yaw(ref_quat[0])
  ref_on_robot = turn_xy(ref_pos - ref_pos[0, a] * flat, turn) + robot[0, a] * flat
  mpkpe = np.linalg.norm(ref_on_robot - robot, axis=-1).mean(axis=1)
  drift = np.linalg.norm(ref_on_robot[:, a, :2] - robot[:, a, :2], axis=1)

  r_mpkpe = np.zeros(n)
  for i in range(n):
    rel = turn_xy(ref_pos[i] - ref_pos[i, a], yaw(anchor_quat[i]) - yaw(ref_quat[i]))
    anchor = np.append(robot[i, a, :2], ref_pos[i, a, 2])
    r_mpkpe[i] = np.linalg.norm(rel + anchor - robot[i], axis=-1).mean()
  return {"mpkpe": mpkpe, "r_mpkpe": r_mpkpe, "joint": joint_err, "drift": drift}


def estimator_errors(run, ref, times, start):
  """Drift in the state estimator's frame, and the estimator's gap to the true head position."""
  head = resample(run["base_time"], run["base_pos"], times)
  est = resample(run["est_time"], run["est_pos"], times)
  gap = np.linalg.norm((est[:, :2] - est[0, :2]) - (head[:, :2] - head[0, :2]), axis=1)
  pelvis = list(ref["body_names"]).index("pelvis")
  k = min(np.searchsorted(run["est_time"], start), len(run["est_time"]) - 1)
  turn = yaw(run["est_quat"][k]) - yaw(ref["body_quat_w"][0, pelvis])
  ref_pelvis = ref["body_pos_w"][: len(times), pelvis] - ref["body_pos_w"][0, pelvis]
  drift = np.linalg.norm(turn_xy(ref_pelvis, turn)[:, :2] + est[0, :2] - est[:, :2], axis=1)
  return drift, gap, head[:, 2]


def r4(x):
  return round(float(x), 4)


def seconds(t):
  return None if t is None else round(float(t), 2)


def analyze(path, ref, model, override=None, grace_s=GRACE_S, logs_dir=None):
  run = load_run(path, ref["joint_names"])
  log = Path(logs_dir, Path(path).stem + ".sim.log") if logs_dir else None
  start, method = policy_start(run, ref, override, log)
  first = run["joint_time"][0]
  motion_s = (len(ref["joint_pos"]) - 1) / FPS
  covered = min(motion_s, run["joint_time"][-1] - start)
  times = start + np.arange(int(np.floor(covered * FPS + 1e-6)) + 1) / FPS

  after_step = times + 1 / FPS  # robot one control step after each reference frame, as in mjlab and the harness
  robot, anchor_quat = robot_bodies(model, run, after_step, ref["body_names"])
  fail, reason = tracking_failure(ref, robot, anchor_quat, grace_s)
  err = tracking_errors(run, ref, after_step, robot, anchor_quat)
  pre = {k: v[: max(fail, 1)] if fail is not None else v for k, v in err.items()}
  est_drift, est_gap, head = estimator_errors(run, ref, times, start)

  head_t, head_z = run["base_time"] - start, run["base_pos"][:, 2]
  fell_at, after = real_fall(head_t, head_z, motion_s)
  complete = bool(run["joint_time"][-1] - start >= motion_s)
  success = complete and fail is None
  return {
    "run": path,
    "policy_start_s": round(float(start), 3),
    "start_method": method,
    "first_joint_sample_s": round(float(first), 3),
    "start_lag_s": round(float(start - first), 3),
    "motion_s": round(motion_s, 2),
    "covered_s": round(float(covered), 2),
    "complete": complete,
    "startup_drop": bool(np.interp(first, run["base_time"], head_z) < STARTUP_DROP_HEAD_M),
    "invalid_recording": bool(first > LATE_RECORDING_S),
    "tracking_failure": fail is not None,
    "tracking_failure_time_s": None if fail is None else round(fail / FPS, 2),
    "tracking_failure_reason": reason,
    "success": success,
    "success_strict": success and bool(err["mpkpe"].max() <= STRICT_MPKPE_M),
    "fell": fell_at is not None and not after,
    "fell_time_s": None if after else seconds(fell_at),
    "fell_after_motion": after,
    "fell_after_motion_time_s": seconds(fell_at) if after else None,
    "mpkpe_m": r4(err["mpkpe"].mean()),
    "max_mpkpe_m": r4(err["mpkpe"].max()),
    "r_mpkpe_m": r4(err["r_mpkpe"].mean()),
    "max_r_mpkpe_m": r4(err["r_mpkpe"].max()),
    "joint_mae_rad": r4(err["joint"].mean()),
    "joint_max_frame_mae_rad": r4(err["joint"].max()),
    "pre_failure_mpkpe_m": r4(pre["mpkpe"].mean()),
    "pre_failure_r_mpkpe_m": r4(pre["r_mpkpe"].mean()),
    "pre_failure_joint_mae_rad": r4(pre["joint"].mean()),
    "drift_mean_m": round(float(err["drift"].mean()), 3),
    "drift_max_m": round(float(err["drift"].max()), 3),
    "est_frame_drift_mean_m": round(float(est_drift.mean()), 3),
    "est_frame_drift_max_m": round(float(est_drift.max()), 3),
    "estimator_gap_max_m": round(float(est_gap.max()), 3),
    "min_head_height_m": round(float(head.min()), 3),
  }


def launches(path, tries_dir):
  tries = Path(tries_dir or ".", Path(path).stem + ".tries")
  return int(tries.read_text()) if tries_dir and tries.exists() else 1


def summarize(name, results, tries_dir, grace_s):
  """Successes, real falls and mean errors of one policy's runs, start-up drops and invalid recordings left out."""
  kept = [r for r in results if not r["startup_drop"] and not r["invalid_recording"]]
  n, wins, falls = len(kept), sum(r["success"] for r in kept), sum(r["fell"] for r in kept)
  after = [r["fell_after_motion_time_s"] - r["motion_s"] for r in kept if r["fell_after_motion"]]
  after_s = round(float(np.median(after)), 2) if after else None
  launched = sum(launches(r["run"], tries_dir) for r in results)
  summary = {
    "policy": name,
    "runs": len(results),
    "startup_drops": sum(r["startup_drop"] for r in results),
    "invalid_recordings": sum(r["invalid_recording"] for r in results),
    "scored": n,
    "launches": launched,
    "successes": wins,
    "falls": falls,
    "falls_after_motion": len(after),
    "median_fall_after_motion_s": after_s,
    "line": f"{wins}/{n} successes, {falls}/{n} falls, from {launched} launches; "
    f"{len(after)}/{n} fell after the motion ended (median {after_s} s after the last frame)",
    "tracking_failure_times_s": [r["tracking_failure_time_s"] for r in kept],
    "start_methods": sorted({r["start_method"] for r in results}),
    "grace_s": grace_s,
  }
  for key in MEAN_KEYS:
    summary[f"mean_{key}"] = r4(np.mean([r[key] for r in kept])) if kept else None
  return summary


def main():
  args = parse_args()
  starts = args.policy_start_s or [None]
  starts = starts * len(args.runs) if len(starts) == 1 else starts
  ref = dict(np.load(args.reference))
  model = mujoco.MjModel.from_xml_path(args.model_xml)
  results = [analyze(path, ref, model, start, args.grace_s, args.logs_dir) for path, start in zip(args.runs, starts)]
  summary = summarize(Path(args.reference).parent.name, results, args.tries_dir, args.grace_s)
  for line in [*results, summary]:
    print(json.dumps(line))
  if args.output:
    with open(args.output, "w") as f:
      json.dump({"summary": summary, "runs": results}, f, indent=2)


if __name__ == "__main__":
  main()
