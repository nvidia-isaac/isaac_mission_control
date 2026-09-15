# Objectives Tutorial

This tutorial demonstrates the Mission Control Objectives framework, which allows for complex mission orchestration using behavior trees with context resolution.

## Features Demonstrated

- Behavior tree composition (SEQUENCE, PARALLEL nodes)
- Context variable resolution using `$variable` syntax
- Multi-robot coordination
- Detection and manipulation workflows

## Prerequisites

- Isaac Sim 4.5 with ROS Humble
- Docker and docker-compose
- Isaac ROS VDA5050 packages

## Build Required Packages

Before running the tutorial, build the necessary mission client packages:

```bash
colcon build --packages-up-to isaac_ros_vda5050_nav2_client_bringup isaac_ros_apriltag 
```

This builds the mission client packages required for navigation and AprilTag detection.
### Isaac Manipulator Pick and Place related builds should be done already.

## Setup and Running Instructions

### Step 1: Launch Isaac Sim

1. Open Isaac Sim 4.5
2. Load the `two_carter_manipulator_warehouse.usd` scene

### Step 2: Prepare Terminals

You will need **5 terminals** total:
- 1 terminal for Mission Control
- 1 terminal for the manipulator Docker container
- 3 terminals for mission clients (arm01, carter01, carter02)

### Step 3: Launch Mission Clients

**Terminal 2 - Manipulator Client (arm01):**
```bash
ros2 launch isaac_ros_vda5050_nav2_client_bringup isaac_ros_vda5050_apriltag_client.launch.py \
    robot_type:=arm \
    launch_ws_bridge:=True \
    serial_number:=arm01 \
    apriltag_target_frame:=base_link \
    apriltag_transform_mode:=static \
    apriltag_transform_timeout:=1.0 \
    apriltag_detection_timout:=1.5 \
    initial_x:=1.42 \
    initial_y:=0.082 \
    initial_theta:=0.0
```

**Terminal 3 - Carter01 Client:**
```bash
ros2 launch isaac_ros_vda5050_nav2_client_bringup isaac_ros_vda5050_nav2_client.launch.py \
    namespace:=carter01 \
    use_namespace:=True \
    serial_number:=carter01 \
    odom_topic:=/carter01/chassis/odom \
    battery_state_topic:=/carter01/chassis/battery_state \
    status_check_service:=/carter01/velocity_smoother/get_state \
    init_pose_x:=0.0 \
    init_pose_y:=4.0 \
    init_pose_yaw:=0.0
```

**Terminal 4 - Carter02 Client:**
```bash
ros2 launch isaac_ros_vda5050_nav2_client_bringup isaac_ros_vda5050_nav2_client.launch.py \
    namespace:=carter02 \
    use_namespace:=True \
    serial_number:=carter02 \
    odom_topic:=/carter02/chassis/odom \
    battery_state_topic:=/carter02/chassis/battery_state \
    status_check_service:=/carter02/velocity_smoother/get_state \
    init_pose_x:=-3.0 \
    init_pose_y:=2.0 \
    init_pose_yaw:=0.0
```

### Step 4: Launch Mission Control

**Terminal 1 - Mission Control:**
```bash
cd ~/workspaces/mission-control/docs/objectives_tutorial
docker-compose -f docker-compose/bringup_services_tutorial.yaml up
```

### Step 5: Submit Example Objective

1. Open the Mission Control API interface (typically at `http://localhost:8050/api/v1/docs`)
2. Navigate to the `submit_objective` endpoint
3. Use the following example objective JSON:

