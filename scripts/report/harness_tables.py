"""Results tables: harness success, tracking error and real falls per tracker, plus mjlab and ROS 2 for BeyondMimic."""

import argparse
import csv
import glob
import json
import os
import re

import numpy as np

TRACKERS = {"beyondmimic": "BeyondMimic", "sonicv11": "SONIC v1.1", "sonic": "SONIC (ViT-H)"}
CLIPS = {
  "tennis": "Tennis serve",
  "studio_dance": "Studio dance",
  "hiphop_back": "Hip-hop (back)",
  "pop": "Pop",
  "jazz": "Jazz",
  "jump_kick": "Jump kick",
  "demo_dance": "LAFAN1 dance",
}
SOURCES = [
  ("GVHMR+GMR", "gmr", ""),
  ("ViT-H sample 1", "vith", ""),
  ("ViT-H sample 2", "vith", "_s1"),
  ("ViT-H sample 3", "vith", "_s2"),
]
VARIANTS = {"": "", "_grounded": ", grounded", "_18500": ", 18500 iterations"}
CONDITIONS = {
  "flat_nominal": "Flat",
  "low_friction": "Low friction",
  "ice": "Ice",
  "push_lateral_medium": "Push from the side",
  "push_forward_hard": "Hard push from behind",
  "push_backward_medium": "Push from the front",
}
SLIPPERY = ["low_friction", "ice"]
PUSHES = ["push_lateral_medium", "push_forward_hard", "push_backward_medium"]
DEFINITIONS = """- **Harness:** one shared MuJoCo sim (the G1 of the ROS 2 stack) for every tracker; each condition runs 10 seeds
  that differ only by tiny start noise (±0.02 rad per joint). **Conditions:** flat ground; slippery: low friction
  (μ 0.4) and ice (μ 0.2); pushes: 0.2 s shoves on the pelvis at t = 4 s ± 0.3 s, 150 N from the side, 250 N from
  behind, 150 N from the front.
- **Success:** the motion plays to its end without a tracking failure.
- **Tracking failure:** BeyondMimic's termination rule fires (torso height or a hand/foot height more than 0.25 m
  off the reference, or the torso tilted too far). The trial stops there; the robot may still recover.
- **Real fall:** in a rerun that keeps going after a tracking failure, the head stays below 0.5 m for more than
  2 s, or is still down when the motion ends. Only conditions with a tracking failure were rerun; "not rerun"
  counts failed trials whose rerun is missing.
- **MPKPE / r-MPKPE:** mean distance (cm) of 14 key bodies from the reference over the 10 flat-ground trials, up to
  the end or the tracking failure. MPKPE in world position (pose plus drift); r-MPKPE with the reference placed on
  the robot (pose only). SONIC follows the reference relative to itself, so its MPKPE grows on long motions.
- **k/n:** k of n trials (mjlab: episodes; ROS 2: scored runs).
- **ViT-H sample N:** ViT-H samples a motion from random noise; samples 1-3 are three draws (seeds 42, 1, 2).
  **Grounded:** the motion moved down so the feet touch the floor.
- **n/a:** the jump kick is 2.2 s long and the pushes come at 3.7-4.3 s, so no push happens.
- **BeyondMimic:** one policy per motion, 3000 mjlab iterations unless the row says otherwise; the LAFAN1 dance uses
  BeyondMimic's pretrained policy. **mjlab:** its own evaluation, 1024 episodes. **ROS 2:** the full ROS 2 stack.
- ViT-H's own tracker script (g1_tracker) also fails the LAFAN1 dance at 106.7 s."""


def parse_args():
  parser = argparse.ArgumentParser(description="Results tables")
  parser.add_argument("--runs", default="runs/harness", help="harness runs, ros2 robot model")
  parser.add_argument("--falls", default="runs/harness_falls", help="reruns that keep going after a tracking failure")
  parser.add_argument("--latency", default="runs/latency", help="harness runs timing the policies")
  parser.add_argument("--mjlab", default="results/mjlab", help="eval_mjlab results")
  parser.add_argument("--ros2", default="results/ros2", help="analyze_ros2 results")
  parser.add_argument("--quality", default="results/motion_quality.json")
  parser.add_argument("--timings", default="results/timings.csv")
  parser.add_argument("--output", default="results/tables.md")
  return parser.parse_args()


