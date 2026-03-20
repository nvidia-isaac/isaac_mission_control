# Isaac Mission Control

## Overview

Mission Control is a lightweight fleet manager.  It coordinates Isaac Cloud Services and orchestrates them together. Missions are submitted to Mission Control, which will assemble a behavior tree of tasks to execute. It uses an occupancy grid map, a CSR (compressed sparse row) graph of that map provided by SWAGGER, optimal routes through that space provided by cuOpt, then leverages Mission Dispatch to execute that behavior tree using VDA5050 with Mission Client.
Internally at NVIDIA it is used as a development tool for a small AMR fleet to automate nightly testing of Isaac, delivery missions, and more.

## Prequisite and Related Services

- [Mission Dispatch](https://github.com/nvidia-isaac/isaac_mission_dispatch)
- [Mission Client](https://nvidia-isaac-ros.github.io/repositories_and_packages/isaac_ros_cloud_control/isaac_ros_mission_client/index.html)
- [SWAGGER](https://github.com/nvidia-isaac/SWAGGER) -- Waypoint Graph Generator - Container requires CUDA 12.5
- [cuOpt](https://docs.nvidia.com/cuopt/user-guide/latest/index.html) -- Container requires Ampere or Hopper GPU
- [IsaacSim](https://developer.nvidia.com/isaac/sim) -- Optional.  Tutorials use IsaacSim to demonstrate functionality.  Container requires RTX capable GPU

## API Reference

Visit [api.md](docs/api.md) for detail on the Mission Control API.

## Tutorials

Visit [tutorial.md](docs/tutorial/tutorial.md) for a step by step guide on how to use the Mission Control in an E2E Isaac Sim simulation.

Visit [config_tutorial.md](docs/config_tutorial.md) to understand the Mission Control config file.

Visit [objectives_doc.md](docs/objectives_doc.md) to understand how to create multi-robot objectives in Mission Control.

## Get Started

### Local Development

#### Clone the repo and submodule

To ensure that the sample map images get copied correctly, make sure that [Git LFS](https://git-lfs.com/) is installed

```
git clone https://github.com/nvidia-isaac/isaac_mission_control.git
```

#### Launch the Developer Docker Container

Use the Docker developer container to ensure correct dependencies when building and running applications through Bazel.

Create an [NVIDIA NGC account](https://catalog.ngc.nvidia.com) and login to the NGC docker registry:

  ```
  docker login nvcr.io
  ```

Launch the developer environment using:

  ```
  ./scripts/run_dev.sh
  ```

#### Verify the Provided Test Cases

Make sure that you are able to build and run the applications in the repo by running the unit tests within the Docker container:  

`bazel test ...`  

**Note**: If you're timing out on pulling images, `export PULLER_TIMEOUT=3000` and then add `--test_timeout=3000` in the test command.

#### Update the Configuration File

The default configuration file is located at `app/config/defaults.yaml`.  

Visit [config_tutorial.md](docs/config_tutorial.md) to understand the Mission Control config file.

\*\* Active Development \*\*  

In one run_dev.sh console:

```
docker compose -f docker-compose/bringup_services.yaml up
```

In a second run_dev.sh console:
```
bazel run -- app/mission-control-img-bundle && docker tag bazel_image mission-control
docker run -it --network host -v ./app/config:/tmp/config  mission-control  --verbose DEBUG --config /tmp/config/defaults.yaml
```

Developers can choose to run `mission-control` with the `--dev` option to enable tracebacks.

Best practice is to have simulated robots execute missions:

```
docker run -it --network host nvcr.io/nvidia/isaac/mission-simulator:4.3.0-amd64 --robots robot_a,4,5 robot_b,5,6

# Use nvcr.io/nvidia/isaac/mission-simulator:4.3.0-arm64 instead if on an ARM64 machine
```


```
docker compose -f docker-compose/bringup_services.yaml --profile enable_mission_control up
```

### Deploy with Docker Compose

If you want to start the whole stack, including Mission Control, from Docker Compose:

```
cd docker_compose
docker compose -f bringup_services.yaml --profile enable_mission_control up
# run `docker compose -f bringup_services.yaml --profile enable_mission_control down` if you want to bring down all the services.
```

If you're on a supported ARM64 machine such as the DGX Spark, run this instead:

```
cd docker_compose
docker compose -f bringup_services_arm64.yaml --profile enable_mission_control up
```

### Map Update Workflow

The workflow uses **three** steps:

1. **Upload** – store the new map image (+ optional YAML metadata) in Mission Control.
2. **Select** – make the uploaded map the *active* one for planning and regenerate the waypoint graph. **No robot is contacted in this step.**
3. **Update robot** – on demand, ask a specific robot to download & enable the map via instant-action missions.

Supported REST endpoints (prefixed with `/api/v1`):

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| `GET`  | `/map` | Download the image of the currently active map |
| `GET`  | `/map/metadata` | Retrieve metadata (resolution, origin, thresholds…) of the active map |
| `POST` | `/map/upload` | Upload a new map image and optional metadata YAML. Returns a `map_id`. |
| `GET`  | `/map/list` | List the IDs of all maps uploaded in the current Mission Control session |
| `GET`  | `/map/preview/{map_id}` | Download the image of an uploaded map without activating it |
| `POST` | `/map/select/{map_id}` | Activate the map and regenerate the planning graph (no robot update). |
| `POST` | `/map/update_robot/{robot_name}/{map_id}` | Trigger `downloadMap` + `enableMap` missions for *robot_name*. |

Note: `/map/update_robot/{robot_name}/{map_id}` returns HTTP 409 Conflict if the target robot is not IDLE or its status cannot be validated.

---

### Extend and use Mission Control

Robot fleet management has not been built into Mission Control at this time. Mission Control requires defaults be populated with robots that are under Mission Dispatch control in the defaults.yaml config file. If you choose to use another pre-loaded map, this can be changed in the same location.

### Waypoint Selection Tool

The Waypoint Selection Tool is a web-based interface for the creation and visualization of waypoint paths for robot navigation. It provides:

- Load and configure map images
- Select waypoints through an interactive interface
- Generate and visualize robot routes
- Export waypoint data for use with Mission Control

The tool is particularly useful for:

- Planning robot navigation paths
- Testing mission routes before deployment
- Visualizing robot trajectories
- Configuring waypoint-based missions

To get started with the Waypoint Selection Tool, see the [detailed documentation](waypoint_selection_ui/README.md).

### SAP EWM Integration (Optional)

Mission Control provides optional integration with SAP Extended Warehouse Management (EWM) for warehouse automation. 

**Note**: This integration is optional and only required if you're using SAP EWM for warehouse management. If you're not using SAP EWM, you can leave this integration disabled.

This integration allows Mission Control to:

- Receive and process warehouse orders from SAP EWM
- Convert warehouse tasks into navigation missions
- Assign robots to warehouse orders
- Track task completion status
- Manage warehouse resources (robots)

To enable SAP EWM integration:

1. Configure the SAP EWM settings in `app/config/defaults.yaml`:
   ```yaml
   sap:
     enable_sap_ewm: true
     base_url: "https://your-sap-ewm-server:50000"
     warehouse: "your_warehouse_id"
     username: "your_username"
     password: "your_password"
     max_orders_to_process: 1  # Set to 0 for unlimited
   ```

2. Ensure your SAP EWM system is accessible from Mission Control's network.

3. The integration will automatically:
   - Register available robots with SAP EWM
   - Process incoming warehouse orders
   - Convert warehouse tasks into navigation missions
   - Update task status in SAP EWM



### Troubleshooting and Common Issues

* Port in use
  * Some commonly used ports may be in conflict, for example, 5001 and datadog-agent.  You can update ports in `docker-compose/.env`

* Isaac Sim: CUDA Driver CALL FAILED
  * See the Isaac Sim documentation for references and workarounds
  * https://docs.isaacsim.omniverse.nvidia.com/4.5.0/overview/known_issues.html#errors

* Robot does circles around a waypoint failing to mark as complete
  * Verify your robot velocities are not too high, and that your planner/SLAM tolerances are set properly.

## VDA5050 Compatibility

Mission Control extends the standard VDA5050 AGV class specification to better support humanoid use cases. While the original VDA5050 specification defines the following AGV classes:
- `FORKLIFT`: Forklift
- `CONVEYOR`: AGV with conveyors
- `TUGGER`: Tugger
- `CARRIER`: Load carrier with or without lifting unit

Mission Control adds additional robot types to support more specialized use cases:

- `MANIPULATOR`: For static manipulator arms
- `HUMANOID`: For humanoid mobile robots

### Changelog

| Mission Control Version | Changes |
| ----- | ----- |
| 4.3.0 | ARM64 support for DGX Spark, Map distribution API |
| 4.0.0 | Objectives, navigate to exact position |
| 3.2.0 | Initial release |

### Version Compatibility

| Mission Control Version | Mission Client Version | Notes |
|------------------------|----------------------|-------|
| Latest | >= 3.2.0 | Uses extended VDA5050 AgvClass enum for robot types, including custom types beyond the VDA5050 specification |
| < 3.2.0 | < 3.2.0 | Uses VDA5050 specification |