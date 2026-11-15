"""Results tables from the harness runs (ros2 robot model) and the motion-quality check."""

import argparse
import csv
import glob
import json
import os
import re

import numpy as np

from scripts.g1 import METHODS

HARD = {
  "low_friction": "Low friction",
  "ice": "Ice",
  "push_lateral_medium": "Push from the side",
  "push_forward_hard": "Hard push from behind",
  "push_backward_medium": "Push from the front",
}
CLIPS = {
  "studio_dance": "Studio dance (Pexels)",
  "hiphop_back": "Hip-hop, filmed from behind (Pexels)",
  "jump_kick": "Jump and knee kick (Pexels)",
  "tennis": "Tennis serve (GVHMR demo video)",
  "pop": "AIST++ Pop",
  "jazz": "AIST++ Jazz",
}
G1_TRACKER_DEMO = "fails at 106.7 s"  # ViT-H's own tracker script; no results file
NOTES = """- **Flat ground:** 10 tries that differ only by tiny start noise (±0.02 rad per joint), so they
  nearly always agree; the harder conditions are where tries really differ.
- **Fails:** torso height, torso tilt or a hand/foot height more than 0.25 m from the reference
  (BeyondMimic's rules). **Never more than 15 cm off:** PHUMA's strict success.
- **Pose error (r-MPKPE):** body-part error after placing the reference on the robot: how well the
  pose is copied. **Position error (MPKPE):** the same without moving it: pose plus drift.
- **SONIC (ViT-H) drifts partly by design:** it follows the reference relative to itself, not a world
  position, so its position error grows on long motions while its pose error stays low.
- **ViT-H samples:** ViT-H generates a motion from random noise; samples 1-3 are three draws
  (seeds 42, 1, 2) from the same video.
- **Robot model:** the harness default, `ros2`: the G1 of the ROS 2 stack that runs the real robot."""


def parse_args():
  parser = argparse.ArgumentParser(description="Results tables")
  parser.add_argument("--runs", default="runs/harness", help="harness runs, ros2 robot model")
  parser.add_argument("--latency", default="runs/latency", help="harness runs timing the policies")
  parser.add_argument("--quality", default="results/motion_quality.json")
  parser.add_argument("--mjlab", default="results/mjlab", help="eval_mjlab results")
  parser.add_argument("--demo", default="results/mjlab/demo_dance_mjlab.json", help="eval_mjlab of the LAFAN1 dance")
  parser.add_argument("--demo-ros2", default="results/ros2/demo_dance.json",
                      help="analyze_ros2 of the LAFAN1 dance in the ROS 2 stack")
  parser.add_argument("--timings", default="results/timings.csv")
  parser.add_argument("--output", default="results/tables.md")
  return parser.parse_args()


def load_runs(root):
  # {run: {scenario: {seed: metrics}}}; per-scenario folders (run__scenario) merged
  runs = {}
  for path in sorted(glob.glob(f"{root}/*/summary.json")):
    name = os.path.basename(os.path.dirname(path)).split("__")[0]
    with open(path) as f:
      runs.setdefault(name, {}).update(json.load(f)["trials"])
  return runs


def vals(trials, key):
  return np.array([t[key] for t in trials.values() if t.get(key) is not None], dtype=float)


def outcome(trials):
  falls = vals(trials, "time_to_fall_s")
  if not len(falls):
    return "finishes"
  when = f"{falls.min():.1f} s" if np.ptp(falls) < 0.2 else f"{falls.min():.1f}–{falls.max():.1f} s"
  return f"fails at {when} ({len(falls)}/{len(trials)})"


def finished(trials):
  return len(trials) - len(vals(trials, "time_to_fall_s"))


def cm(trials, key):
  return f"{100 * vals(trials, key).mean():.1f}"


def load_quality(path):
  with open(path) as f:
    rows = json.load(f)
  out = {}
  for r in rows:
    src, name = r["motion"].split("/")[-2:]
    clip, seed = re.fullmatch(r"(.+?)(_s\d)?", name.removesuffix(".npz")).groups()
    out[(clip, src, seed or "")] = r
  return out


def load_timings(path):
  with open(path) as f:
    stages = [r for r in csv.DictReader(f) if r["stage"] in ("video_to_human", "human_to_g1", "video_to_g1")]
  out = {}
  for r in stages:
    clip = out.setdefault(r["clip"], {})
    clip[r["method"]] = clip.get(r["method"], 0.0) + float(r["seconds"])
  return out


