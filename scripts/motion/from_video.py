"""Make G1 motions from a video: GVHMR then GMR, or ViT-H, then the mjlab motion format."""

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

VITH_SAM = "third-party/Fast-SAM-3D-Body"
VITH_SAM_CKPT = f"{VITH_SAM}/checkpoints/sam-3d-body-dinov3"


def parse_args():
  parser = argparse.ArgumentParser(description="Video -> G1 motion (.npz)")
  parser.add_argument("video", help="input video")
  parser.add_argument("--method", required=True, choices=["gvhmr_gmr", "vith"])
  parser.add_argument("--samples", type=int, default=1, help="ViT-H samples (seeds 42, 1, 2, ...)")
  parser.add_argument("--moving-camera", action="store_true", help="the camera moves")
  parser.add_argument("--name", help="motion name (default: the video's stem)")
  parser.add_argument("--gvhmr-python", default="third_party/GVHMR/.venv/bin/python")
  parser.add_argument("--gmr-python", default="third_party/GMR/.venv/bin/python")
  parser.add_argument("--vith-python", default="third_party/vit-h/.venv/bin/python")
  return parser.parse_args()


def run(cmd, cwd=None, env=None):
  """Print and run a command; cwd is a third-party tool's folder."""
  cmd = [str(c) for c in cmd]
  prefix = "".join(f"{k}={v} " for k, v in (env or {}).items())
  print(f"[RUN] {'(cd ' + str(cwd) + ') ' if cwd else ''}{prefix}{shlex.join(cmd)}", flush=True)
  subprocess.run(cmd, cwd=cwd, env={**os.environ, **env} if env else None, check=True)


def fps(video):
  out = subprocess.run(
    ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0",
     str(video)], capture_output=True, text=True, check=True).stdout.strip()
  num, den = out.split("/")
  return float(num) / float(den)


def video_30fps(video, name):
  """The video itself if it is 30 fps, else a 30 fps copy in data/videos/<name>.mp4."""
  if abs(fps(video) - 30) < 0.01:
    return Path(video).absolute()
  out = Path(f"data/videos/{name}.mp4")
  out.parent.mkdir(parents=True, exist_ok=True)
  run(["ffmpeg", "-y", "-i", video, "-vf", "fps=30", "-an", out])
  return out.absolute()


def gvhmr_gmr(video, work, moving_camera, args):
  gvhmr = Path(args.gvhmr_python).absolute()
  gmr = Path(args.gmr_python).absolute()
  static = [] if moving_camera else ["-s"]
  run([gvhmr, "tools/demo/demo.py", "--video", video, "--output_root", work / "gvhmr", *static],
      cwd="third_party/GVHMR")
  run([gmr, "scripts/gvhmr_to_robot.py", "--gvhmr_pred_file", work / "gvhmr" / video.stem / "hmr4d_results.pt",
       "--robot", "unitree_g1", "--save_path", work / "gmr.pkl"], cwd="third_party/GMR")
  return [work / "gmr.pkl"]


def vith(video, work, moving_camera, samples, args):
  python = Path(args.vith_python).absolute()
  static = [] if moving_camera else ["--static-cam"]
  pickles = []
  for seed in [42, *range(1, samples)]:
    out = work / f"vith_s{seed}.npz"
    run([python, "tools/infer_video.py", "--video", video, "--ckpt", "vith_offline_g1.ckpt",
         "--sam3d-root", VITH_SAM, "--sam3d-ckpt-path", f"{VITH_SAM_CKPT}/model.ckpt",
         "--sam3d-mhr-path", f"{VITH_SAM_CKPT}/assets/mhr_model.pt", "--output-root", work / "vith",
         "--output", out, "--seed", seed, *static], cwd="third_party/vit-h", env={"PYTHONPATH": "."})
    run([sys.executable, "-m", "scripts.motion.vith_to_gmr", out, "--output-file", out.with_suffix(".pkl")])
    pickles.append(out.with_suffix(".pkl"))
  return pickles


def main():
  args = parse_args()
  name = args.name or Path(args.video).stem
  work = Path(f"runs/videos2motion/{name}").absolute()
  work.mkdir(parents=True, exist_ok=True)
  video = video_30fps(args.video, name)
  if args.method == "gvhmr_gmr":
    pickles, folder = gvhmr_gmr(video, work, args.moving_camera, args), "gmr"
  else:
    pickles, folder = vith(video, work, args.moving_camera, args.samples, args), "vith"
  Path(f"data/motions/{folder}").mkdir(parents=True, exist_ok=True)
  for k, pkl in enumerate(pickles, 1):
    out = f"data/motions/{folder}/{name}{f'_s{k}' if k > 1 else ''}.npz"
    run([sys.executable, "-m", "scripts.motion.gmr_to_npz", pkl, "--output-file", out])


if __name__ == "__main__":
  main()
