"""Render a harness run, a ROS 2 recording or a motion to an MP4, filmed from the same side as the person in the
input video."""

import argparse
import subprocess
from pathlib import Path

import mujoco
import numpy as np
import torch

from scripts.g1 import G1_XML, JOINT_NAMES, yaw
from scripts.ros2.analyze_ros2 import load_run, next_to, policy_start, resample, set_pose

GHOST_RGBA = (1.0, 0.6, 0.2, 0.35)


def parse_args():
  parser = argparse.ArgumentParser(description="Render a harness run, a ROS 2 run or a motion")
  parser.add_argument("run_file", help="ROS 2 recording folder (runs/bags/<stem>_r<k>/), harness log .npz or "
                      "motion .npz (joint_pos, body_pos_w, body_quat_w), played back as is")
  parser.add_argument("--output-file", required=True)
  parser.add_argument("--gvhmr-file", help="hmr4d_results.pt of the same video, for the camera side")
  parser.add_argument("--follow", action="store_true", help="turn with the video's camera (for moving cameras)")
  parser.add_argument("--view-deg", type=float, default=0.0, help="extra turn of the camera")
  parser.add_argument("--model-xml", default=G1_XML)
  parser.add_argument("--width", type=int, default=640)
  parser.add_argument("--height", type=int, default=480)
  parser.add_argument("--start", type=float, help="first second to render, in the run's clock")
  parser.add_argument("--duration", type=float, help="seconds to render (default: to the end)")
  parser.add_argument("--fps", type=int, default=30, help="ROS 2 run: frame rate (a log or motion keeps its own)")
  parser.add_argument("--ghost", help="motion .npz drawn see-through at the same motion time (0 = trial start or "
                      "policy start, hidden after its end), at the robot's pelvis x, y and heading but its own "
                      "height plus the robot's start offset, to show pose and height misses, not drift")
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


def motion_frames(motion, model):
  """Poses of a motion file: the root from the first body, the joints in its own order."""
  adr = [model.joint(n).qposadr[0] for n in motion["joint_names"]] if "joint_names" in motion else slice(7, None)
  fps = float(motion["fps"].squeeze()) if "fps" in motion else 50.0
  qpos = np.zeros((len(motion["joint_pos"]), model.nq))
  qpos[:, :3], qpos[:, 3:7] = motion["body_pos_w"][:, 0], motion["body_quat_w"][:, 0]
  qpos[:, adr] = motion["joint_pos"]
  return np.arange(len(qpos)) / fps, qpos


def window(times, frames, start, duration):
  keep = np.ones(len(times), bool)
  if start is not None:
    keep &= times >= start - 1e-6
  if duration is not None:
    keep &= times < (times[0] if start is None else start) + duration - 1e-6
  return times[keep], frames[keep]


def ros2_times(run, start, duration, fps):
  """Sim times at a steady frame rate."""
  start = run["joint_time"][0] if start is None else start
  end = run["joint_time"][-1] if duration is None else start + duration
  return np.arange(start, end, 1 / fps)


def ros2_frames(run, model, times):
  """Poses at these sim times, the pelvis placed under the recorded lidar pose."""
  data = mujoco.MjData(model)
  adr = [model.joint(name).qposadr[0] for name in run["joint_names"]]
  joints = resample(run["joint_time"], run["joint_pos"], times)
  base = resample(run["base_time"], run["base_pos"], times)
  k = np.minimum(np.searchsorted(run["base_time"], times), len(run["base_time"]) - 1)
  qpos = []
  for i in range(len(times)):
    set_pose(model, data, adr, base[i], run["base_quat"][k[i]], joints[i])
    qpos.append(data.qpos.copy())
  return np.array(qpos)


def ghost_frames(motion, model, frames, motion_t, z0):
  """The motion's pose at each motion time, moved to the robot's pelvis x, y and heading; None after its end."""
  t, qpos = motion_frames(motion, model)
  k = np.round(motion_t / t[1]).astype(int)
  ghost = qpos[np.clip(k, 0, len(qpos) - 1)]
  ghost[:, :2] = frames[:, :2]
  ghost[:, 2] += z0 - qpos[0, 2]
  half = (yaw(frames[:, 3:7]) - yaw(ghost[:, 3:7])) / 2
  c, s = np.cos(half), np.sin(half)
  w, x, y, z = ghost[:, 3:7].T.copy()
  ghost[:, 3:7] = np.stack([c * w - s * z, c * x - s * y, c * y + s * x, c * z + s * w], axis=1)
  return [g if 0 <= i < len(qpos) else None for g, i in zip(ghost, k)]


def add_ghost(model, data, scene):
  """Append data's pose to the scene, see-through and without shadows."""
  n = scene.ngeom
  mujoco.mjv_addGeoms(model, data, mujoco.MjvOption(), mujoco.MjvPerturb(), mujoco.mjtCatBit.mjCAT_DYNAMIC, scene)
  for i in range(n, scene.ngeom):
    geom = scene.geoms[i]
    geom.rgba[:], geom.matid, geom.castshadow, geom.transparent = GHOST_RGBA, -1, 0, 1


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
  motion = dict(np.load(args.ghost)) if args.ghost else None
  if Path(args.run_file).is_dir():
    names = list(motion["joint_names"]) if motion and "joint_names" in motion else JOINT_NAMES
    run = load_run(args.run_file, names)
    sim_t = ros2_times(run, args.start, args.duration, args.fps)
    times, frames = sim_t - sim_t[0], ros2_frames(run, model, sim_t)
    if motion:
      zero, method = policy_start(run, motion, None, next_to(args.run_file, ".sim.log"))
      print(f"[INFO] policy start {zero:.3f} s ({method})")
      motion_t, z0 = sim_t - zero, ros2_frames(run, model, np.array([zero]))[0, 2]
  else:
    log = np.load(args.run_file)
    times, frames = harness_frames(log, model) if "base_pos" in log else motion_frames(log, model)
    z0 = frames[0, 2]
    times, frames = window(times, frames, args.start, args.duration)
    motion_t = times
  ghosts = ghost_frames(motion, model, frames, motion_t, z0) if motion else [None] * len(frames)
  ghost_data = mujoco.MjData(model)
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
  for qpos, ghost, az in zip(frames, ghosts, azimuth):
    data.qpos[:] = qpos
    mujoco.mj_forward(model, data)
    cam.lookat[:], cam.azimuth = [qpos[0], qpos[1], 0.8], az
    renderer.update_scene(data, camera=cam)
    if ghost is not None:
      ghost_data.qpos[:] = ghost
      mujoco.mj_forward(model, ghost_data)
      add_ghost(model, ghost_data, renderer.scene)
    ffmpeg.stdin.write(renderer.render().tobytes())
  ffmpeg.stdin.close()
  ffmpeg.wait()
  print(f"[INFO] {len(frames)} frames at {fps} fps -> {args.output_file}")


if __name__ == "__main__":
  main()
