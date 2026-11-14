"""GMR robot motion (.pkl) -> mjlab motion (.npz), saved locally."""

import argparse
import pickle
import tempfile

import numpy as np
import torch
from mjlab.scene import Scene
from mjlab.scripts.csv_to_npz import MotionLoader
from mjlab.sim.sim import Simulation, SimulationCfg
from mjlab.tasks.tracking.config.g1.env_cfgs import unitree_g1_flat_tracking_env_cfg

# mjlab's G1 joint order (same as GMR's unitree_g1)
JOINT_NAMES = [
  "left_hip_pitch_joint",
  "left_hip_roll_joint",
  "left_hip_yaw_joint",
  "left_knee_joint",
  "left_ankle_pitch_joint",
  "left_ankle_roll_joint",
  "right_hip_pitch_joint",
  "right_hip_roll_joint",
  "right_hip_yaw_joint",
  "right_knee_joint",
  "right_ankle_pitch_joint",
  "right_ankle_roll_joint",
  "waist_yaw_joint",
  "waist_roll_joint",
  "waist_pitch_joint",
  "left_shoulder_pitch_joint",
  "left_shoulder_roll_joint",
  "left_shoulder_yaw_joint",
  "left_elbow_joint",
  "left_wrist_roll_joint",
  "left_wrist_pitch_joint",
  "left_wrist_yaw_joint",
  "right_shoulder_pitch_joint",
  "right_shoulder_roll_joint",
  "right_shoulder_yaw_joint",
  "right_elbow_joint",
  "right_wrist_roll_joint",
  "right_wrist_pitch_joint",
  "right_wrist_yaw_joint",
]
KEYS = [
  "joint_pos",
  "joint_vel",
  "body_pos_w",
  "body_quat_w",
  "body_lin_vel_w",
  "body_ang_vel_w",
]


def parse_args():
  parser = argparse.ArgumentParser(description="GMR .pkl -> mjlab motion .npz")
  parser.add_argument(
    "input_file", help="GMR pickle: root_pos, root_rot (xyzw), dof_pos, fps"
  )
  parser.add_argument("--output-file", required=True)
  parser.add_argument("--output-fps", type=int, default=50)
  parser.add_argument("--device", default="cuda:0")
  return parser.parse_args()


def pkl_to_csv(pkl_file, csv_file):
  """Write the CSV layout csv_to_npz.py reads: xyz, quat xyzw, 29 joints."""
  with open(pkl_file, "rb") as f:
    motion = pickle.load(f)
  rows = np.concatenate(
    [motion["root_pos"], motion["root_rot"], motion["dof_pos"]], axis=1
  )
  np.savetxt(csv_file, rows, delimiter=",")
  return float(motion["fps"])


def make_sim(output_fps, device):
  sim_cfg = SimulationCfg()
  sim_cfg.mujoco.timestep = 1.0 / output_fps
  scene = Scene(unitree_g1_flat_tracking_env_cfg().scene, device=device)
  model = scene.compile()
  sim = Simulation(num_envs=1, cfg=sim_cfg, model=model, device=device)
  scene.initialize(sim.mj_model, sim.model, sim.data)
  return sim, scene


def replay(sim, scene, motion):
  """Put the robot in each frame's pose and record body states (no physics)."""
  robot = scene["robot"]
  joint_ids = robot.find_joints(JOINT_NAMES, preserve_order=True)[0]
  log = {k: [] for k in KEYS}
  scene.reset()
  for _ in range(motion.output_frames):
    (base_pos, base_rot, base_lin_vel, base_ang_vel, dof_pos, dof_vel), _ = (
      motion.get_next_state()
    )
    root = robot.data.default_root_state.clone()
    root[:, 0:3] = base_pos
    root[:, :2] += scene.env_origins[:, :2]
    root[:, 3:7] = base_rot
    root[:, 7:10] = base_lin_vel
    root[:, 10:] = base_ang_vel
    robot.write_root_state_to_sim(root)
    joint_pos = robot.data.default_joint_pos.clone()
    joint_vel = robot.data.default_joint_vel.clone()
    joint_pos[:, joint_ids] = dof_pos
    joint_vel[:, joint_ids] = dof_vel
    robot.write_joint_state_to_sim(joint_pos, joint_vel)
    sim.forward()
    scene.update(sim.mj_model.opt.timestep)
    data = robot.data
    log["joint_pos"].append(data.joint_pos[0])
    log["joint_vel"].append(data.joint_vel[0])
    log["body_pos_w"].append(data.body_link_pos_w[0])
    log["body_quat_w"].append(data.body_link_quat_w[0])
    log["body_lin_vel_w"].append(data.body_link_lin_vel_w[0])
    log["body_ang_vel_w"].append(data.body_link_ang_vel_w[0])
  return {k: torch.stack(v).cpu().numpy() for k, v in log.items()}


def main():
  args = parse_args()
  if args.device.startswith("cuda") and not torch.cuda.is_available():
    args.device = "cpu"
  with tempfile.NamedTemporaryFile(suffix=".csv") as csv:
    input_fps = pkl_to_csv(args.input_file, csv.name)
    sim, scene = make_sim(args.output_fps, args.device)
    motion = MotionLoader(csv.name, input_fps, args.output_fps, sim.device)
  log = replay(sim, scene, motion)
  np.savez(args.output_file, fps=[float(args.output_fps)], **log)
  print(
    f"Saved {args.output_file}: {motion.output_frames} frames at {args.output_fps} fps"
  )


if __name__ == "__main__":
  main()
