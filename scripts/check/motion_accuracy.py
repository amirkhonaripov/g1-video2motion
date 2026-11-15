"""How close each method's G1 motion is to the same dance from AIST++ motion capture, retargeted by GMR."""

import argparse
import json

import numpy as np

from scripts.g1 import METHODS, turn_xy, yaw

CLIPS = ["pop", "jazz"]


def parse_args():
  parser = argparse.ArgumentParser(description="Motion accuracy against motion capture")
  parser.add_argument("--motions", default="data/motions")
  parser.add_argument("--output-file", default="results/motion_accuracy.json")
  parser.add_argument("--max-lag-s", type=float, default=0.3, help="search for a time offset up to this")
  return parser.parse_args()


def trim(x, k):
  return x[k:len(x) - k]


def local_bodies(m):
  """Body positions relative to the pelvis, in the pelvis's heading frame."""
  rel = m["body_pos_w"] - m["body_pos_w"][:, :1]
  return np.stack([turn_xy(rel[:, b], -yaw(m["body_quat_w"][:, 0])) for b in range(rel.shape[1])], 1)


def joint_error(a, b):
  return np.degrees(np.abs(a["joint_pos"] - b["joint_pos"]).mean())


def shift(m, lag):
  return {k: np.roll(v, lag, 0) for k, v in m.items() if np.ndim(v) and len(v) == len(m["joint_pos"])}


def best_lag(m, ref, max_lag):
  lags = range(-max_lag, max_lag + 1)
  errs = [trim(np.abs(np.roll(m["joint_pos"], lag, 0) - ref["joint_pos"]), max_lag).mean() for lag in lags]
  return lags[int(np.argmin(errs))]


def root_errors(m, ref):
  d_yaw = yaw(ref["body_quat_w"][:1, 0]) - yaw(m["body_quat_w"][:1, 0])
  xy = turn_xy(m["body_pos_w"][:, 0] - m["body_pos_w"][:1, 0], np.repeat(d_yaw, len(m["joint_pos"])))
  xy_err = np.linalg.norm(xy[:, :2] - (ref["body_pos_w"][:, 0, :2] - ref["body_pos_w"][:1, 0, :2]), axis=-1)
  heading = np.unwrap(yaw(m["body_quat_w"][:, 0]) + d_yaw) - np.unwrap(yaw(ref["body_quat_w"][:, 0]))
  return 100 * xy_err.mean(), np.degrees(np.abs(heading).mean())


def compare(m, ref, max_lag, fps):
  lag = best_lag(m, ref, max_lag)
  m = shift(m, lag)
  m, ref = ({k: trim(v, max_lag) for k, v in x.items()} for x in (m, ref))
  pose = 100 * np.linalg.norm(local_bodies(m) - local_bodies(ref), axis=-1).mean()
  height = 100 * np.abs(m["body_pos_w"][:, 0, 2] - ref["body_pos_w"][:, 0, 2]).mean()
  xy, heading = root_errors(m, ref)
  return {"lag_s": lag / fps, "joint_error_deg": joint_error(m, ref), "pose_error_cm": pose,
          "pelvis_height_error_cm": height, "path_error_cm": xy, "heading_error_deg": heading}


def load(path, fps=None):
  m = dict(np.load(path))
  if fps is not None and float(m["fps"][0]) != fps:
    raise ValueError(f"{path}: {m['fps'][0]} fps, expected {fps}")
  return m


def main():
  args = parse_args()
  results = {}
  for clip in CLIPS:
    ref = load(f"{args.motions}/aistpp/{clip}.npz")
    fps = float(ref["fps"][0])
    max_lag = round(args.max_lag_s * fps)
    for label, src, seed in METHODS:
      m = load(f"{args.motions}/{src}/{clip}{seed}.npz", fps)
      n = min(len(m["joint_pos"]), len(ref["joint_pos"]))
      r = compare({k: v[:n] for k, v in m.items() if np.ndim(v) and len(v) >= n},
                  {k: v[:n] for k, v in ref.items() if np.ndim(v) and len(v) >= n}, max_lag, fps)
      results[f"{clip}/{label}"] = r = {k: float(v) for k, v in r.items()}
      print(clip, label, {k: round(v, 2) for k, v in r.items()})
  with open(args.output_file, "w") as f:
    json.dump(results, f, indent=2)


if __name__ == "__main__":
  main()
