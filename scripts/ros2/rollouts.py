"""Run a policy in the ROS 2 stack's MuJoCo sim several times, one after another, record each rollout and score them.

python -m scripts.ros2.rollouts <stem> [--runs 10] [--max-launches 30] [--after-s 5]

Needs ROS 2 sourced. Each rollout is one `ros2 launch scripts/ros2/record.launch.py` into runs/bags/<stem>_r<k>/
(numbered after the highest existing k), stopped with Ctrl+C's SIGINT --after-s of sim time after the motion ends.
A start-up drop or an invalid recording is deleted and launched again; runs/bags/<stem>_r<k>.tries holds the launches.
At the end all of runs/bags/<stem>_r*/ are scored into results/ros2/<stem>.json.
"""

import argparse
import json
import math
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import mujoco
import numpy as np

from scripts.g1 import G1_XML
from scripts.ros2.analyze_ros2 import FPS, analyze, next_to

BAGS = Path("runs/bags")
STOP_TIMEOUT_S = 30  # SIGKILL if the launch hasn't exited by then
CLOCK = ["ros2", "topic", "echo", "--once", "--field", "clock.sec", "/clock"]


def parse_args():
  parser = argparse.ArgumentParser(description="Record and score ROS 2 rollouts of a policy, one launch at a time")
  parser.add_argument("name", help="policy name: runs/onnx/<name>/policy.onnx and reference.npz")
  parser.add_argument("--runs", type=int, default=10, help="rollouts to add after the existing ones")
  parser.add_argument("--max-launches", type=int, default=30, help="launches in total, relaunches included")
  parser.add_argument(
    "--after-s", type=float, default=5.0,
    help="time to keep recording after the motion ends (to see whether the robot stays up)",
  )
  return parser.parse_args()


def show(cmd):
  print("[run]", shlex.join(cmd), flush=True)


def run_numbers(name):
  """k of each existing runs/bags/<name>_r<k>/."""
  numbers = []
  for path in BAGS.glob(f"{name}_r*"):
    match = re.fullmatch(rf"{re.escape(name)}_r(\d+)", path.name)
    if match and path.is_dir():
      numbers.append(int(match.group(1)))
  return sorted(numbers)


def sim_seconds():
  """Whole seconds of sim time from /clock (None if nothing came)."""
  try:
    out = subprocess.run(CLOCK, capture_output=True, text=True, timeout=5).stdout
  except subprocess.TimeoutExpired:
    return None
  numbers = [line for line in out.splitlines() if line.isdigit()]  # DDS warnings can come first
  return int(numbers[0]) if numbers else None


def stop(proc):
  """SIGINT to the launch's whole process group, as Ctrl+C in a terminal; SIGKILL if it hangs."""
  try:
    os.killpg(proc.pid, signal.SIGINT)
    proc.wait(STOP_TIMEOUT_S)
  except subprocess.TimeoutExpired:
    print(f"launch still running after {STOP_TIMEOUT_S} s: SIGKILL", flush=True)
  except ProcessLookupError:
    pass
  try:
    os.killpg(proc.pid, signal.SIGKILL)  # anything left in the group
  except ProcessLookupError:
    pass
  proc.wait()


def launch(bag, policy, stop_at):
  """One launch, stopped once the sim clock reaches stop_at s; its output goes to <bag>.sim.log."""
  cmd = ["ros2", "launch", "scripts/ros2/record.launch.py", f"policy_path:={policy}", f"bag:={bag}"]
  show(cmd)
  with open(next_to(bag, ".sim.log"), "w") as log:
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
  deadline = time.time() + stop_at * 4 + 120
  try:
    while True:
      if proc.poll() is not None:
        print(f"launch exited by itself (code {proc.returncode})", flush=True)
        break
      if time.time() > deadline:
        print("timed out waiting for the sim clock", flush=True)
        break
      sec = sim_seconds()
      if sec is not None and sec >= stop_at:
        print(f"sim time {sec} s: stopping the launch", flush=True)
        break
      time.sleep(1)
  finally:
    stop(proc)
  if bag.exists() and not (bag / "metadata.yaml").exists():
    cmd = ["ros2", "bag", "reindex", str(bag), "-s", "mcap"]
    show(cmd)
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def score(bag, ref, model):
  """The scorer's result for one recording (None if it can't be read)."""
  try:
    return analyze(str(bag), ref, model)
  except Exception as e:
    print(f"{bag}: can't read the recording ({type(e).__name__}: {e})", flush=True)
    return None


def rollout(bag, policy, stop_at, ref, model, launches_left):
  """Launch until the recording is usable; returns the launches it took (None if launches ran out)."""
  for tries in range(1, launches_left + 1):
    launch(bag, policy, stop_at)
    result = score(bag, ref, model)
    if result and not result["startup_drop"] and not result["invalid_recording"]:
      next_to(bag, ".tries").write_text(f"{tries}\n")
      outcome = "success" if result["success"] else f"tracking failure at {result['tracking_failure_time_s']} s"
      print(f"{bag}: {outcome}, r-MPKPE {result['r_mpkpe_m']} m, {tries} launches", flush=True)
      return tries
    reason = "start-up drop" if result and result["startup_drop"] else "invalid recording"
    print(f"{bag}: {reason}, deleted; launching again", flush=True)
    shutil.rmtree(bag, ignore_errors=True)
  return None


def main():
  args = parse_args()
  signal.signal(signal.SIGINT, signal.default_int_handler)  # launches must not inherit an ignored SIGINT
  if not shutil.which("ros2"):
    sys.exit("ros2 not found: source ROS 2 first")
  policy = Path(f"runs/onnx/{args.name}/policy.onnx").resolve()
  if not policy.exists():
    sys.exit(f"{policy} not found")
  ref = dict(np.load(policy.parent / "reference.npz"))
  model = mujoco.MjModel.from_xml_path(G1_XML)
  stop_at = math.ceil(len(ref["joint_pos"]) / FPS + args.after_s)
  first = max(run_numbers(args.name), default=0) + 1

  launched, added = 0, 0
  for k in range(first, first + args.runs):
    tries = rollout(BAGS / f"{args.name}_r{k}", policy, stop_at, ref, model, args.max_launches - launched)
    if tries is None:
      print(f"stopped after {args.max_launches} launches (--max-launches)", flush=True)
      break
    launched += tries
    added += 1

  runs = [f"{BAGS}/{args.name}_r{k}/" for k in run_numbers(args.name)]
  if not runs:
    sys.exit("no recordings to score")
  cmd = [sys.executable, "-m", "scripts.ros2.analyze_ros2", *sorted(runs)]
  show(cmd)
  subprocess.run(cmd, check=True)
  output = f"results/ros2/{args.name}.json"
  summary = json.loads(Path(output).read_text())["summary"]
  print(f"{args.name}: {summary['line']} ({added} rollouts added; {output})")
  if added < args.runs:
    sys.exit(f"only {added} of {args.runs} rollouts recorded")


if __name__ == "__main__":
  main()
