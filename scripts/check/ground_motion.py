"""Put a motion's feet back on the floor: shift it down by a slowly varying floor estimate, so short jumps stay."""

import argparse

import numpy as np
from scipy.ndimage import minimum_filter1d, uniform_filter1d

ANKLES = [6, 12]  # left/right ankle_roll_link; motion files hold no body names
ANKLE_ON_FLOOR = 0.04  # ankle height (m) with the foot flat, as in LAFAN1


def parse_args():
  parser = argparse.ArgumentParser(description="Ground a motion")
  parser.add_argument("input_file", help="mjlab motion .npz")
  parser.add_argument("--output-file", help="default: <input_file without .npz>_grounded.npz")
  parser.add_argument("--window-s", type=float, default=1.0, help="jumps shorter than this stay")
  args = parser.parse_args()
  args.output_file = args.output_file or args.input_file.removesuffix(".npz") + "_grounded.npz"
  return args


def floor_offset(body_pos_w, fps, window_s):
  foot = body_pos_w[:, ANKLES, 2].min(1)
  n = max(1, round(window_s * fps))
  floor = uniform_filter1d(minimum_filter1d(foot, n, mode="nearest"), n, mode="nearest")
  return floor - ANKLE_ON_FLOOR


def main():
  args = parse_args()
  motion = dict(np.load(args.input_file))
  fps = float(motion["fps"][0])
  offset = floor_offset(motion["body_pos_w"], fps, args.window_s)
  motion["body_pos_w"][..., 2] -= offset[:, None]
  motion["body_lin_vel_w"][..., 2] -= np.gradient(offset, 1 / fps)[:, None]
  print(f"[INFO] shifted down by {offset.min():.3f} to {offset.max():.3f} m (mean {offset.mean():.3f})")
  np.savez(args.output_file, **motion)
  print(f"[INFO] -> {args.output_file}")


if __name__ == "__main__":
  main()
