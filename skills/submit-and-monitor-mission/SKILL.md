---
name: submit-and-monitor-mission
version: 1.0.0
license: Apache-2.0
description: Submit a Mission Control mission and verify it completes end-to-end; not for stack startup, map, or fleet changes.
metadata:
  author: NVIDIA Isaac Team <info@nvidia.com>
  permissions:
    file_read:
      - mission.json
    file_write:
      - mission.json
    execute:
      - skills/submit-and-monitor-mission/scripts/preflight.sh
      - skills/submit-and-monitor-mission/scripts/submit_mission.sh
---


# Submit and Monitor Mission

## Purpose

Submit a Mission Control mission and prove it actually completed, when the
user says "submit this mission and tell me if it completes", "send carter01
on this route and verify it", or "did that mission actually finish?" Process
startup and robot `IDLE` are not sufficient proof — this skill polls Mission
Database, Mission Dispatch logs, robot state, and robot pose until they all
agree on a terminal outcome.

Do not use this for stack startup, image selection, map changes, or fleet edits. Use the matching bringup or configuration skill first, then use this skill to prove the submitted mission completed.

## Prerequisites

```bash
bash skills/submit-and-monitor-mission/scripts/preflight.sh
```

Run it to check all of these at once. It is read-only and starts nothing; it
exits non-zero and names what is missing.

- Mission Control stack is running and reachable, with `MC_PORT` and `DATABASE_CONTROLLER_PORT` exported in the caller's environment.
- Mission Database and Mission Dispatch containers are healthy enough to answer API requests and logs.
- A route mission payload, or enough of a route description to write one.
  The payload need not exist before this skill runs: preflight reports its
  absence as a warning, and step 1 below writes it.
- The target robot name is known and present in Mission Database.
- Docker access is available for Dispatch and robot runtime logs when log correlation is needed.

## Instructions

1. Ensure a mission payload exists. Use the user's file unchanged when they
   supplied one. Otherwise write `mission.json` in the format under *Mission
   Payload Format*, choosing coordinates as described in *Choosing Route
   Coordinates* rather than inventing them, and show the user the payload and
   the `/visualize_route` preview before submitting.
2. Submit the mission with a stable mission ID and explicit robot name.
3. Poll Mission Database and robot state until the mission reaches a terminal state.
4. Treat `FAILED`, `CANCELED`, or `CANCELLED` as terminal failures.
5. Sample robot pose before, during, and after the mission; require meaningful pose progress unless the mission is intentionally stationary.
6. Correlate Mission Dispatch logs with robot runtime or Nav2 logs.
7. Report success only after Mission Database, Dispatch, robot state, and robot motion agree.

## Available Scripts

| Script | Purpose | Arguments |
| --- | --- | --- |
| `skills/submit-and-monitor-mission/scripts/preflight.sh` | Read-only host check. Run before `submit_mission.sh`; writes nothing, submits nothing, exits non-zero and names what is missing. | Optional mission JSON path to check; defaults to `mission.json`. `-h` |
| `skills/submit-and-monitor-mission/scripts/submit_mission.sh` | Submit a mission JSON payload with a stable mission ID and robot name. Requires `MC_PORT` to be exported in the environment. | Optional mission JSON path; defaults to `mission.json`. |

## Success Definition

A mission succeeds only when all are true:

- Mission Database `/mission/<mission_id>` reports `status.state == COMPLETED`.
- Mission Database has no `failure_reason`.
- Robot returns to `IDLE`, remains online, and has no errors.
- Mission Dispatch logs show `Mission state: RUNNING -> COMPLETED`.
- Robot/runtime logs show the order or Nav2 goals completed.
- Robot pose changed along the expected route or the visual stream confirms motion.

If the robot goes `ON_TASK -> IDLE` but Mission Database says `FAILED`, the mission failed.

## Submission Pattern

Prefer the standalone script so mission IDs are explicit. Export `MC_PORT`
(and `DATABASE_CONTROLLER_PORT` if you plan to poll) in the caller's shell
first — the script does not source any environment file itself:

```bash
skills/submit-and-monitor-mission/scripts/submit_mission.sh mission.json
```

The script implements this pattern:

