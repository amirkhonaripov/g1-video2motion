"""How close each method's G1 motion is to the same dance from AIST++ motion capture, retargeted by GMR."""

import argparse
import json

import numpy as np

CLIPS = ["pop", "jazz"]
MOTIONS = [("GVHMR + GMR", "gmr", ""), ("ViT-H sample 1", "vith", ""), ("ViT-H sample 2", "vith", "_s1"),
           ("ViT-H sample 3", "vith", "_s2")]


def parse_args():
  parser = argparse.ArgumentParser(description="Motion accuracy against motion capture")
  parser.add_argument("--motions", default="data/motions")
  parser.add_argument("--output-file", default="results/routes/motion_accuracy.json")
  parser.add_argument("--max-lag-s", type=float, default=0.3, help="search for a time offset up to this")
  return parser.parse_args()


def yaw(quat):
  w, x, y, z = quat.T
  return np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


def rotate_z(v, angle):
  c, s = np.cos(angle), np.sin(angle)
  return np.stack([c * v[..., 0] - s * v[..., 1], s * v[..., 0] + c * v[..., 1], v[..., 2]], -1)


def local_bodies(m):
  """Body positions relative to the pelvis, in the pelvis's heading frame."""
  rel = m["body_pos_w"] - m["body_pos_w"][:, :1]
  return np.stack([rotate_z(rel[:, b], -yaw(m["body_quat_w"][:, 0])) for b in range(rel.shape[1])], 1)


def joint_error(a, b):
  return np.degrees(np.abs(a["joint_pos"] - b["joint_pos"]).mean())


def shift(m, lag):
  return {k: np.roll(v, lag, 0) for k, v in m.items() if np.ndim(v) and len(v) == len(m["joint_pos"])}


def best_lag(m, ref, max_lag):
  lags = range(-max_lag, max_lag + 1)
  errs = [np.abs(np.roll(m["joint_pos"], lag, 0) - ref["joint_pos"])[max_lag:-max_lag].mean() for lag in lags]
  return lags[int(np.argmin(errs))]


def root_errors(m, ref):
  d_yaw = yaw(ref["body_quat_w"][:1, 0]) - yaw(m["body_quat_w"][:1, 0])
  xy = rotate_z(m["body_pos_w"][:, 0] - m["body_pos_w"][:1, 0], np.repeat(d_yaw, len(m["joint_pos"])))
  xy_err = np.linalg.norm(xy[:, :2] - (ref["body_pos_w"][:, 0, :2] - ref["body_pos_w"][:1, 0, :2]), axis=-1)
  heading = np.unwrap(yaw(m["body_quat_w"][:, 0]) + d_yaw) - np.unwrap(yaw(ref["body_quat_w"][:, 0]))
  return 100 * xy_err.mean(), np.degrees(np.abs(heading).mean())


def compare(m, ref, max_lag):
  lag = best_lag(m, ref, max_lag)
  m = shift(m, lag)
  keep = slice(max_lag, -max_lag)
  m, ref = ({k: v[keep] for k, v in x.items()} for x in (m, ref))
  pose = 100 * np.linalg.norm(local_bodies(m) - local_bodies(ref), axis=-1).mean()
  height = 100 * np.abs(m["body_pos_w"][:, 0, 2] - ref["body_pos_w"][:, 0, 2]).mean()
  xy, heading = root_errors(m, ref)
  return {"lag_s": lag / 50, "joint_error_deg": joint_error(m, ref), "pose_error_cm": pose,
          "pelvis_height_error_cm": height, "path_error_cm": xy, "heading_error_deg": heading}


def main():
  args = parse_args()
  max_lag = round(args.max_lag_s * 50)
  results = {}
  for clip in CLIPS:
    ref = dict(np.load(f"{args.motions}/aistpp/{clip}.npz"))
    for label, src, seed in MOTIONS:
      m = dict(np.load(f"{args.motions}/{src}/{clip}{seed}.npz"))
      n = min(len(m["joint_pos"]), len(ref["joint_pos"]))
      r = compare({k: v[:n] for k, v in m.items() if np.ndim(v) and len(v) >= n},
                  {k: v[:n] for k, v in ref.items() if np.ndim(v) and len(v) >= n}, max_lag)
      results[f"{clip}/{label}"] = r = {k: float(v) for k, v in r.items()}
      print(clip, label, {k: round(v, 2) for k, v in r.items()})
  with open(args.output_file, "w") as f:
    json.dump(results, f, indent=2)


if __name__ == "__main__":
  main()
