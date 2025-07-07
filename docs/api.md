## API Reference:

### **POST** /mission/submit_mission

Create a new mission and execute it.

**Query Parameters:**
| Parameter | Required? | Type | Description |
| ----------- | ----------- | ---- | ------------|
| mission_id | No | string | Text identifier to refer to this mission |
| mandatory_robot_name | No | string | Name of robot to forcibly assign this mission to |

**Request Body:**

JSON Structure
| Element | Required? | Type | Description |
| ----------- | ----------- | ---- | ------------|
| route | Yes | list[Point] | List of points for the robot to travel to. |
| start_location | No | Point | If you would like to prepend the route with a specific starting location. Robot will travel from the current location to this point before starting the route. |
| end_location | No | Point | If you would like to append to the route with a final ending location. Robot will travel to this location after completing the route. |
| iterations | No | integer | Default 1. Number of times to perform the route. |
| timeout | No | integer | Default 3600. Timeout for the mission in seconds. |
| solver | No | string | Default "NVIDIA_CUOPT". The route planning solver to use. "NVIDIA_CUOPT" for CUDA accelerated route planning (requires cuOpt container to be running), "CPU_DIJKSTRA" for CPU based route planning. |

**Response:**

On top of all the fields in the request body, the response contains the following fields:

JSON Structure
| Element | Type | Description |
| ----------- | ---- | ------------|
| sub_mission_uuids | list[string] | List of UUIDs for each sub-mission in the mission |
| robots | list[string] | List of robot names that were assigned to this mission |
| docks | list[string] | List of dock IDs that were assigned to this mission |


Example:
If your robot is in a parking zone and you need it to travel to a specific track entry location, do five laps on the track, and return to a charging location, then you would localize at the parking zone, set `start_location` to the track entry, describe your route on the track with iterations set to 5, then set `end_location` as the charger.

### **POST** /mission/charging

Send a robot to a dock for charging.

**Query Parameters:**
| Parameter | Required? | Type | Description |
| ----------- | ----------- | ---- | ------------|
| robot_name | Yes | string | Name of robot to send to the dock for charging. |
| dock_id | No | string | ID of the dock to send the robot to. If not provided, the route planner selects the nearest dock. |

**Request Body:** None

**Response:** Same as `/mission/submit_mission`

### **POST** /mission/undock

Undocks a robot from a dock.

**Query Parameters:**
| Parameter | Required? | Type | Description |
| ----------- | ----------- | ---- | ------------|
| robot_name | Yes | string | Name of the robot to send to undock. |

**Request Body:** None

**Response:** Same as `/mission/submit_mission`

### **POST** /visualize_route

Visualize a route without submitting an actual mission. Returns an image showing the route drawn on the map.

**Query Parameters:** None

**Request Body Schema:** Same as `/mission/submit_mission`

**Response:** PNG image with the route visualized on the map, showing:
- Waypoints (red circles with numbered labels)
- Route path (green line)
- Solver information 

This endpoint is useful for:
- Planning and verifying routes before assigning them to robots.

### **GET** /mission/get_available_objects

Get a list of objects that can be picked up by the robot.

**Query Parameters:**
| Parameter | Required? | Type | Description |
| ----------- | ----------- | ---- | ------------|
| robot_name | Yes | string | Name of robot arm to get available objects for. |

**Request Body:** None

**Response:**

JSON Structure
| Element | Type | Description |
| ----------- | ---- | ------------|
| object_id | integer | ID of the object |
| class_id | string | The classification result of the object of interest. |

### **POST** /mission/pick_and_place

**Query Parameters:**
| Parameter | Required? | Type | Description |
| ----------- | ----------- | ---- | ------------|
| robot_name | Yes | string | Text identifier to refer to robot of interest. |

**Request Body:**

JSON Structure
| Element | Required? | Type | Description |
| ----------- | ----------- | ---- | ------------|
| object_id | Yes | integer | ID of the object |
| class_id | Yes | string | The classification result of the object of interest |
| pos_x | Yes | float | X coordinate of the object |
| pos_y | Yes | float | Y coordinate of the object |
| pos_z | Yes | float | Z coordinate of the object |
| quat_x | Yes | float | X component of the object's orientation |
| quat_y | Yes | float | Y component of the object's orientation |
| quat_z | Yes | float | Z component of the object's orientation |
| quat_w | Yes | float | W component of the object's orientation |

**Response:** Same as `/mission/submit_mission`

### **GET /api/v1/health**

**Query Parameters: None**  
**Request Body: None**
