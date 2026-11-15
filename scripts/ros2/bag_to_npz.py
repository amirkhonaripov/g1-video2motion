"""Convert ROS 2 run bags into small .npz files (needs ROS 2 sourced)."""

import argparse
from pathlib import Path

import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

TOPICS = ["/joint_states", "/mid360", "/odom", "/rosout"]
POLICY_SWITCH = "Activating controllers: [ walking_controller ]"


def parse_args():
  parser = argparse.ArgumentParser(description="Convert run bags to .npz")
  parser.add_argument("bags", nargs="+", help="bag folders")
  parser.add_argument("--out-dir", default="runs/npz", help="where to write the .npz")
  return parser.parse_args()


def stamp(msg):
  return msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9


def pose_row(msg):
  # time, x, y, z, qw, qx, qy, qz
  p, q = msg.pose.pose.position, msg.pose.pose.orientation
  return [stamp(msg), p.x, p.y, p.z, q.w, q.x, q.y, q.z]


def read_bag(path):
  reader = rosbag2_py.SequentialReader()
  reader.open(
    rosbag2_py.StorageOptions(uri=str(path), storage_id="mcap"),
    rosbag2_py.ConverterOptions("cdr", "cdr"),
  )
  types = {t.name: t.type for t in reader.get_all_topics_and_types()}
  reader.set_filter(rosbag2_py.StorageFilter(topics=TOPICS))

  joints, lidar, odom, names, switch = [], [], [], None, None
  while reader.has_next():
    topic, data, received = reader.read_next()
    msg = deserialize_message(data, get_message(types[topic]))
    if topic == "/joint_states":
      names = list(msg.name)
      joints.append([stamp(msg), received * 1e-9, *msg.position])
    elif topic == "/rosout":
      if msg.name == "controller_manager" and msg.msg.startswith(POLICY_SWITCH):
        switch = msg.stamp.sec + msg.stamp.nanosec * 1e-9  # system clock, like `received`
    elif topic == "/mid360":
      lidar.append(pose_row(msg))
    else:
      odom.append(pose_row(msg))
  return names, np.array(joints), np.array(lidar), np.array(odom), switch


def main():
  args = parse_args()
  out_dir = Path(args.out_dir)
  out_dir.mkdir(parents=True, exist_ok=True)

  for bag in args.bags:
    bag = Path(bag.rstrip("/"))
    names, joints, lidar, odom, switch = read_bag(bag)
    out = out_dir / f"{bag.name}.npz"
    extra = {} if switch is None else {"policy_start_wall_time": switch}
    np.savez_compressed(
      out,
      **extra,
      joint_names=np.array(names),
      joint_time=joints[:, 0],
      joint_wall_time=joints[:, 1],  # when the recorder got it (system clock), to place the policy start in sim time
      joint_pos=joints[:, 2:].astype(np.float32),
      base_frame=np.array("mid360"),
      base_time=lidar[:, 0],
      base_pos=lidar[:, 1:4],
      base_quat=lidar[:, 4:8],
      est_time=odom[:, 0],
      est_pos=odom[:, 1:4],
      est_quat=odom[:, 4:8],
    )
    print(f"{bag} -> {out}")


if __name__ == "__main__":
  main()
