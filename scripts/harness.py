"""Score a policy in the eval harness under the 6 conditions, then rerun the failed conditions to count real falls."""

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path

from scripts.motion.gmr_to_sonic import default_output

EVALUATE = "third_party/g1-eval-harness/evaluate.py"
ADAPTERS = {
  "beyondmimic": "adapters.beyondmimic_adapter:BeyondMimicAdapter",
  "sonicv11": "adapters.sonic_v1_1_adapter:SonicV11Adapter",
  "sonicvith": "adapters.sonic_vith_adapter:SonicVitHAdapter",
}
CHECKPOINTS = {
  "sonicv11": "third_party/GR00T-WholeBodyControl/gear_sonic_deploy/policy/sonic_v1_1/model_decoder.onnx",
  "sonicvith": "third_party/vit-h/inputs/checkpoints/g1_tracker/model_step_020000_g1.onnx",
}
VITH_TRACKER_ROOT = "third_party/vit-h/g1_tracker"


def parse_args():
  parser = argparse.ArgumentParser(description="Score a policy in the eval harness (6 conditions, then real falls)")
  parser.add_argument("tracker", choices=list(ADAPTERS))
  parser.add_argument("what", help="beyondmimic: a policy name (runs/onnx/<name>/policy.onnx) or a .onnx path; "
                      "sonicv11/sonicvith: a mjlab motion .npz, or a SONIC motion in data/motions/sonic/")
  parser.add_argument("--seeds", nargs="+", default=[str(s) for s in range(10)], help="default: 0 to 9")
  parser.add_argument("--name", help="stem of the output folders (default: from the policy or motion)")
  parser.add_argument("--checkpoint", help="policy file (default: from <what>, or SONIC's released one)")
  parser.add_argument("--no-falls", action="store_true", help="skip the rerun of failed conditions")
  return parser.parse_args()


def policy_file(what):
  """A policy name or a .onnx path -> the .onnx file."""
  return what if what.endswith(".onnx") else f"runs/onnx/{what}/policy.onnx"


def policy_stem(what):
  """runs/onnx/<name>/policy.onnx or <name> -> <name>; other .onnx files -> the file stem."""
  path = Path(policy_file(what))
  return path.parent.name if path.name == "policy.onnx" else path.stem


def sonic_motion(motion):
  """The SONIC motion for a mjlab motion (data/motions/sonic/<stem>.npz), or the motion itself if already SONIC."""
  return motion if Path(motion).parent.name == "sonic" else default_output(motion)


def run(cmd):
  print("[run]", shlex.join(cmd), flush=True)
  subprocess.run([sys.executable if c == "python" else c for c in cmd], check=True)


def failed_conditions(out_dir):
  """Conditions with at least one tracking failure."""
  with open(f"{out_dir}/summary.json") as f:
    trials = json.load(f)["trials"]
  return [cond for cond, seeds in trials.items() if any(t["fall"] for t in seeds.values())]


def main():
  args = parse_args()
  if args.tracker == "beyondmimic":
    checkpoint = args.checkpoint or policy_file(args.what)
    stem = args.name or policy_stem(args.what)
    extra = []
  else:
    motion = sonic_motion(args.what)
    if not Path(motion).exists():
      run(["python", "-m", "scripts.motion.gmr_to_sonic", args.what])
    checkpoint = args.checkpoint or CHECKPOINTS[args.tracker]
    stem = args.name or Path(motion).stem
    extra = ["--set", f"motion={motion}"]
    if args.tracker == "sonicvith":
      extra = ["--set", f"tracker_root={VITH_TRACKER_ROOT}", *extra]
  if not Path(checkpoint).exists():
    sys.exit(f"no policy file {checkpoint}")

  base = ["python", EVALUATE, "--adapter", ADAPTERS[args.tracker], "--checkpoint", checkpoint, *extra,
          "--seeds", *args.seeds]
  out = f"runs/harness/{args.tracker}_{stem}__all"
  run([*base, "--output-dir", out])
  summaries = [f"{out}/summary.md"]

  failed = [] if args.no_falls else failed_conditions(out)
  if failed:
    falls = f"runs/harness_falls/{args.tracker}_{stem}__all"
    run([*base, "--scenarios", *failed, "--keep-running-after-tracking-failure", "--output-dir", falls])
    summaries.append(f"{falls}/summary.md")
  elif not args.no_falls:
    print("[info] no tracking failures, so no rerun for real falls")
  print("[done] summary tables:", *summaries)


if __name__ == "__main__":
  main()