```json
{
  "node_class": "COMPOSITE",
  "node_type": "SEQUENCE", 
  "children": [
    {
      "node_class": "COMPOSITE",
      "node_type": "PARALLEL",
      "children": [
        {
          "node_class": "COMPOSITE", 
          "node_type": "SEQUENCE",
          "children": [
            {
              "node_class": "BEHAVIOR",
              "node_type": "NAVIGATION",
              "parameters": {
                "robot_name": "carter01",
                "route": [],
                "end_location": {"x": 1.75, "y": 1.0, "theta": 0, "exact": true}
              }
            },
            {
              "node_class": "BEHAVIOR", 
              "node_type": "APRILTAG_DETECTION",
              "parameters": {"robot_name": "arm01"},
              "outputs": {"tags_pose_by_id": "tags_pose1"}
            },
            {
              "node_class": "BEHAVIOR",
              "node_type": "PICKPLACE", 
              "parameters": {
                "robot_name": "arm01",
                "object_id": "$object_ids['3'][0]",
                "class_id": "3",
                "pos_x": "$tags_pose1['2'].pos_x",
                "pos_y": "$tags_pose1['2'].pos_y", 
                "pos_z": "$tags_pose1['2'].pos_z",
                "pos_z_offset": 0.3,
                "quat_x": 0.996,
                "quat_y": 0.066,
                "quat_z": 0.042,
                "quat_w": 0.034
              }
            }
          ]
        },
        {
          "node_class": "BEHAVIOR",
          "node_type": "NAVIGATION", 
          "parameters": {
            "robot_name": "carter02",
            "route": [],
            "end_location": {"x": 1.1, "y": 2.5, "theta": -1.5708, "exact": true}
          }
        },
        {
          "node_class": "BEHAVIOR",
          "node_type": "OBJ_DETECTION",
          "parameters": {"robot_name": "arm01"}, 
          "outputs": {
            "object_id_by_class": "object_ids",
            "object_pose2D_by_class": "object_poses1"
          }
        }
      ]
    },
    {
      "node_class": "COMPOSITE",
      "node_type": "PARALLEL",
      "children": [
        {
          "node_class": "BEHAVIOR",
          "node_type": "NAVIGATION",
          "parameters": {
            "robot_name": "carter01", 
            "route": [],
            "end_location": {"x": 5.0, "y": 5.0, "exact": false}
          }
        },
        {
          "node_class": "COMPOSITE",
          "node_type": "SEQUENCE",
          "children": [
            {
              "node_class": "BEHAVIOR",
              "node_type": "NAVIGATION",
              "parameters": {
                "robot_name": "carter02",
                "route": [],
                "end_location": {"x": 1.5, "y": 1.0, "theta": 0, "exact": true}
              }
            },
            {
              "node_class": "BEHAVIOR", 
              "node_type": "APRILTAG_DETECTION",
              "parameters": {"robot_name": "arm01"},
              "outputs": {"tags_pose_by_id": "tags_pose2"}
            },
            {
              "node_class": "BEHAVIOR",
              "node_type": "PICKPLACE",
              "parameters": {
                "robot_name": "arm01",
                "object_id": "$object_ids['3'][1]",
                "class_id": "3", 
                "pos_x": "$tags_pose2['0'].pos_x",
                "pos_y": "$tags_pose2['0'].pos_y",
                "pos_z": "$tags_pose2['0'].pos_z",
                "pos_z_offset": 0.3,
                "quat_x": 0.996,
                "quat_y": 0.066,
                "quat_z": 0.042,
                "quat_w": 0.034
              }
            },
            {
              "node_class": "BEHAVIOR", 
              "node_type": "NAVIGATION",
              "parameters": {
                "robot_name": "carter02",
                "route": [],
                "end_location": {"x": 4.0, "y": 4.0, "exact": false}
              }
            }
          ]
        }
      ]
    }
  ]
}
```

## What This Example Demonstrates

This complex objective showcases:

1. **Parallel Execution**: Multiple robots operating simultaneously
2. **Context Resolution**: Using `$variable` syntax to reference detected objects and poses
3. **Sequential Dependencies**: AprilTag detection feeding into pick-and-place operations
4. **Multi-Robot Coordination**: Carter robots navigating while the arm performs manipulation tasks onto the carters

## Differences from Main Tutorial

This tutorial includes:
- Manipulator robot configuration (`arm01`)
- Modified map configuration for warehouse operations
- Objectives framework examples with behavior trees
- Context resolution demonstrations

For the basic tutorial without objectives framework, see the main `docs/tutorial/` directory. 