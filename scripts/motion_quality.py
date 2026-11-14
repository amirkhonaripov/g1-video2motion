"""Measure common artifacts in mjlab motion files (.npz), before any tracking."""

import argparse
import json

import mujoco
import numpy as np
from gmr_to_npz import JOINT_NAMES

G1_XML = "/opt/ros/jazzy/share/unitree_description/mjcf/g1.xml"
FEET = ["left_ankle_roll_link", "right_ankle_roll_link"]
CONTACT_M = 0.03  # a foot counts as planted within this height of its lowest point


def parse_args():
  parser = argparse.ArgumentParser(description="Motion artifacts of mjlab motions")
  parser.add_argument("motions", nargs="+", help="mjlab motion .npz files")
  parser.add_argument("--output", help="write the results as JSON")
  return parser.parse_args()


def foot_positions(model, motion):
  # forward kinematics
  data = mujoco.MjData(model)
  adr = [model.joint(name).qposadr[0] for name in JOINT_NAMES]
  ids = [model.body(name).id for name in FEET]
  feet = []
  for i in range(len(motion["joint_pos"])):
    data.qpos[:3] = motion["body_pos_w"][i, 0]
    data.qpos[3:7] = motion["body_quat_w"][i, 0]
    data.qpos[adr] = motion["joint_pos"][i]
    mujoco.mj_kinematics(model, data)
    feet.append(data.xpos[ids].copy())
  return np.array(feet)  # (T, 2, 3)


def foot_sliding(feet, fps):
  # foot speed while planted
  speeds = []
  for f in range(2):
    z = feet[:, f, 2]
    planted = z[:-1] < z.min() + CONTACT_M
    speed = np.linalg.norm(np.diff(feet[:, f, :2], axis=0), axis=1) * fps
    speeds.append(speed[planted])
  return np.concatenate(speeds)


def analyze(path, model):
  motion = np.load(path)
  fps = float(motion["fps"][0])
  q = motion["joint_pos"]
  low, high = model.jnt_range[[model.joint(n).id for n in JOINT_NAMES]].T
  outside = (q < low - 1e-3) | (q > high + 1e-3)
  accel = np.diff(q, n=2, axis=0) * fps**2
  feet = foot_positions(model, motion)
  slide = foot_sliding(feet, fps)
  floor = feet[0, :, 2].min()  # lowest foot at the start = the floor
  return {
    "motion": path,
    "seconds": round(len(q) / fps, 2),
    "frames_outside_joint_limits": round(float(outside.any(axis=1).mean()), 3),
    "max_joint_speed_rad_s": round(float(np.abs(motion["joint_vel"]).max()), 2),
    "mean_joint_accel_rad_s2": round(float(np.abs(accel).mean()), 1),
    "foot_sliding_mean_m_s": round(float(slide.mean()), 3),
    "foot_below_start_floor_max_m": round(float(max(0.0, floor - feet[:, :, 2].min())), 3),
    "pelvis_height_min_max_m": [
      round(float(motion["body_pos_w"][:, 0, 2].min()), 3),
      round(float(motion["body_pos_w"][:, 0, 2].max()), 3),
    ],
  }


def main():
  args = parse_args()
  model = mujoco.MjModel.from_xml_path(G1_XML)
  results = [analyze(path, model) for path in args.motions]
  for r in results:
    print(json.dumps(r))
  if args.output:
    with open(args.output, "w") as f:
      json.dump(results, f, indent=2)


if __name__ == "__main__":
  main()
