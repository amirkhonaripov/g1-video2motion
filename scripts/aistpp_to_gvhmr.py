"""AIST++ motion capture (.pkl) -> GVHMR-style hmr4d_results.pt at 30 fps, feet on the floor, for GMR."""

import argparse
import pickle

import numpy as np
import smplx
import torch

FEET = [7, 8, 10, 11]
FOOT_ON_FLOOR = 0.044  # lowest foot joint height in GVHMR's output (m)


def parse_args():
  parser = argparse.ArgumentParser(description="AIST++ to GVHMR format")
  parser.add_argument("input_file", help="AIST++ motions/<sequence>.pkl (60 fps)")
  parser.add_argument("--output-file", required=True)
  parser.add_argument("--body-models", default="assets/body_models", help="GMR's SMPL-X folder")
  return parser.parse_args()


def foot_floor(params, body_models):
  n = len(params["transl"])
  zeros = {k: torch.zeros(n, d) for k, d in [("left_hand_pose", 45), ("right_hand_pose", 45), ("jaw_pose", 3),
                                             ("leye_pose", 3), ("reye_pose", 3), ("expression", 10)]}
  model = smplx.create(body_models, "smplx", gender="neutral", use_pca=False)
  out = model(betas=torch.zeros(1, 16), global_orient=params["global_orient"], body_pose=params["body_pose"],
              transl=params["transl"], **zeros)
  return out.joints[:, FEET, 1].min().item()


def main():
  args = parse_args()
  with open(args.input_file, "rb") as f:
    seq = pickle.load(f)
  poses = seq["smpl_poses"][::2]
  params = {
    "global_orient": torch.tensor(poses[:, :3]).float(),
    "body_pose": torch.tensor(poses[:, 3:66]).float(),
    "transl": torch.tensor(seq["smpl_trans"][::2] / seq["smpl_scaling"]).float(),
    "betas": torch.zeros(len(poses), 10),
  }
  params["transl"][:, 1] -= foot_floor(params, args.body_models) - FOOT_ON_FLOOR
  torch.save({"smpl_params_global": params}, args.output_file)
  print(f"[INFO] {len(poses)} frames at 30 fps -> {args.output_file}")


if __name__ == "__main__":
  main()
