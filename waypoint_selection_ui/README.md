# Waypoint Selection Tool

A web-based tool for selecting and generating waypoints on map images.

## Overview

The Waypoint Selection Tool provides an intuitive interface for loading map images, selecting points, and generating waypoint paths. It's designed for robotics applications, navigation planning, and similar use cases that require path selection on 2D maps.

![Waypoint Selection Tool Interface](assets/waypoint_selection_tool_example.png)

## Features

- Upload and manage map images (PNG, JPG)
- Upload or manually enter map configuration
- Interactive point selection with visual feedback
- Real-time coordinate display
- Zoom and pan controls for precise point placement
- Waypoint generation based on selected points
- Route visualization showing the path a robot would follow
- Simple JSON output format for integration with other systems

## Installation

### Using Docker (Recommended)

1. **Clone the repository**:

   ```bash
   git clone ssh://git@gitlab-master.nvidia.com:12051/isaac_amr_platform/mission-control.git
   cd mission-control
   ```

2. **Run with Docker Compose** (simplest method):

   ```bash
   docker compose -f waypoint_selection_ui/bringup_wp_selection_ui.yaml up --build
   ```

   This will build the image and start the container with the correct volume mappings.

3. **Alternatively, build and run manually**:

   ```bash
   # Build the Docker image
   docker build -t waypoint-selection-tool -f waypoint_selection_ui/Dockerfile .

   # Run the container
   docker run -p 8051:8051 -v $(pwd)/waypoint_selection_ui/uploads:/app/uploads waypoint-selection-tool
   ```

## Usage

1. **Access the web interface** at http://localhost:8051

2. **Upload a map image**:
   - Click on the "Upload Files" tab
   - Select a PNG or JPG file and click "Upload Map"

3. **Configure map parameters**:
   - Either upload a YAML configuration file
   - Or enter parameters manually (resolution, origin coordinates)

4. **Select waypoints**:
   - Click on the map to place points
   - The first point will be marked green (start)
   - The last point will be marked blue (end)
   - Intermediate points will be marked red

5. **Generate waypoints**:
   - Click "Generate Waypoints" to process your selection
   - The resulting waypoints will appear in JSON format

6. **Visualize route path**:
   - Click "Visualize Route" to see the actual path a robot would follow
   - This feature requires Mission Control service to be running with proper configuration
   
   To set up Mission Control for route visualization:

   a. **Configure Mission Control**:
      - After uploading and configuring your map in the Waypoint Selection Tool:
        1. Right-click on the map image in the web UI to get its URL
        2. Update the following fields in `app/config/defaults.yaml`:
           ```yaml
           map:
             map_uri: "<map_image_url>"  # URL from right-clicking the map
             metadata:
               resolution: <value>        # Resolution from your map config
               x_offset: <value>         # X origin from your map config
               y_offset: <value>         # Y origin from your map config
           ```
      - The map configuration values should match those used in the Waypoint Selection Tool
      - For custom maps, adjust the values according to your map's configuration file
      - Every time you upload a new map in the UI, update these four fields in `defaults.yaml`
      - After updating the map configuration, you should restart Mission Control for the changes to take effect.
      - If you need to adjust the robot's safety buffer (minimum distance from obstacles), update the `safety_distance` parameter in `app/config/defaults.yaml`:
        ```yaml
        map:
          metadata:
            safety_distance: 0.45  # Adjust this value (in meters) based on your robot's size and requirements
        ```
        This parameter determines how far the robot will stay from obstacles during navigation. The default value of 0.45 meters provides a safe buffer for most robots, but you may need to adjust it based on your specific robot's dimensions and operational requirements.

   b. **Launch Mission Control**:
      There are two ways to launch Mission Control depending on your setup:

      1. **Using the Default Robot Simulator** (for simulation/testing):
         ```bash
         docker compose -f docker-compose/bringup_services.yaml --profile robot-simulator up
         ```

      2. **Using Mission Client** (for isaac ros2 stack):
         ```bash
         docker compose -f docker-compose/bringup_services.yaml up
         ```
         Note: Choose this option only if you have a mission client running locally with Isaac ROS2 stack.

      Note: If using a custom map (not the example map), you must adjust the robot's initial position in the docker-compose file to ensure it starts in an obstacle-free location:
      ```yaml
      robot-simulator:
        command: ["--robots", "carter01,<x>,<y>"]  # Update x,y coordinates to a clear area on your map
      ```
      To find suitable coordinates:
      1. Use the Waypoint Selection Tool to identify an open area on your map
      2. Note the coordinates of that location
      3. Update the docker-compose file with those coordinates
      4. Restart Mission Control to apply the new starting position

   c. **View the Route**:
      - Once Mission Control is running, return to the Waypoint Selection Tool
      - Click "Visualize Route" to see:
        - The route path as a green line
        - Waypoints as numbered red circles
        - Robot's path between waypoints
      - If Mission Control is not available or misconfigured, an error message will be displayed

   Troubleshooting:
   - If the route visualization fails, verify that:
     1. Mission Control is running
     2. Map configuration matches between Mission Control and Waypoint Selection Tool
     3. Robot coordinates are within the map boundaries
     4. The map URL in `defaults.yaml` is accessible
     5. All map configuration fields are correctly updated


7. **Clear or modify points**:
   - Use the "Clear Points" button to start over

## Map Configuration Format

The YAML configuration file should include:

```yaml
image: "map_name.png"
resolution: 0.05  # meters per pixel
origin: [0.0, 0.0, 0.0]  # [x, y, theta] in meters and radians
```

## Coordinate System

The tool uses a standard robotics coordinate system:
- Origin (0,0) is at the bottom left of the map
- X increases to the right
- Y increases upward
- Theta (rotation) is measured counterclockwise from the X-axis

## Integration with Mission Control

For route visualization functionality, the tool connects to the Mission Control service, which performs the route planning calculations. By default, it attempts to connect to `http://localhost:8050/api/v1`.

To specify a different Mission Control URL, set the `MISSION_CONTROL_API_URL` environment variable when running the container.