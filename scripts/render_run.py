"""Render a harness run from its log, filmed from the same side as the person in the input video."""

import argparse
import subprocess

import mujoco
import numpy as np
import torch

HARNESS_XML = "third_party/g1-eval-harness/assets/g1/g1_29dof_ros2.xml"


def parse_args():
  parser = argparse.ArgumentParser(description="Render a harness run")
  parser.add_argument("log_file", help="harness logs/<scenario>_seed<n>.npz")
  parser.add_argument("--output-file", required=True)
  parser.add_argument("--gvhmr-file", help="hmr4d_results.pt of the same video, for the camera side")
  parser.add_argument("--follow", action="store_true", help="turn with the video's camera (for moving cameras)")
  parser.add_argument("--view-deg", type=float, default=0.0, help="extra turn of the camera")
  parser.add_argument("--model-xml", default=HARNESS_XML)
  parser.add_argument("--width", type=int, default=640)
  parser.add_argument("--height", type=int, default=480)
  return parser.parse_args()


def axis_angle_to_matrix(v):
  angle = np.linalg.norm(v)
  k = v / angle
  kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
  return np.eye(3) + np.sin(angle) * kx + (1 - np.cos(angle)) * kx @ kx


def person_turn(gvhmr_file):
  """How far the person is turned from facing the camera in each video frame (rad, 30 fps)."""
  orient = torch.load(gvhmr_file, map_location="cpu", weights_only=False)["smpl_params_incam"]["global_orient"]
  forward = np.array([axis_angle_to_matrix(v)[:, 2] for v in orient.numpy()])
  return np.unwrap(np.arctan2(forward[:, 0], -forward[:, 2]))


def smooth(x, n):
  return np.convolve(np.pad(x, n // 2, mode="edge"), np.ones(n) / n, mode="valid")[:len(x)]


def yaw(quat):
  w, x, y, z = quat
  return np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


def camera_azimuth(log, args):
  """Degrees per step: see the robot from the side the video sees the person."""
  heading = np.unwrap([yaw(q) for q in log["base_quat"]])
  if not args.gvhmr_file:
    return np.full(len(heading), np.degrees(heading[0]) + 180 + args.view_deg)
  turn = person_turn(args.gvhmr_file)
  if args.follow:
    az = heading - np.interp(log["t"], np.arange(len(turn)) / 30, turn)
    az = smooth(az, round(1 / np.median(np.diff(log["t"]))))
  else:
    az = np.full(len(heading), heading[0] - np.angle(np.mean(np.exp(1j * turn[:10]))))
  return np.degrees(az) + 180 + args.view_deg


def main():
  args = parse_args()
  log = np.load(args.log_file)
  model = mujoco.MjModel.from_xml_path(args.model_xml)
  data = mujoco.MjData(model)
  model.vis.global_.offwidth, model.vis.global_.offheight = args.width, args.height
  renderer = mujoco.Renderer(model, height=args.height, width=args.width)
  azimuth = camera_azimuth(log, args)
  cam = mujoco.MjvCamera()
  cam.distance, cam.elevation = 3.0, -10.0
  print(f"[INFO] camera azimuth {azimuth.min():.0f}° to {azimuth.max():.0f}°")
  fps = round(1 / np.median(np.diff(log["t"])))
  ffmpeg = subprocess.Popen(
    ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{args.width}x{args.height}",
     "-r", str(fps), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", args.output_file],
    stdin=subprocess.PIPE)
  for pos, quat, q, az in zip(log["base_pos"], log["base_quat"], log["q"], azimuth):
    data.qpos[:3], data.qpos[3:7], data.qpos[7:] = pos, quat, q
    mujoco.mj_forward(model, data)
    cam.lookat[:], cam.azimuth = [pos[0], pos[1], 0.8], az
    renderer.update_scene(data, camera=cam)
    ffmpeg.stdin.write(renderer.render().tobytes())
  ffmpeg.stdin.close()
  ffmpeg.wait()
  print(f"[INFO] {len(log['q'])} frames at {fps} fps -> {args.output_file}")


if __name__ == "__main__":
  main()
