"""Evaluate a trained tracking policy and compute metrics."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import numpy as np
import torch
import tyro
from mjlab.envs import ManagerBasedRlEnv
from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
from mjlab.tasks.registry import list_tasks, load_env_cfg, load_rl_cfg, load_runner_cls
from mjlab.tasks.tracking.mdp import MotionCommandCfg
from mjlab.tasks.tracking.mdp.commands import MotionCommand
from mjlab.tasks.tracking.mdp.metrics import (
  compute_ee_orientation_error,
  compute_ee_position_error,
  compute_joint_velocity_error,
  compute_mpkpe,
  compute_root_relative_mpkpe,
)
from mjlab.utils.torch import configure_torch_backends


@dataclass(frozen=True)
class EvaluateConfig:
  """Configuration for policy evaluation."""

  """Local instead of WnB"""
  motion_file: str  # path to the motion.npz to track
  checkpoint_file: str  # path to the trained policy checkpoint .pt

  num_envs: int = 1024
  """Number of parallel environments (= number of episodes to evaluate)."""
  device: str | None = None
  """Device to run on. Defaults to CUDA if available."""
  output_file: str | None = None
  """Optional path to save metrics as JSON."""
  record_file: str | None = None
  """Optional .npz to save episode 0's robot pose at every step (for videos)."""


