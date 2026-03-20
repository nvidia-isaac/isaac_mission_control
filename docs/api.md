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
| route | Yes | list[Point2D] | List of points for the robot to travel to. |
| start_location | No | Point2D | If you would like to prepend the route with a specific starting location. Robot will travel from the current location to this point before starting the route. |
| end_location | No | Waypoint2D | If you would like to append to the route with a final ending location. Robot will travel to this location after completing the route. Set `exact` to True to route to the exact x, y, theta. |
| iterations | No | integer | Default 1. Number of times to perform the route. |
| timeout | No | integer | Default 3600. Timeout for the mission in seconds. |
| solver | No | string | Default "NVIDIA_CUOPT". The route planning solver to use. "NVIDIA_CUOPT" for CUDA accelerated route planning (requires cuOpt container to be running), "CPU_DIJKSTRA" for CPU based route planning. |

Point2D
| Element | Required? | Type | Description |
| ----------- | ----------- | ---- | ------------|
| x | Yes | float | x coordinate on a 2D plane. |
| y | Yes | float | y coordinate on a 2D plane. |

Waypoint2D
| Element | Required? | Type | Description |
| ----------- | ----------- | ---- | ------------|
| x | Yes | float | x coordinate on a 2D plane. |
| y | Yes | float | y coordinate on a 2D plane. |
| theta | No | float | Orientation of the robot in radians. |
| exact | No | bool | Default False. Set `exact` to True to route to the exact x, y, theta. |

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

### **Error & Exception Reference**

Mission Control uses a small, well–defined set of Python exception classes together with
FastAPI's `HTTPException` to communicate problems to API clients.  This document
collects all of the currently-defined error types, explains when they are raised,
and lists the HTTP status codes that the public REST endpoints can return.

---

#### 1. Custom exception hierarchy

| Class | Located in | Purpose | Typical HTTP mapping |
|-------|------------|---------|----------------------|
| `ICSError` *(base)* | `cloud_common/objects/common.py` | Generic base‐class for all *Isaac Cloud Services* errors. | *n/a – abstract* |
| `ICSUsageError` | same as above | Raised when **user input** is invalid, missing or out-of-range. | 400 *Bad Request* |
| `ICSServerError` | same as above | Raised when an **internal service** fails or a required dependency is unavailable. | 500 *Internal Server Error* or 503 *Service Unavailable* |
| `MissionCtrlError` | `app/common/utils.py` | Configuration & start-up problems detected by Mission Control itself (e.g. bad YAML, missing map). | 500 *Internal Server Error* (only surfaced at startup) |
| `CuOptOptimizationException` | `app/api/clients/cuopt_client.py` | cuOpt solver could not compute a solution within time / constraints. | 400 *Bad Request* |

> **FYI**  Only the five classes above are defined inside the repository.  All
> other raised exceptions are standard Python errors (`ValueError`,
> `KeyError`, …) or `fastapi.HTTPException` instances created in the REST
> layer.

##### 1.1  Error code fields

`ICSError` and its subclasses expose a string attribute `error_code` that can
be used by callers to distinguish *usage* vs *server* errors programmatically:

```python
from cloud_common.objects.common import ICSUsageError, ICSServerError
try:
    ...
except ICSUsageError as e:
    assert e.error_code == "USAGE"
except ICSServerError as e:
    assert e.error_code == "SERVER"
```

---

#### 2. HTTP errors returned by the REST API

Mission Control converts internal exceptions to `fastapi.HTTPException` as close
as possible to the request boundary.  The table below summarises the status
codes that each documented endpoint may return.

| Endpoint | 400 – Bad Request | 404 – Not Found | 409 - Conflict | 500 – Internal | 503 – Unavailable |
|----------|------------------|-----------------|----------------|-----------------|-------------------|
| **POST** `/mission/submit_mission` | Invalid route data, unknown robot, cuOpt failure | — | mission_id conflict |— | MC not initialised |
| **POST** `/mission/charging` | Invalid parameters, robot offline | — | mission_id conflict |— | MC not initialised |
| **POST** `/mission/undock` | Invalid parameters | — | mission_id conflict | — | MC not initialised |
| **POST** `/mission/pick_and_place` | Validation errors | — | mission_id conflict | — | MC not initialised |
| **POST** `/visualize_route` | Invalid mission data | — | - | — | MC not initialised |
| **GET** `/mission/get_available_objects` | Invalid robot name | — | - | — | MC not initialised |
| **GET/POST** `/health` | — | — | - | — | MC not initialised |
| **SAP** `/sap/*` | Validation / client errors | Missing task / order / robot | - | Downstream SAP / mapping errors | SAP or MC unavailable |

Note: **POST** `/map/update_robot/{robot_name}/{map_id}` may return `409 Conflict` if the target robot is not IDLE or its status cannot be validated.

Legend:  "MC" = Mission Control service;  "—" = code not used by this endpoint.

> NOTE: The list above was generated by scanning all FastAPI routes in
> `app/api/endpoints`.  If you introduce a new route, please update the table.

---

#### 3. Mapping rules inside the codebase

1. **At the business-logic layer** (`app/core/*`, `cloud_common/*`)

   • raise `ICSUsageError` for anything that is the caller's fault (bad
   arguments, unsupported operation, …).
   
   • raise `ICSServerError` for dependency or infrastructure failures.
2. **At the API layer** (`app/api/endpoints/*`)

   • catch `(ValidationError, ValueError, KeyError, CuOptOptimizationException,
   ICSError)` and translate them to `HTTPException(status_code=400)`.

   • let unanticipated `ICSServerError` bubble up – FastAPI's exception handler
   converts it to HTTP 500 unless a route intercepts it earlier.

   • Use 503 when Mission Control is *intentionally unavailable* (startup or
   shutdown) via `mc_ready()` helper.

---

#### 4. Example

```text
Errors:
  • 400 BAD_REQUEST
      – Route has < 2 waypoints
      – Unknown robot "carter99"
      – cuOpt solver error (timeout / infeasible)
  • 503 SERVICE_UNAVAILABLE
      – Mission Control not ready (initialising dependencies)
```

---

#### 5. Adding new errors

When adding features, follow the hierarchy below:

1. Decide whether it is a **usage** error or a **server** error.
2. Derive a new class *only if* you need a machine-readable marker beyond the
   usage/server split.  Otherwise reuse `ICSUsageError` / `ICSServerError`.
3. Update this document and any endpoint-specific tables if the public API is
   affected.

```python
class MyNewError(ICSUsageError):
    """Raised when … """
    error_code = "MY_NEW_ERROR"
```

---