"""Evaluate a trained BeyondMimic policy in mjlab and compute tracking metrics."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import mjlab.tasks  # noqa: F401  registers the tasks
import numpy as np
import torch
from mjlab.envs import ManagerBasedRlEnv
from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
from mjlab.tasks.registry import list_tasks, load_env_cfg, load_rl_cfg, load_runner_cls
from mjlab.tasks.tracking.mdp import MotionCommandCfg
from mjlab.tasks.tracking.mdp.metrics import (
  compute_ee_orientation_error,
  compute_ee_position_error,
  compute_joint_velocity_error,
  compute_mpkpe,
  compute_root_relative_mpkpe,
)
from mjlab.utils.torch import configure_torch_backends

from scripts.g1 import STRICT_MPKPE_M

METRICS = ["mpkpe", "r_mpkpe", "joint_vel_error", "ee_pos_error", "ee_ori_error", "joint_mae_rad", "drift"]


def parse_args():
  parser = argparse.ArgumentParser(description="Evaluate a tracking policy in mjlab")
  parser.add_argument("task", choices=[t for t in list_tasks() if "Tracking" in t])
  parser.add_argument("--motion-file", required=True, help="motion .npz to track")
  parser.add_argument("--checkpoint-file", required=True, help="trained policy checkpoint .pt")
  parser.add_argument("--output-file", help="write the metrics as JSON")
  parser.add_argument("--num-envs", type=int, default=1024, help="parallel environments = episodes")
  return parser.parse_args()


def make_env(task, motion_file, num_envs, device):
  env_cfg = load_env_cfg(task, play=False)
  agent_cfg = load_rl_cfg(task)
  motion_cmd = env_cfg.commands.get("motion")
  if not isinstance(motion_cmd, MotionCommandCfg):
    raise ValueError(f"Task {task} is not a tracking task.")
  if not Path(motion_file).exists():
    raise FileNotFoundError(motion_file)
  motion_cmd.motion_file = motion_file
  motion = np.load(motion_file)
  env_cfg.episode_length_s = (motion["joint_pos"].shape[0] - 1) / motion["fps"].item()
  print(f"[INFO] Episode length set to {env_cfg.episode_length_s:.2f} s")
  motion_cmd.sampling_mode = "start"
  env_cfg.observations["actor"].enable_corruption = True
  env_cfg.events.pop("push_robot", None)
  env_cfg.scene.num_envs = num_envs
  env = RslRlVecEnvWrapper(ManagerBasedRlEnv(cfg=env_cfg, device=device), clip_actions=agent_cfg.clip_actions)
  return env, env_cfg, agent_cfg


def load_policy(task, env, agent_cfg, checkpoint_file, device):
  if not Path(checkpoint_file).exists():
    raise FileNotFoundError(checkpoint_file)
  print(f"[INFO] Loading checkpoint: {checkpoint_file}")
  runner_cls = load_runner_cls(task) or MjlabOnPolicyRunner
  runner = runner_cls(env, asdict(agent_cfg), device=device)
  runner.load(checkpoint_file, map_location=device)
  return runner.get_inference_policy(device=device)


def snapshot(command):
  """The reference for this step (env.step advances it after the reward)."""
  return SimpleNamespace(
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


def step_errors(ref, command, ee_body_names):
  """Per-env errors of the post-step robot against the snapshotted reference."""
  ref.robot_body_pos_w = command.robot_body_pos_w
  ref.robot_body_quat_w = command.robot_body_quat_w
  ref.robot_joint_vel = command.robot_joint_vel
  return {
    "mpkpe": compute_mpkpe(ref),
    "r_mpkpe": compute_root_relative_mpkpe(ref),
    "joint_vel_error": compute_joint_velocity_error(ref),
    "ee_pos_error": compute_ee_position_error(ref, ee_body_names),
    "ee_ori_error": compute_ee_orientation_error(ref, ee_body_names),
    "joint_mae_rad": (ref.joint_pos - command.robot_joint_pos).abs().mean(dim=-1),
    "drift": torch.norm(ref.anchor_pos_w[:, :2] - command.robot_anchor_pos_w[:, :2], dim=-1),
  }


def evaluate(env, policy, num_envs, ee_body_names, device):
  """Run every env through one episode; per-step errors (masked to active envs), success and failures."""
  unwrapped = env.unwrapped
  command = unwrapped.command_manager.get_term("motion")
  policy_hz = 1 / unwrapped.step_dt
  errors = {k: [] for k in METRICS}
  all_active = []
  done_envs = torch.zeros(num_envs, dtype=torch.bool, device=device)
  success = torch.zeros(num_envs, dtype=torch.bool, device=device)
  failures = []
  obs = env.get_observations()
  print(f"[INFO] Running {num_envs} evaluation episodes...")

  step = 0
  while not done_envs.all():
    ref = snapshot(command)
    with torch.no_grad():
      actions = policy(obs)
    obs, _, dones, _ = env.step(actions)

    active = ~done_envs & ~dones.bool()  # envs reset inside env.step: skip their new episode
    all_active.append(active.float())
    for k, v in step_errors(ref, command, ee_body_names).items():
      errors[k].append(torch.where(active, v, 0.0))

    terminated = unwrapped.termination_manager.terminated
    truncated = unwrapped.termination_manager.time_outs
    newly_done = dones.bool() & ~done_envs
    if newly_done.any():
      success = success | (newly_done & truncated & ~terminated)
      failed = newly_done & terminated
      term_dones = unwrapped.termination_manager._term_dones
      for i in failed.nonzero().squeeze(-1).tolist():
        rules = [name for name, flags in term_dones.items() if flags[i]]
        print(f"[INFO] episode {i} failed at step {step} ({step / policy_hz:.1f} s) by {rules}")
        failures.append({"episode": i, "step": step, "time_s": step / policy_hz, "rules": rules})
      done_envs = done_envs | newly_done
      print(
        f"[INFO] {done_envs.sum().item()}/{num_envs} episodes completed "
        f"(step {step}, truncated={(newly_done & truncated).sum().item()}, "
        f"terminated={(newly_done & terminated).sum().item()})"
      )
    step += 1
  return {k: torch.stack(v) for k, v in errors.items()}, torch.stack(all_active), success, failures


def summarize(errors, active, success, num_envs):
  """Means over the steps each env was active, then over envs."""
  steps = active.sum(dim=0).clamp(min=1)
  mean = {k: (v.sum(dim=0) / steps).mean().item() for k, v in errors.items()}
  worst = {k: errors[k].max(dim=0).values for k in ("mpkpe", "r_mpkpe", "drift")}
  return {
    "num_episodes": num_envs,
    "success_rate": success.float().mean().item(),
    "mpkpe": mean["mpkpe"],
    "r_mpkpe": mean["r_mpkpe"],
    "joint_vel_error": mean["joint_vel_error"],
    "ee_pos_error": mean["ee_pos_error"],
    "ee_ori_error": mean["ee_ori_error"],
    "max_mpkpe": worst["mpkpe"].mean().item(),
    "max_r_mpkpe": worst["r_mpkpe"].mean().item(),
    "success_rate_strict": (success & (worst["mpkpe"] <= STRICT_MPKPE_M)).float().mean().item(),
    "joint_mae_rad": mean["joint_mae_rad"],
    "drift_mean_m": mean["drift"],
    "drift_max_m": worst["drift"].mean().item(),
  }


def main():
  args = parse_args()
  configure_torch_backends()
  device = "cuda:0" if torch.cuda.is_available() else "cpu"
  env, env_cfg, agent_cfg = make_env(args.task, args.motion_file, args.num_envs, device)
  policy = load_policy(args.task, env, agent_cfg, args.checkpoint_file, device)
  ee_body_names = env_cfg.terminations["ee_body_pos"].params["body_names"]
  print(f"[INFO] End effector bodies: {ee_body_names}")

  errors, active, success, failures = evaluate(env, policy, args.num_envs, ee_body_names, device)
  metrics = summarize(errors, active, success, args.num_envs)
  print("\n" + "=" * 50 + "\nEvaluation Results\n" + "=" * 50)
  for name, value in metrics.items():
    print(f"  {name}: {value:.4f}")
  print("=" * 50)

  if args.output_file:
    out = Path(args.output_file)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
      json.dump({"metrics": metrics, "failures": failures}, f, indent=2)
    print(f"[INFO] Metrics saved to {out}")
  env.close()


if __name__ == "__main__":
  main()