def table(header, cols, rows):
  lines = [f"| {header} | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
  lines += [f"| {label} | " + " | ".join(cells) + " |" for label, cells in rows]
  return "\n".join(lines)


def clip_tables(runs, quality, timings, clip):
  cols = [m[0] for m in METHODS]
  scen = [runs[f"sonic_{src}_{clip}{seed}"] for _, src, seed in METHODS]
  ref = [quality[(clip, src, seed)] for _, src, seed in METHODS]
  time = [timings[clip]["gvhmr_gmr" if src == "gmr" else "vith"] for _, src, _ in METHODS]
  flat = [s["flat_nominal"] for s in scen]
  main = table("SONIC (ViT-H)", cols, [
    ("Reference: frames past joint limits (%)", [f"{100 * r['frames_outside_joint_limits']:.1f}" for r in ref]),
    ("Reference: fastest joint (rad/s)", [f"{r['max_joint_speed_rad_s']:.0f}" for r in ref]),
    ("Reference: foot sliding (cm/s)", [f"{100 * r['foot_sliding_mean_m_s']:.0f}" for r in ref]),
    ("Flat ground", [outcome(t) for t in flat]),
    ("Never more than 15 cm off", [f"{int(vals(t, 'success_strict').sum())}/{len(t)}" for t in flat]),
    ("Pose error, mean / worst (cm)", [f"{cm(t, 'r_mpkpe_m')} / {cm(t, 'max_r_mpkpe_m')}" for t in flat]),
    ("Position error, mean / worst (cm)", [f"{cm(t, 'mpkpe_m')} / {cm(t, 'max_mpkpe_m')}" for t in flat]),
    ("Joint error (°)", [f"{np.degrees(vals(t, 'joint_pos_tracking_mae').mean()):.1f}" for t in flat]),
    ("Robot joints past limits (% of time)",
     [f"{100 * vals(t, 'joint_limit_violation_rate').mean():.1f}" for t in flat]),
    ("Power (W)", [f"{vals(t, 'mean_mech_power_w').mean():.0f}" for t in flat]),
    ("Time to make the motion (s)", [f"{t:.0f}" for t in time]),
  ])
  hard = table("Finishes (of 10 tries)", cols,
               [(label, [f"{finished(s[k])}/{len(s[k])}" for s in scen]) for k, label in HARD.items()])
  return [main, hard]


def summary_table(runs):
  rows = []
  for clip, title in CLIPS.items():
    gmr = runs[f"sonic_gmr_{clip}"]
    vith = [runs[f"sonic_vith_{clip}{seed}"] for _, src, seed in METHODS if src == "vith"]
    flat = sum(finished(v["flat_nominal"]) == len(v["flat_nominal"]) for v in vith)
    rows.append((title, [
      outcome(gmr["flat_nominal"]),
      f"{sum(finished(gmr[k]) for k in HARD)}/50",
      cm(gmr["flat_nominal"], "r_mpkpe_m"),
      f"{flat}/{len(vith)} finish",
      f"{sum(finished(v[k]) for v in vith for k in HARD)}/{50 * len(vith)}",
      f"{np.mean([vals(v['flat_nominal'], 'r_mpkpe_m').mean() for v in vith]) * 100:.1f}",
    ]))
  cols = ["GVHMR + GMR: flat ground", "harder", "pose error (cm)",
          "ViT-H, 3 samples: flat ground", "harder", "pose error (cm)"]
  return table("SONIC (ViT-H)", cols, rows)


def grounded_table(runs):
  rows = []
  for clip, title in CLIPS.items():
    cells = []
    for src, seeds in (("gmr", [""]), ("vith", ["", "_s1", "_s2"])):
      for c in ("", "_grounded"):
        trials = [runs[f"sonic_{src}_{clip}{c}{seed}"] for seed in seeds]
        flat = sum(finished(t["flat_nominal"]) for t in trials)
        hard = sum(finished(t[k]) for t in trials for k in HARD)
        cells.append(f"{flat}/{10 * len(trials)} · {hard}/{50 * len(trials)}")
    rows.append((title, cells))
  cols = ["GVHMR + GMR, raw", "GVHMR + GMR, grounded", "ViT-H, raw", "ViT-H, grounded"]
  return table("SONIC (ViT-H) finishes: flat ground · harder", cols, rows)


def tracker_rows(runs, name):
  if name not in runs:
    return ["–"] * 3
  s = runs[name]
  return [outcome(s["flat_nominal"]), f"{sum(finished(s[k]) for k in HARD)}/50", cm(s["flat_nominal"], "r_mpkpe_m")]


def mjlab_success(path):
  if not os.path.exists(path):
    return "–"
  with open(path) as f:
    return f"finishes {json.load(f)['metrics']['success_rate']:.0%}"


def tracker_table(runs, mjlab_dir, title, refs):
  """refs: (column, BeyondMimic run, SONIC run or None)."""
  bm = [tracker_rows(runs, f"beyondmimic_{b}") for _, b, _ in refs]
  so = [tracker_rows(runs, f"sonic_{x}") for _, _, x in refs]
  labels = ["flat ground", "harder (of 50)", "pose error (cm)"]
  rows = [("BeyondMimic: mjlab (1024 tries)", [mjlab_success(f"{mjlab_dir}/{b}_mjlab.json") for _, b, _ in refs])]
  rows += [(f"BeyondMimic: {label}", [b[i] for b in bm]) for i, label in enumerate(labels)]
  rows += [(f"SONIC (ViT-H): {label}", [x[i] for x in so]) for i, label in enumerate(labels)]
  return table(title, [r[0] for r in refs], rows)


def tennis_table(runs, mjlab_dir):
  refs = [("GVHMR + GMR", "gmr_tennis", "gmr_tennis"),
          ("GVHMR + GMR, clipped", "gmr_tennis_clipped", "gmr_tennis_clipped"),
          ("ViT-H sample 1", "vith_tennis", "vith_tennis"),
          ("ViT-H sample 1, clipped", "vith_tennis_clipped", "vith_tennis_clipped")]
  return tracker_table(runs, mjlab_dir, "Tennis serve", refs)


def trackers_table(runs, mjlab_dir):
  rows = []
  for clip, title in CLIPS.items():
    for label, src in (("GVHMR + GMR", "gmr"), ("ViT-H sample 1", "vith")):
      bm = f"{src}_tennis" if clip == "tennis" else f"{clip}_{src}"
      cells = [mjlab_success(f"{mjlab_dir}/{bm}_mjlab.json"), *tracker_rows(runs, f"beyondmimic_{bm}"),
               *tracker_rows(runs, f"sonic_{src}_{clip}")]
      rows.append((f"{title}, {label}", cells))
  cols = ["BeyondMimic: mjlab", "BeyondMimic: flat ground", "BeyondMimic: harder (of 50)",
          "BeyondMimic: pose error (cm)", "SONIC (ViT-H): flat ground", "SONIC (ViT-H): harder (of 50)",
          "SONIC (ViT-H): pose error (cm)"]
  return table("BeyondMimic (3000 iterations) vs SONIC (ViT-H)", cols, rows)


def jump_kick_table(runs, mjlab_dir):
  refs = [("GVHMR + GMR", "jump_kick_gmr", "gmr_jump_kick"),
          ("GVHMR + GMR, grounded", "jump_kick_gmr_grounded", "gmr_jump_kick_grounded"),
          ("ViT-H sample 1", "jump_kick_vith", "vith_jump_kick"),
          ("GVHMR + GMR, 18500 iterations", "jump_kick_gmr_18500", None)]
  return tracker_table(runs, mjlab_dir, "Jump and knee kick", refs)


def ros2_success(path):
  with open(path) as f:
    s = json.load(f)["summary"]
  return f"finishes {s['successes']}/{s['scored']}"


def demo_table(runs, latency, mjlab, ros2):
  bm, so = runs["beyondmimic_demo_dance"], runs["sonic_demo_dance"]
  fb, fs = bm["flat_nominal"], so["flat_nominal"]
  rows = [
    ("Flat ground", [outcome(fb), outcome(fs)]),
    ("Harder conditions", [f"{sum(finished(bm[k]) for k in HARD)}/50", f"{sum(finished(so[k]) for k in HARD)}/50"]),
    ("Pose error, mean (cm)", [cm(fb, "r_mpkpe_m"), cm(fs, "r_mpkpe_m")]),
    ("Position error, mean (cm)", [cm(fb, "mpkpe_m"), cm(fs, "mpkpe_m")]),
  ]
  lat = {k: f"{vals(v['flat_nominal'], 'mean_policy_latency_ms').mean():.2f}" for k, v in latency.items()}
  rows += [
    ("Policy time per step (ms)", [lat["beyondmimic_demo_dance"], lat["sonic_demo_dance"]]),
    ("mjlab (training simulator, 1024 tries)", [mjlab, "–"]),
    ("ROS 2 deployment stack (5 tries)", [ros2, "–"]),
    ("ViT-H's tracker script (g1_tracker)", ["–", G1_TRACKER_DEMO]),
  ]
  return table("LAFAN1 dance (131 s, motion capture)", ["BeyondMimic", "SONIC (ViT-H)"], rows)


def main():
  args = parse_args()
  runs = load_runs(args.runs)
  quality = load_quality(args.quality)
  timings = load_timings(args.timings)
  parts = ["### At a glance", summary_table(runs)]
  for clip, title in CLIPS.items():
    parts += [f"### {title}", *clip_tables(runs, quality, timings, clip)]
  parts += ["### BeyondMimic vs SONIC (ViT-H), every clip", trackers_table(runs, args.mjlab)]
  parts += ["### Tennis serve: BeyondMimic vs SONIC (ViT-H)", tennis_table(runs, args.mjlab)]
  parts += ["### Jump and knee kick: BeyondMimic vs SONIC (ViT-H)", jump_kick_table(runs, args.mjlab)]
  parts += ["### Feet put back on the floor (grounded)", grounded_table(runs)]
  demo = demo_table(runs, load_runs(args.latency), mjlab_success(args.demo), ros2_success(args.demo_ros2))
  parts += ["### LAFAN1 dance: BeyondMimic vs SONIC (ViT-H)", demo]
  parts += ["### Notes", NOTES]
  text = "\n\n".join(parts)
  with open(args.output, "w") as f:
    f.write(text + "\n")
  print(text)


if __name__ == "__main__":
  main()
