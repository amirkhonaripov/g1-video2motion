"""Clip a GMR-style motion (.pkl) into mjlab's soft joint limits, which BeyondMimic's reward penalises."""

import argparse
import pickle

import mujoco
import numpy as np
from gmr_to_npz import JOINT_NAMES

G1_XML = "/opt/ros/jazzy/share/unitree_description/mjcf/g1.xml"
SOFT_FACTOR = 0.9  # mjlab's soft_joint_pos_limit_factor for the G1


def parse_args():
  parser = argparse.ArgumentParser(description="Clip joints into the soft limits")
  parser.add_argument("input_file", help="GMR-style .pkl")
  parser.add_argument("--output-file", required=True)
  return parser.parse_args()


def soft_limits():
  model = mujoco.MjModel.from_xml_path(G1_XML)
  lo, hi = model.jnt_range[[model.joint(n).id for n in JOINT_NAMES]].T
  mid, half = (lo + hi) / 2, (hi - lo) / 2 * SOFT_FACTOR
  return mid - half, mid + half


def main():
  args = parse_args()
  with open(args.input_file, "rb") as f:
    motion = pickle.load(f)
  lo, hi = soft_limits()
  q = motion["dof_pos"]
  clipped = np.clip(q, lo, hi)
  moved = np.abs(clipped - q)
  print(f"[INFO] {100 * (moved > 0).any(1).mean():.0f}% of frames changed, largest change {np.degrees(moved.max()):.1f}°")
  motion["dof_pos"] = clipped
  with open(args.output_file, "wb") as f:
    pickle.dump(motion, f)


if __name__ == "__main__":
  main()
