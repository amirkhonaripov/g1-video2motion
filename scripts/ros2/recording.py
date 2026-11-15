"""Read a ROS 2 run recording (an mcap bag folder) without ROS: joints, head pose, odometry and the policy start."""

import struct
from pathlib import Path

import numpy as np
from mcap.exceptions import McapError
from mcap.records import Channel, Message, Schema
from mcap.stream_reader import StreamReader
from rosbags.typesys import Stores, get_typestore

TOPICS = ["/joint_states", "/mid360", "/odom", "/rosout"]
POLICY_SWITCH = "Activating controllers: [ walking_controller ]"
TYPES = get_typestore(Stores.ROS2_JAZZY)


def records(path):
  """MCAP records in file order; a recording cut off before its footer just ends early."""
  with open(path, "rb") as f:
    reader = StreamReader(f).records
    while True:
      try:
        yield next(reader)
      except (StopIteration, McapError, struct.error):
        return


def messages(bag):
  """(topic, message, receive time in s) of the recorded topics."""
  for path in sorted(Path(bag).glob("*.mcap"), key=lambda p: int(p.stem.rsplit("_", 1)[1])):
    schemas, channels = {}, {}
    for rec in records(path):
      if isinstance(rec, Schema):
        schemas[rec.id] = rec.name
      elif isinstance(rec, Channel):
        channels[rec.id] = (rec.topic, schemas[rec.schema_id])
      elif isinstance(rec, Message) and channels[rec.channel_id][0] in TOPICS:
        topic, msgtype = channels[rec.channel_id]
        yield topic, TYPES.deserialize_cdr(rec.data, msgtype), rec.log_time * 1e-9


def stamp(msg):
  return msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9


def pose_row(msg):
  # time, x, y, z, qw, qx, qy, qz
  p, q = msg.pose.pose.position, msg.pose.pose.orientation
  return [stamp(msg), p.x, p.y, p.z, q.w, q.x, q.y, q.z]


def read_recording(bag):
  """Arrays of one run; `policy_start_wall_time` only if the controller manager announced the policy on /rosout."""
  joints, head, odom, names, switch = [], [], [], None, None
  for topic, msg, received in messages(bag):
    if topic == "/joint_states":
      names = list(msg.name)
      joints.append([stamp(msg), received, *msg.position])
    elif topic == "/rosout":
      if msg.name == "controller_manager" and msg.msg.startswith(POLICY_SWITCH):
        switch = msg.stamp.sec + msg.stamp.nanosec * 1e-9  # system clock, like `received`
    elif topic == "/mid360":
      head.append(pose_row(msg))
    else:
      odom.append(pose_row(msg))
  joints, head, odom = np.array(joints), np.array(head), np.array(odom)
  run = {
    "joint_names": np.array(names),
    "joint_time": joints[:, 0],
    "joint_wall_time": joints[:, 1],  # when the recorder got it (system clock), to place the policy start in sim time
    "joint_pos": joints[:, 2:].astype(np.float32),
    "base_time": head[:, 0],
    "base_pos": head[:, 1:4],
    "base_quat": head[:, 4:8],
    "est_time": odom[:, 0],
    "est_pos": odom[:, 1:4],
    "est_quat": odom[:, 4:8],
  }
  if switch is not None:
    run["policy_start_wall_time"] = switch
  return run