```bash
MISSION_ID="codex-mission-$(date +%s)"
ROBOT_NAME="${ROBOT_NAME:-carter01}"

curl -fsS -X POST \
  -H "Content-Type: application/json" \
  "http://127.0.0.1:${MC_PORT}/api/v1/mission/submit_mission?mission_id=${MISSION_ID}&mandatory_robot_name=${ROBOT_NAME}" \
  --data @mission.json
```

URL-encode query values if mission IDs or robot names contain spaces or special characters. For simple route replay, submit route-only missions. Do not include `start_location`, `end_location`, or `iterations`. Those fields are for more complex workflows such as starting at a desk, driving multiple laps, then returning to a parking area.

## Mission Payload Format

Read the schema from the running stack rather than assuming it. Mission
Control serves its own OpenAPI document, so the payload contract is always
current and never has to be mirrored here:

```bash
curl -fsS "http://127.0.0.1:${MC_PORT}/api/v1/openapi.json" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin)["components"]["schemas"]; \
print(json.dumps({k: d[k] for k in ("MissionData", "Point2D", "Waypoint2D") if k in d}, indent=2))'
```

That tells you which fields are required, every default, and the type of each
one. It also shows that `mission_id` and `mandatory_robot_name` are **query**
parameters, not body fields — a robot name placed in the payload is not a
validation error, it is silently ignored, and the mission submits with no
robot bound.

At the time of writing the body reduces to a list of route points, and a
route-only mission is what "replay this route" means:

```json
{
  "route": [
    {"x": 1.5, "y": 2.0},
    {"x": 5.0, "y": 3.25},
    {"x": 1.5, "y": 2.0}
  ]
}
```

If the fetched schema disagrees with that example, the schema is right.

## Choosing Route Coordinates

The schema gives types, not meaning. Two things it cannot tell you:

**Units and frame.** Route points are metres in the map frame, not pixels and
not the simulator's scene frame. Mission Control converts them with
`pixel = (world - origin) / resolution`, where the origin and resolution come
from the active map. A coordinate copied from an Isaac Sim scene or another
map is silently a different place.

**Navigability.** A point can be well-formed, in range, and still be inside a
wall or outside the map, which fails at execution with `Non-navigable surface
in mission plan` after the mission has already been accepted. `{"x": 0, "y":
0}` is not a safe default either: both coordinates default to 0, so an empty
point object submits a mission to the map origin, wherever that happens to be.

Do not invent coordinates. Read the active map's frame, then confirm the route
renders on navigable space before submitting:

```bash
# origin (x_offset, y_offset), resolution and rotation. No dimensions.
curl -fsS "http://127.0.0.1:${MC_PORT}/api/v1/map/metadata"

# the map image itself; pixel size x resolution gives the extent in metres
curl -fsS "http://127.0.0.1:${MC_PORT}/api/v1/map" -o active-map.png

curl -fsS -X POST -H "Content-Type: application/json" \
  "http://127.0.0.1:${MC_PORT}/api/v1/visualize_route" \
  --data @mission.json -o route-preview.png
```

`/visualize_route` takes the same body as submit, submits nothing, returns the
route drawn on the map, and rejects an invalid payload with the same 400 the
submit endpoint would, so it doubles as a dry run. Show the user the preview
when authoring a route on their behalf.

## Examples

Use the submission, polling, and log-correlation commands below as the standard route-mission validation flow.

## Polling Pattern