def load_runs(root):
  """{run: {condition: {seed: trial}}}; None for a push that would come after the motion ends."""
  runs = {}
  for path in sorted(glob.glob(f"{root}/*/summary.json")):
    name = os.path.basename(os.path.dirname(path)).split("__")[0]
    if "_clipped" in name:
      continue
    with open(path) as f:
      s = json.load(f)
    motion_s = s["adapter"]["describe"]["motion_frames"] / 50
    for cond, trials in s["trials"].items():
      starts = [p["start_s"] for seed in s["perturbations"][cond].values() for p in seed["pushes"]]
      runs.setdefault(name, {})[cond] = None if starts and min(starts) >= motion_s else trials
  return runs


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


def run_name(tracker, clip, src, seed, variant):
  if clip == "demo_dance":
    return f"{tracker}_demo_dance"
  if tracker != "beyondmimic":
    return f"{tracker}_{src}_{clip}{variant}{seed}"
  if clip == "tennis" and not seed:
    return f"beyondmimic_{src}_tennis{variant}"
  return f"beyondmimic_{clip}{seed}_{src}{variant}"


def motions(variants, vith_grounded=False):
  """(clip, motion label, src, seed, variant) of every row, LAFAN1 dance last."""
  out = []
  for clip in CLIPS:
    if clip == "demo_dance":
      out.append((clip, "motion capture", "", "", ""))
      continue
    for label, src, seed in SOURCES:
      for v in variants:
        if v != "_grounded" or src == "gmr" or vith_grounded:
          out.append((clip, label + VARIANTS[v], src, seed, v))
  return out


def vals(trials, key):
  return np.array([t[key] for t in trials.values() if t.get(key) is not None], dtype=float)


def tally(runs, falls, name, conds):
  """Successes, real falls, trials and failed trials without a rerun, over these conditions."""
  ok = fell = n = unknown = 0
  for cond in conds:
    trials = runs[name][cond]
    if trials is None:
      continue
    ok += sum(not t["fall"] for t in trials.values())
    n += len(trials)
    if cond in falls.get(name, {}):
      fell += sum(t["fell"] for t in falls[name][cond].values())
    else:
      unknown += sum(t["fall"] for t in trials.values())
  return ok, fell, n, unknown


def success(t):
  ok, _, n, _ = t
  return f"{ok}/{n}" if n else "n/a"


def real_falls(t):
  _, fell, n, unknown = t
  return f"{fell}/{n}" + (f" ({unknown} not rerun)" if unknown else "")


def error(trials):
  return f"{100 * vals(trials, 'mpkpe_m').mean():.1f} / {100 * vals(trials, 'r_mpkpe_m').mean():.1f}"


def summary_cells(runs, falls, name):
  """Success all / flat / slippery / pushes, flat error, real falls."""
  if name not in runs:
    return ["no run"] + ["–"] * 5
  every = tally(runs, falls, name, CONDITIONS)
  parts = [success(tally(runs, falls, name, c)) for c in (["flat_nominal"], SLIPPERY, PUSHES)]
  return [success(every), *parts, error(runs[name]["flat_nominal"]), real_falls(every)]


def mjlab(path):
  if not os.path.exists(path):
    return "–"
  with open(path) as f:
    m = json.load(f)["metrics"]
  n = m["num_episodes"]
  return f"{100 * m['success_rate']:.1f}% ({round(m['success_rate'] * n)}/{n})"


def ros2(path):
  if not os.path.exists(path):
    return "–"
  with open(path) as f:
    d = json.load(f)
  if "summary" not in d:  # old format: a list of runs
    return "–"
  s = d["summary"]
  return f"{s['successes']}/{s['scored']} ({s['launches']} launches)"


def table(cols, rows):
  lines = ["| " + " | ".join(cols) + " |", "|---" * len(cols) + "|"]
  return "\n".join(lines + ["| " + " | ".join(r) + " |" for r in rows])


