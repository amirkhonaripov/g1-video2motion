"""Compare ROS 2 + MuJoCo runs (.npz from bag_to_npz.py) with the reference motion."""

import argparse
import json
import math

import mujoco
import numpy as np

G1_XML = "/opt/ros/jazzy/share/unitree_description/mjcf/g1.xml"
FPS = 50.0
FALL_HEIGHT_M = 0.5  # head (lidar) below this...
FALL_TIME_S = 2.0  # ...for longer than this counts as a fall
STRICT_MPKPE_M = 0.15  # PHUMA's strict success, same as eval_mjlab.py


def parse_args():
  parser = argparse.ArgumentParser(description="Analyze ROS 2 sim-to-sim runs")
  parser.add_argument("runs", nargs="+", help="run .npz files")
  parser.add_argument(
    "--reference",
    default="runs/onnx/demo/reference.npz",
    help="reference motion saved by export_onnx.py",
  )
  parser.add_argument("--output", help="write the results as JSON")
  return parser.parse_args()


def yaw(quat):
  w, x, y, z = quat
  return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


def turn_xy(vectors, angle):
  # rotate xy about z
  c, s = math.cos(angle), math.sin(angle)
  out = vectors.copy()
  out[..., 0] = c * vectors[..., 0] - s * vectors[..., 1]
  out[..., 1] = s * vectors[..., 0] + c * vectors[..., 1]
  return out


def resample(times, values, new_times):
  return np.stack(
    [np.interp(new_times, times, values[:, k]) for k in range(values.shape[1])],
    axis=1,
  )


def find_start(run, ref_q):
  # policy switch: best match of the first 30 s of the reference
  n = int(30 * FPS)
  times = run["joint_time"]
  best_start, best_err = times[0], np.inf
  for start in np.arange(times[0], times[-1] - 30, 0.02):
    q = resample(times, run["joint_pos"], start + np.arange(n) / FPS)
    err = np.abs(q - ref_q[:n]).mean()
    if err < best_err:
      best_start, best_err = start, err
  return best_start


def longest_run(flags):
  longest, current = 0, 0
  for flag in flags:
    current = current + 1 if flag else 0
    longest = max(longest, current)
  return longest


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
  # forward kinematics
  data = mujoco.MjData(model)
  adr = [model.joint(name).qposadr[0] for name in run["joint_names"]]
  ids = [model.body(name).id for name in body_names]
  torso = model.body("torso_link").id
  joints = resample(run["joint_time"], run["joint_pos"], times)
  base = resample(run["base_time"], run["base_pos"], times)
  k = np.minimum(np.searchsorted(run["base_time"], times), len(run["base_time"]) - 1)

  pos, torso_quat = [], []
  for i in range(len(times)):
    set_pose(model, data, run, adr, base[i], run["base_quat"][k[i]], joints[i])
    mujoco.mj_kinematics(model, data)
    pos.append(data.xpos[ids].copy())
    torso_quat.append(data.xquat[torso].copy())
  return np.array(pos), np.array(torso_quat)


def analyze(path, ref, model):
  run = dict(np.load(path))
  order = [list(run["joint_names"]).index(n) for n in ref["joint_names"]]
  run["joint_pos"] = run["joint_pos"][:, order]
  run["joint_names"] = ref["joint_names"]

  ref_q = ref["joint_pos"]
  start = find_start(run, ref_q)
  covered = min(start + (len(ref_q) - 1) / FPS, run["joint_time"][-1]) - start
  n = int(covered * FPS) + 1
  times = start + np.arange(n) / FPS

  joint_err = np.abs(resample(run["joint_time"], run["joint_pos"], times) - ref_q[:n])
  head = resample(run["base_time"], run["base_pos"], times)
  est = resample(run["est_time"], run["est_pos"], times)
  robot, robot_torso_quat = robot_bodies(model, run, times, ref["body_names"])

  # align the reference with the robot's torso at the switch
  torso = list(ref["body_names"]).index("torso_link")
  ref_pos, ref_quat = ref["body_pos_w"][:n], ref["body_quat_w"][:n, torso]
  flat = np.array([1, 1, 0])  # move in x, y only; keep the reference heights
  turn = yaw(robot_torso_quat[0]) - yaw(ref_quat[0])
  ref_on_robot = (
    turn_xy(ref_pos - ref_pos[0, torso] * flat, turn) + robot[0, torso] * flat
  )
  mpkpe = np.linalg.norm(ref_on_robot - robot, axis=-1).mean(axis=1)
  drift = np.linalg.norm(ref_on_robot[:, torso, :2] - robot[:, torso, :2], axis=1)

  # root-relative, as mjlab
  r_mpkpe = np.zeros(n)
  for i in range(n):
    rel = turn_xy(
      ref_pos[i] - ref_pos[i, torso], yaw(robot_torso_quat[i]) - yaw(ref_quat[i])
    )
    anchor = np.append(robot[i, torso, :2], ref_pos[i, torso, 2])
    r_mpkpe[i] = np.linalg.norm(rel + anchor - robot[i], axis=-1).mean()

  est_gap = np.linalg.norm(
    (est[:, :2] - est[0, :2]) - (head[:, :2] - head[0, :2]), axis=1
  )

  # drift in the estimator's frame
  pelvis = list(ref["body_names"]).index("pelvis")
  k = min(np.searchsorted(run["est_time"], start), len(run["est_time"]) - 1)
  est_turn = yaw(run["est_quat"][k]) - yaw(ref["body_quat_w"][0, pelvis])
  ref_pelvis = ref_pos[:, pelvis] - ref_pos[0, pelvis]
  ref_on_est = turn_xy(ref_pelvis, est_turn)[:, :2] + est[0, :2]
  est_drift = np.linalg.norm(ref_on_est - est[:, :2], axis=1)
  complete = bool(covered >= (len(ref_q) - 1) / FPS - 0.1)
  fell = bool(longest_run(head[:, 2] < FALL_HEIGHT_M) / FPS > FALL_TIME_S)
  return {
    "run": path,
    "policy_start_s": round(float(start), 2),
    "covered_s": round(float(covered), 2),
    "complete": complete,
    "fell": fell,
    "success_strict": complete and not fell and bool(mpkpe.max() <= STRICT_MPKPE_M),
    "mpkpe_m": round(float(mpkpe.mean()), 4),
    "max_mpkpe_m": round(float(mpkpe.max()), 4),
    "r_mpkpe_m": round(float(r_mpkpe.mean()), 4),
    "max_r_mpkpe_m": round(float(r_mpkpe.max()), 4),
    "joint_mae_rad": round(float(joint_err.mean()), 4),
    "joint_max_frame_mae_rad": round(float(joint_err.mean(axis=1).max()), 4),
    "drift_mean_m": round(float(drift.mean()), 3),
    "drift_max_m": round(float(drift.max()), 3),
    "est_frame_drift_mean_m": round(float(est_drift.mean()), 3),
    "est_frame_drift_max_m": round(float(est_drift.max()), 3),
    "estimator_gap_max_m": round(float(est_gap.max()), 3),
    "min_head_height_m": round(float(head[:, 2].min()), 3),
  }


def main():
  args = parse_args()
  ref = np.load(args.reference)
  model = mujoco.MjModel.from_xml_path(G1_XML)
  results = [analyze(path, ref, model) for path in args.runs]
  for r in results:
    print(json.dumps(r))
  if args.output:
    with open(args.output, "w") as f:
      json.dump(results, f, indent=2)


if __name__ == "__main__":
  main()