Poll Mission Database by mission ID and robot name (`DATABASE_CONTROLLER_PORT`
must already be exported in the caller's environment):

```bash
curl -fsS "http://127.0.0.1:${DATABASE_CONTROLLER_PORT}/mission/${MISSION_ID}"
curl -fsS "http://127.0.0.1:${DATABASE_CONTROLLER_PORT}/robot/${ROBOT_NAME}"
```

Automated wait helpers should repeatedly query:

- `http://127.0.0.1:${DATABASE_CONTROLLER_PORT}/mission/<mission_id>`
- `http://127.0.0.1:${DATABASE_CONTROLLER_PORT}/robot/<robot_name>`

Treat `FAILED`, `CANCELED`, or `CANCELLED` as terminal failure. Keep printing compact mission and robot summaries while waiting, and require `COMPLETED` before reporting success.

## Pose Progress Validation

For mobile robot route missions, record pose before submission, while Mission Database is `RUNNING`, and after terminal state. A valid moving-route mission should show a meaningful position or heading delta while the robot is `ON_TASK`. Report the sampled poses and the final pose in the result.

If a visual viewer is part of the requested demonstration, pose progress is still required unless the user explicitly accepts visual-only validation. Robot `IDLE` after a mission is not enough; a failed or stalled mission can also return the robot to `IDLE`.

## Stalled-Mission Decision Tree

Use this when Mission Database remains `RUNNING`, the robot is online, and the user expects motion:

- Mission `RUNNING`, robot `ON_TASK`, route node still `PENDING`: inspect Dispatch logs for order send/ack and robot client logs for order acceptance.
- Mission `RUNNING`, robot `ON_TASK`, `/cmd_vel` absent: inspect action server/lifecycle state, route validity, and whether the order reached the robot runtime.
- Mission `RUNNING`, robot `ON_TASK`, `/cmd_vel` active, but pose or odom frozen: inspect the simulator or physical base. In Isaac-backed demos, first check that Isaac Sim's timeline is playing and physics/odom are advancing.
- Mission `RUNNING`, robot `ON_TASK`, odom moves but Mission Database pose does not: inspect the robot status bridge and Mission Database robot updates.
- Robot returns `IDLE` while Mission Database is not `COMPLETED`: treat the database terminal state or lack of terminal state as authoritative and continue log correlation.

Do not submit overlapping retry missions until the active mission is terminal or explicitly canceled.

## Log Correlation

After terminal state, check the compose-managed Dispatch logs and the robot runtime logs:

```bash
docker compose -f docker-compose/bringup_services.yaml logs --tail 160 mission-dispatch
docker logs --tail 200 nova-carter-sil
```

(`docker compose` picks up the working-directory environment file automatically;
no `--env-file` flag is needed here.)

Expected Dispatch signatures:

- `Mission state: PENDING -> RUNNING`
- `Node 0: RUNNING -> COMPLETED`
- `Mission state: RUNNING -> COMPLETED`
- `Robot state: ON_TASK -> IDLE`

Expected robot/Nav2 signatures:

- `Order with order_id ... received`
- `Sending goal for ...`
- `Goal succeeded`
- `Order ... is completed`

## Limitations

- This skill validates submitted Mission Control missions; it does not start the stack, change maps, change fleets, or build runtime images.
- Robot `IDLE` state alone is not proof of mission success. Always check Mission Database terminal state.
- Runtime log names can vary by deployment; use the owning compose file or runbook when `nova-carter-sil` is not the active robot container.
- Pose or visual validation may be unavailable in headless or log-only environments; report that gap explicitly.

## Troubleshooting

- Error: Mission endpoint returns 400 before submission. Cause: checking a mission ID that does not exist yet. Solution: submit the mission first or choose a new stable mission ID.
- Error: `Failure reason: Goal rejected`. Cause: TF, Nav2 lifecycle, action server, or invalid route state. Solution: confirm `map -> odom -> base_link`, `/chassis/odom`, `/tf`, and `/tf_static`, then check Nav2 logs.
- Error: `Non-navigable surface in mission plan`. Cause: route coordinates are outside routable graph space. Solution: query nearest graph nodes for the active map and update the route.
- Error: `Fatal Errors present, failing mission`. Cause: robot status or Nav2 runtime reported a fatal condition. Solution: inspect robot status errors, Nav2 logs, and runtime container logs before retrying.
- Error: robot pose does not change while mission is `RUNNING`. Cause: route handoff, action server, command, simulator, odom, or robot-status update stalled. Solution: use the stalled-mission decision tree; if `/cmd_vel` is active but odom is frozen in an Isaac-backed demo, check that Isaac Sim is playing.
- Error: robot returns to `IDLE` while Mission Database says `FAILED`. Cause: robot state reset after failure. Solution: treat Mission Database failure as authoritative and inspect Dispatch plus runtime logs.

## Reporting

When reporting a completed run, include:

- Mission ID.
- Final Mission Database state and timestamp.
- Dispatch completion/failure signature.
- Robot initial, moving, and final pose samples, or an explicit note that pose validation was unavailable.
- Viewer URL if visual validation was part of the target.