def run_evaluate(task_id: str, cfg: EvaluateConfig) -> dict[str, float]:
  """Run policy evaluation and compute metrics."""
  configure_torch_backends()
  device = cfg.device or ("cuda:0" if torch.cuda.is_available() else "cpu")

  # Load configs.
  env_cfg = load_env_cfg(task_id, play=False)
  agent_cfg = load_rl_cfg(task_id)

  motion_cmd = env_cfg.commands.get("motion")
  if not isinstance(motion_cmd, MotionCommandCfg):
    raise ValueError(f"Task {task_id} is not a tracking task.")

  if not Path(cfg.motion_file).exists():
    raise FileNotFoundError(f"Motion file not found: {cfg.motion_file}")
  motion_cmd.motion_file = cfg.motion_file

  # overwrite the duration_s to match the actual duration of the motion:
  motion_data = np.load(cfg.motion_file)
  env_cfg.episode_length_s = (motion_data["joint_pos"].shape[0] - 1) / motion_data[
    "fps"
  ].item()
  print(f"[INFO] Episode length set to {env_cfg.episode_length_s:.2f} s")

  # Evaluation config.
  motion_cmd.sampling_mode = "start"
  env_cfg.observations["actor"].enable_corruption = True
  env_cfg.events.pop("push_robot", None)
  env_cfg.scene.num_envs = cfg.num_envs

  env = ManagerBasedRlEnv(cfg=env_cfg, device=device)
  env = RslRlVecEnvWrapper(env, clip_actions=agent_cfg.clip_actions)

  if not Path(cfg.checkpoint_file).exists():
    raise FileNotFoundError(f"Checkpoint file not found: {cfg.checkpoint_file}")
  resume_path = cfg.checkpoint_file
  print(f"[INFO] Loading checkpoint: {resume_path}")

  runner_cls = load_runner_cls(task_id) or MjlabOnPolicyRunner
  runner = runner_cls(env, asdict(agent_cfg), device=device)
  runner.load(str(resume_path), map_location=device)
  policy = runner.get_inference_policy(device=device)

  command = cast(MotionCommand, env.unwrapped.command_manager.get_term("motion"))
  ee_body_names = env_cfg.terminations["ee_body_pos"].params["body_names"]
  print(f"[INFO] End effector bodies: {ee_body_names}")

  # Metric accumulators.
  all_mpkpe: list[torch.Tensor] = []
  all_r_mpkpe: list[torch.Tensor] = []
  all_joint_vel_error: list[torch.Tensor] = []
  all_ee_pos_error: list[torch.Tensor] = []
  all_ee_ori_error: list[torch.Tensor] = []
  all_joint_error: list[torch.Tensor] = []
  all_drift: list[torch.Tensor] = []
  all_active: list[torch.Tensor] = []
  record = {"time": [], "base_pos": [], "base_quat": [], "joint_pos": []}

  done_envs = torch.zeros(cfg.num_envs, dtype=torch.bool, device=device)
  success = torch.zeros(cfg.num_envs, dtype=torch.bool, device=device)

  failures = []

  obs = env.get_observations()

  print(f"[INFO] Running {cfg.num_envs} evaluation episodes...")

  step = 0
  while not done_envs.all():
    # reference for this step (env.step advances it after the reward)
    ref = SimpleNamespace(
      num_envs=command.num_envs,
      device=command.device,
      cfg=command.cfg,
      body_pos_w=command.body_pos_w.clone(),
      body_pos_relative_w=command.body_pos_relative_w.clone(),
      body_quat_relative_w=command.body_quat_relative_w.clone(),
      joint_vel=command.joint_vel.clone(),
      joint_pos=command.joint_pos.clone(),
      anchor_pos_w=command.anchor_pos_w.clone(),
    )

    with torch.no_grad():
      actions = policy(obs)
    obs, _, dones, _ = env.step(actions)

    # Pair the snapshotted reference with the post-step robot state.
    ref.robot_body_pos_w = command.robot_body_pos_w
    ref.robot_body_quat_w = command.robot_body_quat_w
    ref.robot_joint_vel = command.robot_joint_vel
    ref_command = cast(MotionCommand, ref)

    # envs reset inside env.step: skip their new episode
    active = ~done_envs & ~dones.bool()
    all_active.append(active.float())
    all_mpkpe.append(torch.where(active, compute_mpkpe(ref_command), 0.0))
    all_r_mpkpe.append(
      torch.where(active, compute_root_relative_mpkpe(ref_command), 0.0)
    )
    all_joint_vel_error.append(
      torch.where(active, compute_joint_velocity_error(ref_command), 0.0)
    )
    all_ee_pos_error.append(
      torch.where(active, compute_ee_position_error(ref_command, ee_body_names), 0.0)
    )
    all_ee_ori_error.append(
      torch.where(active, compute_ee_orientation_error(ref_command, ee_body_names), 0.0)
    )
    # same measures as analyze_ros2.py
    joint_error = (ref.joint_pos - command.robot_joint_pos).abs().mean(dim=-1)
    drift = torch.norm(
      ref.anchor_pos_w[:, :2] - command.robot_anchor_pos_w[:, :2], dim=-1
    )
    all_joint_error.append(torch.where(active, joint_error, 0.0))
    all_drift.append(torch.where(active, drift, 0.0))

    if cfg.record_file and active[0]:
      robot = command.robot.data
      record["time"].append((step + 1) / 50)
      record["base_pos"].append(robot.root_link_pos_w[0].cpu().numpy())
      record["base_quat"].append(robot.root_link_quat_w[0].cpu().numpy())
      record["joint_pos"].append(robot.joint_pos[0].cpu().numpy())

    # Track completions.
    terminated = env.unwrapped.termination_manager.terminated
    truncated = env.unwrapped.termination_manager.time_outs
    newly_done = dones.bool() & ~done_envs

    if newly_done.any():
      success = success | (newly_done & truncated & ~terminated)
      odd = newly_done & ~truncated & ~terminated
      failed = newly_done & terminated
      if failed.any():
        term_dones = env.unwrapped.termination_manager._term_dones
        for i in failed.nonzero().squeeze(-1).tolist():
          rules = [name for name, flags in term_dones.items() if flags[i]]
          print(
            f"[INFO] episode {i} failed at step {step} ({step / 50:.1f} s) by {rules}"
          )
          failures.append(
            {"episode": i, "step": step, "time_s": step / 50, "rules": rules}
          )
      if odd.any():
        ids = odd.nonzero().squeeze(-1)
        print(
          f"[DEBUG] step {step}: {len(ids)} episodes done with neither flag: {ids.tolist()}"
        )
        print(f"[DEBUG]   dones={dones[ids].tolist()}")
        print(
          f"[DEBUG]   episode_length_buf={env.unwrapped.episode_length_buf[ids].tolist()} "
          f"(max {env.unwrapped.max_episode_length})"
        )
        print(
          f"[DEBUG]   time_outs={env.unwrapped.termination_manager.time_outs[ids].tolist()}"
        )

      done_envs = done_envs | newly_done
      print(
        f"[INFO] {done_envs.sum().item()}/{cfg.num_envs} episodes completed "
        f"(step {step}, truncated={(newly_done & truncated).sum().item()}, "
        f"terminated={(newly_done & terminated).sum().item()})"
      )
    step += 1

  # Compute mean metrics over the steps each env was active.
  stacks = [
    all_mpkpe,
    all_r_mpkpe,
    all_joint_vel_error,
    all_ee_pos_error,
    all_ee_ori_error,
    all_joint_error,
    all_drift,
  ]
  stacks = [torch.stack(s, dim=0) for s in stacks]
  active_steps = torch.stack(all_active, dim=0).sum(dim=0).clamp(min=1)
  means = [s.sum(dim=0) / active_steps for s in stacks]

  max_mpkpe = stacks[0].max(dim=0).values
  max_r_mpkpe = stacks[1].max(dim=0).values
  max_drift = stacks[6].max(dim=0).values
  success_strict = success & (max_mpkpe <= 0.15)

  metrics = {
    "num_episodes": cfg.num_envs,
    "success_rate": success.float().mean().item(),
    "mpkpe": means[0].mean().item(),
    "r_mpkpe": means[1].mean().item(),
    "joint_vel_error": means[2].mean().item(),
    "ee_pos_error": means[3].mean().item(),
    "ee_ori_error": means[4].mean().item(),
    "max_mpkpe": max_mpkpe.mean().item(),
    "max_r_mpkpe": max_r_mpkpe.mean().item(),
    "success_rate_strict": success_strict.float().mean().item(),
    "joint_mae_rad": means[5].mean().item(),
    "drift_mean_m": means[6].mean().item(),
    "drift_max_m": max_drift.mean().item(),
  }

  print("\n" + "=" * 50)
  print("Evaluation Results")
  print("=" * 50)
  for name, value in metrics.items():
    print(f"  {name}: {value:.4f}")
  print("=" * 50)

  if cfg.output_file:
    output_path = Path(cfg.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
      json.dump({"metrics": metrics, "failures": failures}, f, indent=2)
    print(f"[INFO] Metrics saved to {output_path}")

  if cfg.record_file:
    np.savez_compressed(
      cfg.record_file,
      joint_names=np.array(command.robot.joint_names),
      base_frame=np.array("pelvis"),
      joint_time=np.array(record["time"]),
      base_time=np.array(record["time"]),
      base_pos=np.array(record["base_pos"]),
      base_quat=np.array(record["base_quat"]),
      joint_pos=np.array(record["joint_pos"]),
    )
    print(f"[INFO] Episode 0 pose saved to {cfg.record_file}")

  env.close()
  return metrics


def main():
  import mjlab.tasks

  tracking_tasks = [t for t in list_tasks() if "Tracking" in t]
  if not tracking_tasks:
    print("No tracking tasks found.")
    sys.exit(1)

  chosen_task, remaining_args = tyro.cli(
    tyro.extras.literal_type_from_choices(tracking_tasks),
    add_help=False,
    return_unknown_args=True,
    config=mjlab.TYRO_FLAGS,
  )

  args = tyro.cli(
    EvaluateConfig,
    args=remaining_args,
    prog=sys.argv[0] + f" {chosen_task}",
    config=mjlab.TYRO_FLAGS,
  )

  run_evaluate(chosen_task, args)


if __name__ == "__main__":
  main()
