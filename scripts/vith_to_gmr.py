"""Turn a ViT-H output (.npz) into GMR's pickle format, so gmr_to_npz.py can convert it."""

import argparse
import pickle

import numpy as np
from gmr_to_npz import JOINT_NAMES

# ViT-H joint order (IsaacLab)
VITH_JOINT_NAMES = [
  "left_hip_pitch_joint",
  "right_hip_pitch_joint",
  "waist_yaw_joint",
  "left_hip_roll_joint",
  "right_hip_roll_joint",
  "waist_roll_joint",
  "left_hip_yaw_joint",
  "right_hip_yaw_joint",
  "waist_pitch_joint",
  "left_knee_joint",
  "right_knee_joint",
  "left_shoulder_pitch_joint",
  "right_shoulder_pitch_joint",
  "left_ankle_pitch_joint",
  "right_ankle_pitch_joint",
  "left_shoulder_roll_joint",
  "right_shoulder_roll_joint",
  "left_ankle_roll_joint",
  "right_ankle_roll_joint",
  "left_shoulder_yaw_joint",
  "right_shoulder_yaw_joint",
  "left_elbow_joint",
  "right_elbow_joint",
  "left_wrist_roll_joint",
  "right_wrist_roll_joint",
  "left_wrist_pitch_joint",
  "right_wrist_pitch_joint",
  "left_wrist_yaw_joint",
  "right_wrist_yaw_joint",
]
VITH_FPS = 30  # ViT-H resamples every video to 30 fps


def parse_args():
  parser = argparse.ArgumentParser(description="ViT-H .npz -> GMR .pkl")
  parser.add_argument("input_file", help="ViT-H output .npz")
  parser.add_argument("--output-file", required=True, help="GMR-style .pkl")
  return parser.parse_args()


def main():
  args = parse_args()
  vith = np.load(args.input_file)
  order = [VITH_JOINT_NAMES.index(name) for name in JOINT_NAMES]
  motion = {
    "fps": VITH_FPS,
    "root_pos": vith["root_pos_w"],
    "root_rot": vith["root_quat_w"][:, [1, 2, 3, 0]],  # wxyz -> xyzw
    "dof_pos": vith["joint_pos"][:, order],
  }
  with open(args.output_file, "wb") as f:
    pickle.dump(motion, f)
  print(f"[INFO] {len(motion['dof_pos'])} frames -> {args.output_file}")


if __name__ == "__main__":
  main()
