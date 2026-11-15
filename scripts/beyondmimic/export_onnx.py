"""Export a trained BeyondMimic policy (.pt) to ONNX, with its reference motion saved next to it."""

import argparse
from dataclasses import asdict
from pathlib import Path

import mjlab.tasks  # noqa: F401  registers the tasks
import numpy as np
import onnx
import torch
from mjlab.envs import ManagerBasedRlEnv
from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
from mjlab.rl.exporter_utils import attach_metadata_to_onnx
from mjlab.tasks.registry import list_tasks, load_env_cfg, load_rl_cfg, load_runner_cls
from mjlab.tasks.tracking.mdp import MotionCommandCfg
from onnx import numpy_helper


def parse_args():
  parser = argparse.ArgumentParser(description="Export a tracking policy to ONNX")
  parser.add_argument("task", choices=[t for t in list_tasks() if "Tracking" in t])
  parser.add_argument("--motion-file", required=True, help="motion .npz baked into the ONNX file")
  parser.add_argument("--checkpoint-file", required=True, help="trained policy checkpoint .pt")
  parser.add_argument("--output-file", default="runs/onnx/policy.onnx")
  return parser.parse_args()


def save_reference(onnx_path):
  """Save the motion baked into the ONNX file as reference.npz next to it."""
  model = onnx.load(str(onnx_path))
  meta = {p.key: p.value for p in model.metadata_props}
  arrays = {i.name.split(".")[0]: numpy_helper.to_array(i) for i in model.graph.initializer}
  out = onnx_path.with_name("reference.npz")
  np.savez(
    out,
    joint_pos=arrays["joint_pos"],
    body_pos_w=arrays["body_pos_w"],
    body_quat_w=arrays["body_quat_w"],
    joint_names=np.array(meta["joint_names"].split(",")),
    body_names=np.array(meta["body_names"].split(",")),
  )
  return out


def export(task, motion_file, checkpoint_file, output_file):
  """Build a one-robot environment, load the policy and export it to ONNX."""
  device = "cuda:0" if torch.cuda.is_available() else "cpu"
  env_cfg = load_env_cfg(task, play=False)
  agent_cfg = load_rl_cfg(task)
  motion_cmd = env_cfg.commands.get("motion")
  if not isinstance(motion_cmd, MotionCommandCfg):
    raise ValueError(f"Task {task} is not a tracking task.")
  for path in (motion_file, checkpoint_file):
    if not Path(path).exists():
      raise FileNotFoundError(path)
  motion_cmd.motion_file = motion_file
  env_cfg.scene.num_envs = 1

  env = RslRlVecEnvWrapper(ManagerBasedRlEnv(cfg=env_cfg, device=device), clip_actions=agent_cfg.clip_actions)
  runner_cls = load_runner_cls(task) or MjlabOnPolicyRunner
  runner = runner_cls(env, asdict(agent_cfg), device=device)
  runner.load(checkpoint_file, map_location=device)

  out = Path(output_file)
  runner.export_policy_to_onnx(str(out.parent), out.name)
  attach_metadata_to_onnx(str(out), runner.get_export_metadata("local"))
  print(f"[INFO] Exported ONNX policy to {out}")
  print(f"[INFO] Saved reference motion to {save_reference(out)}")
  env.close()


def main():
  args = parse_args()
  export(args.task, args.motion_file, args.checkpoint_file, args.output_file)


if __name__ == "__main__":
  main()