def tracker_table(tracker, runs, falls, args):
  cols = ["Clip", "Motion", "Success: all", "flat", "slippery", "pushes", "MPKPE / r-MPKPE (cm), flat", "Real falls"]
  if tracker == "beyondmimic":
    cols += ["mjlab success", "ROS 2 success"]
  rows = []
  for clip, label, src, seed, v in motions(VARIANTS):
    name = run_name(tracker, clip, src, seed, v)
    if v and name not in runs:
      continue
    cells = [CLIPS[clip], label, *summary_cells(runs, falls, name)]
    if tracker == "beyondmimic":
      short = name.removeprefix("beyondmimic_")
      cells += [mjlab(f"{args.mjlab}/{short}_mjlab.json"), ros2(f"{args.ros2}/{short}.json")]
    rows.append(cells)
  return table(cols, rows)


def comparison_table(runs, falls):
  cols = ["Clip", "Motion"]
  cols += [f"{m}: {t}" for m in ("Success", "MPKPE / r-MPKPE (cm)", "Real falls") for t in TRACKERS.values()]
  rows = []
  for clip, label, src, seed, v in motions(["", "_grounded"]):
    names = [run_name(t, clip, src, seed, v) for t in TRACKERS]
    if v and not any(n in runs for n in names):
      continue
    cells = [summary_cells(runs, falls, n) for n in names]
    rows.append([CLIPS[clip], label] + [c[i] for i in (0, 4, 5) for c in cells])
  return table(cols, rows)


def detail_table(tracker, runs, falls):
  rows = []
  for clip, label, src, seed, v in motions(VARIANTS, vith_grounded=True):
    name = run_name(tracker, clip, src, seed, v)
    if name not in runs:
      continue
    cells = []
    for cond in CONDITIONS:
      if runs[name][cond] is None:
        cells.append("n/a")
        continue
      t = tally(runs, falls, name, [cond])
      cells.append(f"{success(t)} · {real_falls(t)} · {100 * vals(runs[name][cond], 'r_mpkpe_m').mean():.1f}")
    rows.append([CLIPS[clip], label, *cells])
  return table(["Clip", "Motion", *CONDITIONS.values()], rows)


def latency_table(latency):
  cells = [f"{vals(latency[f'{t}_demo_dance']['flat_nominal'], 'mean_policy_latency_ms').mean():.2f}" for t in TRACKERS]
  return table(["", *TRACKERS.values()], [["Policy time per step (ms), LAFAN1 dance", *cells]])


def sources_table(quality, timings):
  rows = []
  for clip, label, src, seed, _ in motions([""])[:-1]:
    q = quality[(clip, src, seed)]
    rows.append([CLIPS[clip], label, f"{timings[clip]['gvhmr_gmr' if src == 'gmr' else 'vith']:.0f}",
                 f"{100 * q['frames_outside_joint_limits']:.1f}", f"{q['max_joint_speed_rad_s']:.0f}",
                 f"{100 * q['foot_sliding_mean_m_s']:.0f}"])
  cols = ["Clip", "Motion", "Time to make (s)", "Frames past joint limits (%)", "Fastest joint (rad/s)",
          "Foot sliding (cm/s)"]
  return table(cols, rows)


def main():
  args = parse_args()
  runs, falls = load_runs(args.runs), load_runs(args.falls)
  parts = ["### Definitions", DEFINITIONS]
  for tracker, title in TRACKERS.items():
    parts += [f"### {title}", tracker_table(tracker, runs, falls, args)]
  parts += ["### Trackers side by side", comparison_table(runs, falls)]
  parts += ["### Policy time", latency_table(load_runs(args.latency))]
  parts += ["### Motion sources", sources_table(load_quality(args.quality), load_timings(args.timings))]
  parts += ["### Every condition", "Each cell: success · real falls · r-MPKPE (cm)."]
  for tracker, title in TRACKERS.items():
    parts += [f"#### {title}", detail_table(tracker, runs, falls)]
  text = "\n\n".join(parts)
  with open(args.output, "w") as f:
    f.write(text + "\n")
  print(text)


if __name__ == "__main__":
  main()
