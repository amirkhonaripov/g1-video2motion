"""Render a harness run or a ROS 2 recording to an MP4, filmed from the same side as the person in the input video."""

import argparse
import subprocess
from pathlib import Path

import mujoco
import numpy as np
import torch

from scripts.g1 import G1_XML, yaw
from scripts.ros2.analyze_ros2 import resample, set_pose
from scripts.ros2.recording import read_recording


def parse_args():
  parser = argparse.ArgumentParser(description="Render a harness run or a ROS 2 run")
  parser.add_argument("run_file", help="ROS 2 recording folder (runs/bags/<stem>_r<k>/) or harness log .npz")
  parser.add_argument("--output-file", required=True)
  parser.add_argument("--gvhmr-file", help="hmr4d_results.pt of the same video, for the camera side")
  parser.add_argument("--follow", action="store_true", help="turn with the video's camera (for moving cameras)")
  parser.add_argument("--view-deg", type=float, default=0.0, help="extra turn of the camera")
  parser.add_argument("--model-xml", default=G1_XML)
  parser.add_argument("--width", type=int, default=640)
  parser.add_argument("--height", type=int, default=480)
  parser.add_argument("--start", type=float, help="ROS 2 run: first second to render, in the run's clock")
  parser.add_argument("--duration", type=float, help="ROS 2 run: seconds to render (default: to the end)")
  parser.add_argument("--fps", type=int, default=30, help="ROS 2 run: frame rate (a harness log keeps its own)")
  return parser.parse_args()


def axis_angle_to_matrix(v):
  angle = np.linalg.norm(v)
  if angle < 1e-12:
    return np.eye(3)
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


def harness_frames(log, model):
  qpos = np.zeros((len(log["t"]), model.nq))
  qpos[:, :3], qpos[:, 3:7], qpos[:, 7:] = log["base_pos"], log["base_quat"], log["q"]
  return log["t"], qpos


def ros2_frames(run, model, start, duration, fps):
  """Poses at a steady frame rate, the pelvis placed under the recorded lidar pose."""
  data = mujoco.MjData(model)
  adr = [model.joint(name).qposadr[0] for name in run["joint_names"]]
  start = run["joint_time"][0] if start is None else start
  end = run["joint_time"][-1] if duration is None else start + duration
  times = np.arange(start, end, 1 / fps)
  joints = resample(run["joint_time"], run["joint_pos"], times)
  base = resample(run["base_time"], run["base_pos"], times)
  k = np.minimum(np.searchsorted(run["base_time"], times), len(run["base_time"]) - 1)
  qpos = []
  for i in range(len(times)):
    set_pose(model, data, adr, base[i], run["base_quat"][k[i]], joints[i])
    qpos.append(data.qpos.copy())
  return times - start, np.array(qpos)


def camera_azimuth(times, base_quat, args):
  """Degrees per frame: see the robot from the side the video sees the person."""
  heading = np.unwrap(yaw(base_quat))
  if not args.gvhmr_file:
    return np.full(len(heading), np.degrees(heading[0]) + 180 + args.view_deg)
  turn = person_turn(args.gvhmr_file)
  if args.follow:
    az = heading - np.interp(times, np.arange(len(turn)) / 30, turn)
    az = smooth(az, round(1 / np.median(np.diff(times))))
  else:
    az = np.full(len(heading), heading[0] - np.angle(np.mean(np.exp(1j * turn[:10]))))
  return np.degrees(az) + 180 + args.view_deg


def main():
  args = parse_args()
  model = mujoco.MjModel.from_xml_path(args.model_xml)
  data = mujoco.MjData(model)
  if Path(args.run_file).is_dir():
    times, frames = ros2_frames(read_recording(args.run_file), model, args.start, args.duration, args.fps)
  else:
    times, frames = harness_frames(np.load(args.run_file), model)
  model.vis.global_.offwidth, model.vis.global_.offheight = args.width, args.height
  renderer = mujoco.Renderer(model, height=args.height, width=args.width)
  azimuth = camera_azimuth(times, frames[:, 3:7], args)
  cam = mujoco.MjvCamera()
  cam.distance, cam.elevation = 3.0, -10.0
  print(f"[INFO] camera azimuth {azimuth.min():.0f}° to {azimuth.max():.0f}°")
  fps = round(1 / np.median(np.diff(times)))
  ffmpeg = subprocess.Popen(
    ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{args.width}x{args.height}",
     "-r", str(fps), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", args.output_file],
    stdin=subprocess.PIPE)
  for qpos, az in zip(frames, azimuth):
    data.qpos[:] = qpos
    mujoco.mj_forward(model, data)
    cam.lookat[:], cam.azimuth = [qpos[0], qpos[1], 0.8], az
    renderer.update_scene(data, camera=cam)
    ffmpeg.stdin.write(renderer.render().tobytes())
  ffmpeg.stdin.close()
  ffmpeg.wait()
  print(f"[INFO] {len(frames)} frames at {fps} fps -> {args.output_file}")


if __name__ == "__main__":
  main()
