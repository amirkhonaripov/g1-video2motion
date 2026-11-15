"""Checkpoint, motion and name of a BeyondMimic policy, from its training run folder or given directly."""

import re
from pathlib import Path

TASK = "Mjlab-Tracking-Flat-Unitree-G1"
DATE_PREFIX = r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_"


def add_args(parser):
  parser.add_argument("run_dir", nargs="?", help="training run folder, e.g. runs/train/g1_tracking/<date>_<name>")
  parser.add_argument("--checkpoint", help="model_N.pt in the run folder (default: the last one)")
  parser.add_argument("--name", help="policy stem (default: the run folder's name without the date)")
  parser.add_argument("--checkpoint-file", help="a checkpoint .pt outside a run folder (with --motion-file, --name)")
  parser.add_argument("--motion-file", help="motion .npz (default: motion_file in the run's params/env.yaml)")
  parser.add_argument("--task", default=TASK, help="mjlab tracking task")


def resolve(parser, args):
  """(checkpoint file, motion file, name)."""
  if args.run_dir is None:
    if not (args.checkpoint_file and args.motion_file and args.name):
      parser.error("give a training run folder, or --checkpoint-file, --motion-file and --name")
    return args.checkpoint_file, args.motion_file, args.name
  run = Path(args.run_dir)
  if args.checkpoint:
    checkpoint = run / args.checkpoint
  else:
    checkpoint = max(run.glob("model_*.pt"), key=lambda p: int(p.stem.split("_")[1]))
  env = (run / "params/env.yaml").read_text()
  motion = args.motion_file or re.search(r"^\s*motion_file: (\S+)", env, re.MULTILINE)[1]
  return str(checkpoint), motion, args.name or re.sub(DATE_PREFIX, "", run.name)
