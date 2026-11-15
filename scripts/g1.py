"""G1 constants and helpers shared by the scripts (numpy only)."""

import numpy as np

G1_XML = "third_party/g1-eval-harness/assets/g1/g1_29dof_ros2.xml"
STRICT_MPKPE_M = 0.15  # PHUMA's strict success

# BeyondMimic's termination rules (mjlab), as in the eval harness (harness/config.py)
TRACKING_ANCHOR_BODY = "torso_link"
TRACKING_ANCHOR_HEIGHT_M = 0.25  # |reference - robot| anchor height
TRACKING_ANCHOR_GRAVITY = 0.8  # |reference - robot| projected-gravity z of the anchor
TRACKING_END_EFFECTOR_HEIGHT_M = 0.25
TRACKING_END_EFFECTORS = (
  "left_ankle_roll_link",
  "right_ankle_roll_link",
  "left_wrist_yaw_link",
  "right_wrist_yaw_link",
)

# real fall: head (mid360 lidar) below this for over REAL_FALL_TIME_S, or still below when the motion ends
REAL_FALL_HEAD_HEIGHT_M = 0.5
REAL_FALL_TIME_S = 2.0

# ROS 2 start-up drop: head below this at the first joint sample (falling before the controllers are up)
STARTUP_DROP_HEAD_M = 1.15

# mjlab's order, same as GMR's unitree_g1
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

# ViT-H's order (IsaacLab)
VITH_JOINT_NAMES = [
  "left_hip_pitch_joint",
  "right_hip_pitch_joint",
  "waist_yaw_joint",
  "left_hip_roll_joint",
  "right_hip_roll_joint",
  "waist_roll_joint",
  "left_hip_yaw_joint",
  "right_hip_yaw_joint",
  "waist_pitch_joint",
  "left_knee_joint",
  "right_knee_joint",
  "left_shoulder_pitch_joint",
  "right_shoulder_pitch_joint",
  "left_ankle_pitch_joint",
  "right_ankle_pitch_joint",
  "left_shoulder_roll_joint",
  "right_shoulder_roll_joint",
  "left_ankle_roll_joint",
  "right_ankle_roll_joint",
  "left_shoulder_yaw_joint",
  "right_shoulder_yaw_joint",
  "left_elbow_joint",
  "right_elbow_joint",
  "left_wrist_roll_joint",
  "right_wrist_roll_joint",
  "left_wrist_pitch_joint",
  "right_wrist_pitch_joint",
  "left_wrist_yaw_joint",
  "right_wrist_yaw_joint",
]

# (label, folder under data/motions, ViT-H sample suffix)
METHODS = [
  ("GVHMR + GMR", "gmr", ""),
  ("ViT-H sample 1", "vith", ""),
  ("ViT-H sample 2", "vith", "_s2"),
  ("ViT-H sample 3", "vith", "_s3"),
]


def yaw(quat):
  """Heading (rad) of wxyz quaternions."""
  w, x, y, z = np.moveaxis(np.asarray(quat), -1, 0)
  return np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


def gravity_z(quat):
  """z of world gravity seen from bodies with these wxyz orientations (-1 when upright)."""
  _, x, y, _ = np.moveaxis(np.asarray(quat), -1, 0)
  return 2 * (x * x + y * y) - 1


def turn_xy(vectors, angle):
  """Rotate vectors about z."""
  c, s = np.cos(angle), np.sin(angle)
  out = vectors.copy()
  out[..., 0] = c * vectors[..., 0] - s * vectors[..., 1]
  out[..., 1] = s * vectors[..., 0] + c * vectors[..., 1]
  return out
