"""Measure common artifacts in mjlab motion files (.npz), before any tracking."""

import argparse
import json

import mujoco
import numpy as np

from scripts.g1 import G1_XML, JOINT_NAMES

FEET = ["left_ankle_roll_link", "right_ankle_roll_link"]
CONTACT_M = 0.03  # a foot counts as planted within this height of its lowest point
FLOAT_M = 0.05  # floating: both feet this far above the floor (lowest foot in the first second)
STILL_M_S = 0.3  # and the lower foot this still vertically (not mid-jump)
SPEED_WINDOW_S = 0.1  # vertical speed over this window
FLOAT_S = 0.5  # for at least this long


def parse_args():
  parser = argparse.ArgumentParser(description="Motion artifacts of mjlab motions")
  parser.add_argument("motions", nargs="+", help="mjlab motion .npz files")
  parser.add_argument("--output", help="write the results as JSON, e.g. results/motion_quality.json")
  parser.add_argument("--model-xml", default=G1_XML, help="G1 MuJoCo model")
  return parser.parse_args()


def foot_positions(model, motion):
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
  """Foot speed while planted."""
  speeds = []
  for f in range(2):
    z = feet[:, f, 2]
    planted = z[:-1] < z.min() + CONTACT_M
    speed = np.linalg.norm(np.diff(feet[:, f, :2], axis=0), axis=1) * fps
    speeds.append(speed[planted])
  return np.concatenate(speeds)


def vertical_speed(z, fps):
  """Speed (m/s) over SPEED_WINDOW_S around each frame."""
  i = np.arange(len(z))
  half = max(1, round(SPEED_WINDOW_S * fps / 2))
  a, b = np.clip(i - half, 0, len(z) - 1), np.clip(i + half, 0, len(z) - 1)
  return (z[b] - z[a]) / np.maximum(b - a, 1) * fps


def longest_float(lowest_foot, fps):
  """(start s, end s, mean height m) of the longest stretch of floating frames, or None."""
  height = lowest_foot - lowest_foot[: max(1, round(fps))].min()
  floating = (height >= FLOAT_M) & (np.abs(vertical_speed(lowest_foot, fps)) < STILL_M_S)
  best, start = None, None
  for i, up in enumerate([*floating, False]):
    if up and start is None:
      start = i
    elif not up and start is not None:
      if best is None or i - start > best[1] - best[0]:
        best = (start, i)
      start = None
  if best is None:
    return None
  return best[0] / fps, best[1] / fps, float(height[best[0]:best[1]].mean())


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
  stretch = longest_float(feet[:, :, 2].min(axis=1), fps)
  floats = stretch is not None and stretch[1] - stretch[0] >= FLOAT_S
  speed = np.abs(motion["joint_vel"])
  return {
    "motion": path,
    "seconds": round(len(q) / fps, 2),
    "frames_outside_joint_limits": round(float(outside.any(axis=1).mean()), 3),
    "max_joint_speed_rad_s": round(float(speed.max()), 2),
    "fastest_joint": JOINT_NAMES[int(speed.max(axis=0).argmax())],
    "mean_joint_accel_rad_s2": round(float(np.abs(accel).mean()), 1),
    "foot_sliding_mean_m_s": round(float(slide.mean()), 3),
    "foot_below_start_floor_max_m": round(float(max(0.0, floor - feet[:, :, 2].min())), 3),
    "pelvis_height_min_max_m": [
      round(float(motion["body_pos_w"][:, 0, 2].min()), 3),
      round(float(motion["body_pos_w"][:, 0, 2].max()), 3),
    ],
    "floats": floats,
    "float_start_end_s": [round(stretch[0], 2), round(stretch[1], 2)] if floats else None,
    "float_height_m": round(stretch[2], 3) if floats else None,
  }


def line(r):
  """One readable line."""
  text = (f"{r['motion']}: {r['seconds']:.1f} s, "
          f"{100 * r['frames_outside_joint_limits']:.1f}% frames past joint limits, "
          f"fastest joint {r['max_joint_speed_rad_s']:.0f} rad/s ({r['fastest_joint']}), "
          f"foot sliding {100 * r['foot_sliding_mean_m_s']:.0f} cm/s, floats: {'yes' if r['floats'] else 'no'}")
  if r["floats"]:
    start, end = r["float_start_end_s"]
    text += f" ({start:.1f}-{end:.1f} s, {100 * r['float_height_m']:.0f} cm up)"
  return text


def main():
  args = parse_args()
  model = mujoco.MjModel.from_xml_path(args.model_xml)
  results = [analyze(path, model) for path in args.motions]
  for r in results:
    print(line(r))
  if args.output:
    with open(args.output, "w") as f:
      json.dump(results, f, indent=2)


if __name__ == "__main__":
  main()
