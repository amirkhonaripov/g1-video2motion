"""G1 motion (GMR .pkl or mjlab .npz) -> SONIC tracker input (.npz)."""

import argparse
import pickle
import re
from pathlib import Path

import numpy as np

from scripts.g1 import JOINT_NAMES, VITH_JOINT_NAMES


def parse_args():
  parser = argparse.ArgumentParser(description="G1 motion -> SONIC tracker .npz")
  parser.add_argument("input_file", help="GMR-style .pkl or mjlab motion .npz")
  parser.add_argument("--output-file", help="default: data/motions/sonic/<clip>_<method>[_s2|_s3][_grounded].npz")
  args = parser.parse_args()
  if args.output_file is None:
    if not args.input_file.endswith(".npz"):
      parser.error("give --output-file for a .pkl input")
    args.output_file = default_output(args.input_file)
  return args


def default_output(motion_file):
  """data/motions/<method>/<clip>[_s2|_s3][_grounded].npz -> data/motions/sonic/<clip>_<method>[...].npz"""
  path = Path(motion_file)
  if path.parent.name == "demo":
    return "data/motions/sonic/lafan1_dance.npz"
  clip, rest = re.fullmatch(r"(.+?)((?:_s\d)?(?:_grounded)?)", path.stem).groups()
  return f"data/motions/sonic/{clip}_{path.parent.name}{rest}.npz"


def load_motion(path):
  if path.endswith(".npz"):
    m = np.load(path)  # mjlab motion: body 0 is the pelvis
    return m["joint_pos"], m["body_pos_w"][:, 0], m["body_quat_w"][:, 0], float(m["fps"][0])
  with open(path, "rb") as f:
    m = pickle.load(f)
  return m["dof_pos"], m["root_pos"], m["root_rot"][:, [3, 0, 1, 2]], float(m["fps"])  # xyzw -> wxyz


def main():
  args = parse_args()
  joint_pos, root_pos, root_quat, fps = load_motion(args.input_file)
  order = [JOINT_NAMES.index(name) for name in VITH_JOINT_NAMES]  # IsaacLab order
  frames = len(joint_pos)
  Path(args.output_file).parent.mkdir(parents=True, exist_ok=True)
  np.savez(
    args.output_file,
    joint_pos=joint_pos[:, order],
    root_pos_w=root_pos,
    root_quat_w=root_quat,
    body_pos_w=np.zeros((frames, 30, 3)),  # the tracker recomputes these from the joints
    fps=np.array(fps),
  )
  print(f"[INFO] {frames} frames at {fps:g} fps -> {args.output_file}")


if __name__ == "__main__":
  main()
