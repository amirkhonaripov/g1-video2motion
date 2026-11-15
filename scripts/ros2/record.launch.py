"""Run a policy in the ROS 2 stack's MuJoCo sim and record the run for scoring.

ros2 launch scripts/ros2/record.launch.py policy_path:=/abs/path/policy.onnx bag:=runs/bags/<run>
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare

TOPICS = ["/joint_states", "/mid360", "/odom", "/rosout"]


def generate_launch_description():
  record = ExecuteProcess(
    cmd=["ros2", "bag", "record", "-s", "mcap", "-o", LaunchConfiguration("bag"), "--topics", *TOPICS],
    output="screen",
  )
  sim = IncludeLaunchDescription(
    PythonLaunchDescriptionSource(
      PathJoinSubstitution([FindPackageShare("motion_tracking_controller"), "launch", "mujoco.launch.py"])
    ),
    launch_arguments={"policy_path": LaunchConfiguration("policy_path")}.items(),
  )
  return LaunchDescription([
    DeclareLaunchArgument("policy_path", description="absolute path of the policy .onnx"),
    DeclareLaunchArgument("bag", description="output bag folder (must not exist yet)"),
    record,
    TimerAction(period=3.0, actions=[sim]),  # recorder first, so the run is recorded from its first message
  ])
