import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import torch
import tyro

import mjlab
import mjlab.tasks
from mjlab.envs import ManagerBasedRlEnv
from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
from mjlab.rl.exporter_utils import attach_metadata_to_onnx
from mjlab.tasks.registry import list_tasks, load_env_cfg, load_rl_cfg, load_runner_cls
from mjlab.tasks.tracking.mdp import MotionCommandCfg


@dataclass(frozen=True)
class ExportConfig:
  """Configuration for ONNX export."""

  motion_file: str
  """Path to the motion .npz baked into the ONNX file."""
  checkpoint_file: str
  """Path to the trained policy checkpoint (.pt)."""
  output_file: str = "runs/onnx/policy.onnx"
  """Where to write the ONNX file."""
  run_name: str = "local"
  """Label stored in the ONNX metadata."""


def run_export(task_id: str, cfg: ExportConfig) -> None:
  """Build a one-robot environment, load the policy and export it to ONNX."""
  device = "cuda:0" if torch.cuda.is_available() else "cpu"

  env_cfg = load_env_cfg(task_id, play=False)
  agent_cfg = load_rl_cfg(task_id)

  motion_cmd = env_cfg.commands.get("motion")
  if not isinstance(motion_cmd, MotionCommandCfg):
    raise ValueError(f"Task {task_id} is not a tracking task.")
  if not Path(cfg.motion_file).exists():
    raise FileNotFoundError(f"Motion file not found: {cfg.motion_file}")
  motion_cmd.motion_file = cfg.motion_file
  env_cfg.scene.num_envs = 1

  env = ManagerBasedRlEnv(cfg=env_cfg, device=device)
  env = RslRlVecEnvWrapper(env, clip_actions=agent_cfg.clip_actions)

  if not Path(cfg.checkpoint_file).exists():
    raise FileNotFoundError(f"Checkpoint file not found: {cfg.checkpoint_file}")
  runner_cls = load_runner_cls(task_id) or MjlabOnPolicyRunner
  runner = runner_cls(env, asdict(agent_cfg), device=device)
  runner.load(cfg.checkpoint_file, map_location=device)

  out = Path(cfg.output_file)
  runner.export_policy_to_onnx(str(out.parent), out.name)
  metadata = runner.get_export_metadata(cfg.run_name)
  attach_metadata_to_onnx(str(out), metadata)
  print(f"[INFO] Exported ONNX policy to {out}")

  env.close()


def main():
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
    ExportConfig,
    args=remaining_args,
    prog=sys.argv[0] + f" {chosen_task}",
    config=mjlab.TYRO_FLAGS,
  )
  run_export(chosen_task, args)


if __name__ == "__main__":
  main()
