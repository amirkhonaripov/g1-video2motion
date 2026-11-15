"""Train a BeyondMimic policy on one motion, export it to runs/onnx/<name>/ and score it in mjlab."""

import argparse
import re
import shlex
import subprocess
import sys
from pathlib import Path

from scripts.beyondmimic.train_run import DATE_PREFIX, TASK

METHODS = ("gmr", "vith")


def parse_args():
  parser = argparse.ArgumentParser(description="Train, export and score a BeyondMimic policy")
  parser.add_argument("motion", help="mjlab motion .npz, e.g. data/motions/gmr/my_clip.npz")
  parser.add_argument("--name", help="policy stem (default: <clip>_<method>[_s2|_s3][_grounded] from the motion path)")
  parser.add_argument("--iterations", type=int, default=3000, help="training iterations (default 3000)")
  parser.add_argument("--num-envs", type=int, default=4096,
                      help="parallel training environments (default 4096); lower it if training runs out of GPU memory")
  parser.add_argument("--task", default=TASK, help="mjlab tracking task")
  return parser.parse_args()


def default_name(motion):
  """data/motions/<method>/<clip>[_s2|_s3][_grounded].npz -> <clip>_<method>[...]; anything else -> the file stem."""
  path = Path(motion)
  if path.parent.name not in METHODS or path.parent.parent.name != "motions":
    return path.stem
  clip, rest = re.fullmatch(r"(.+?)((?:_s\d)?(?:_grounded)?)", path.stem).groups()
  return f"{clip}_{path.parent.name}{rest}"


def show(cmd):
  print("[run]", shlex.join(cmd), flush=True)


def run(cmd):
  show(cmd)
  subprocess.run([sys.executable if c == "python" else c for c in cmd], check=True)


def run_folder(name):
  """The newest runs/train/g1_tracking/<date>_<name>."""
  runs = [p for p in Path("runs/train/g1_tracking").glob(f"*_{name}") if re.sub(DATE_PREFIX, "", p.name) == name]
  if not runs:
    sys.exit(f"no training run folder runs/train/g1_tracking/<date>_{name}")
  return max(runs, key=lambda p: p.name)


def main():
  args = parse_args()
  name = args.name or default_name(args.motion)
  if not Path(args.motion).exists():
    sys.exit(f"no motion file {args.motion}")
  run([
    "python", "-m", "mjlab.scripts.train", args.task,
    "--env.commands.motion.motion-file", args.motion,
    "--env.scene.num-envs", str(args.num_envs),
    "--agent.max-iterations", str(args.iterations),
    "--log-root", "runs/train", "--agent.run-name", name, "--agent.logger", "tensorboard",
  ])

  from scripts.beyondmimic import eval_mjlab, export_onnx  # imports mjlab, slow

  folder = run_folder(name)
  checkpoint = str(max(folder.glob("model_*.pt"), key=lambda p: int(p.stem.split("_")[1])))
  show(["python", "-m", "scripts.beyondmimic.export_onnx", str(folder), "--name", name])
  export_onnx.export(args.task, args.motion, checkpoint, f"runs/onnx/{name}/policy.onnx")
  show(["python", "-m", "scripts.beyondmimic.eval_mjlab", str(folder), "--name", name])
  eval_mjlab.evaluate_policy(args.task, args.motion, checkpoint, name)
  print(f"[done] policy runs/onnx/{name}/policy.onnx, mjlab results results/mjlab/{name}.json")


if __name__ == "__main__":
  main()
