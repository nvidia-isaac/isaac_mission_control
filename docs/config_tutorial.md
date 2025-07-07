# Understanding the Mission Control Config File

Mission Control takes a YAML config file at startup. This config file is used to configure the:
- robots that Mission Control will manage and their properties
- URLs and ports of the services that Mission Control depends on
- map and its metadata that Mission Control will use for route planning
- constants that Mission Control will use

Example config file:
<details>
<summary>Click to expand</summary>

```yaml
robots:
  - name: "carter01"
    labels: ["test", "carter", "ros"]
    heartbeat_timeout: 30

services:
  waypoint_graph:
    base_url: "http://127.0.0.1:8000"
  mission_database:
    base_url: "http://127.0.0.1:5003"
  mission_dispatch:
    base_url: "http://127.0.0.1:5002"
    default_mission_timeout: 900
  cuopt:
    base_url: "http://127.0.0.1:5050"
    solve_parameters:
      time_limit: .5
      verbose_mode: False

map:
  # One and only one of map_file, map_uri, or map_s3 must be set
  map_file: ""
# map_uri: ""
# map_s3: ""
  metadata_yaml: ""

  # metadata is needed if metadata_yaml is not provided
  metadata:
    map_id: "galileo_hubble"
    resolution: 0.05
    occupancy_threshold: 206
    x_offset: 0.0
    y_offset: 0.0
    rotation: 0.0
    safety_distance: 0.45
  push_map_on_startup: False

  docks:
    - dock_id: dock01
      dock_type: nova_carter_dock
      dock_pose:
        x: 43.7278
        y: 19.7377
        yaw: 1.36224
  
constants:
  MIN_BATTERY: 0.0

telemetry:
  SEND_TELEMETRY: False
  TELEMETRY_ID: ""
  TELEMETRY_SECRET: ""
  TELEMETRY_ENV: "DEV" # {DEV | TEST | PROD}

s3:
  AWS_ACCESS_KEY_ID: ""
  AWS_SECRET_ACCESS_KEY: ""
  AWS_REGION: ""
  AWS_ENDPOINT_URL: ""
```
</details>

### robots

The `robots` section takes in a list of YAML objects that is used to configure the robots that Mission Control will manage and their properties. If the robot is not already registered with Mission Dispatch, Mission Control will register it along with the provided labels and heartbeat timeout.

```yaml
robots:
  - name: "carter01"
    labels: ["test", "carter", "ros"]
    heartbeat_timeout: 30
  - name: "carter02"
    labels: ["test", "carter", "ros"]
    heartbeat_timeout: 30
```
| Element | Required? | Type | Description |
| ----------- | ----------- | ---- | ------------|
| name | yes | string | The unique identifier of the robot. |
| labels | no | list[string] | A list of labels to assign to the robot. Not currently used in any logic. |
| heartbeat_timeout | no | int | The timeout for the robot's heartbeat in seconds. |

### services

The `services` section is used to configure the URLs and ports of the services that Mission Control depends on. The values used in the example are default values, you must update them to match your setup as needed.

```yaml
services:
  waypoint_graph:
    base_url: "http://127.0.0.1:8000"
  mission_database:
    base_url: "http://127.0.0.1:5003"
  mission_dispatch:
    base_url: "http://127.0.0.1:5002"
    default_mission_timeout: 900  # Default timeout for a mission in seconds
  cuopt:
    base_url: "http://127.0.0.1:5050"
    # Optional parameters for cuopt
    solve_parameters:
      time_limit: 60  # Time limit for the cuopt solver to generate a path in seconds
      verbose_mode: False  # Whether to print verbose output from the cuopt solver
```

### map

The `map` section is used to configure the map that Mission Control will use for route planning. The map image and its metadata will be provided to the Waypoint Graph Generator service to generate a navigable graph from the map.

```yaml
map:
  # One and only one of map_file, map_uri, or map_s3 must be set
  map_file: ""  # Path to a local map file
  map_uri: ""  # URL to a map file
  map_s3: ""  # S3 URL to a map file

  # Link to a yaml file that contains metadata about the map. This can either be a local file or an S3 URL.
  # If metadata_yaml is valid, the metadata section will be ignored.
  metadata_yaml: ""
  # Metadata section is required, if the metadata_yaml is not provided.
  metadata:
    map_id: "map_id"
    resolution: 0.05 # The size of each pixel in meters
    occupancy_threshold: 206  # (0-255) Threshold for which cells are considered free space.
    x_offset: 0.0  # The X coordinate of the bottom-left pixel in the world frame in meters.
    y_offset: 0.0  # The Y coordinate of the bottom-left pixel in the world frame in meters.
    rotation: 0.0  # Rotation angle from image frame to world frame in radians.
    safety_distance: 0.45  # The minimum distance (in meters) that graph nodes and edges must maintain from obstacles to ensure safe robot navigation.

  push_map_on_startup: False  # Whether to send the map loading action on startup.

  # Configure the docks that Mission Control will use.
  docks:
    - dock_id: dock01  # The unique identifier of the dock.
      dock_type: nova_carter_dock  # The type of dock.
      dock_pose:
        x: 0.0 # The X coordinate of the dock in the world frame in meters.
        y: 0.0  # The Y coordinate of the dock in the world frame in meters.
        yaw: 0.0  # The yaw angle of the dock in the world frame in radians.
```
### constants

The `constants` section is used to configure the constants that Mission Control will use.

```yaml
constants:
  MIN_BATTERY: 0.0  # The minimum battery level that a robot can have before it cannot accept navigation missions.
  STARTUP_TIMEOUT: 1200  # The timeout that Mission Control will wait for its dependencies to start up in seconds.
```

### telemetry

The `telemetry` section is used to configure the telemetry that Mission Control will send.

```yaml
telemetry:
  SEND_TELEMETRY: False
  TELEMETRY_ID: ""
  TELEMETRY_SECRET: ""
  TELEMETRY_ENV: "DEV" # {DEV | TEST | PROD}
```

### s3

An optional section that is used to configure the S3 AWS credentials. This is only necessary if you are using an S3 URL to load a map or the metadata YAML file.

```yaml
s3:
  AWS_ACCESS_KEY_ID: ""
  AWS_SECRET_ACCESS_KEY: ""
  AWS_REGION: ""
  AWS_ENDPOINT_URL: ""
```


