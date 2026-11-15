"""Turn a ViT-H output (.npz) into GMR's pickle format, so gmr_to_npz can convert it."""

import argparse
import pickle

import numpy as np

from scripts.g1 import JOINT_NAMES, VITH_JOINT_NAMES

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
