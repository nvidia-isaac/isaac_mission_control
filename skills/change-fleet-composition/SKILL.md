---
name: change-fleet-composition
license: Apache-2.0
description: Use when adding, removing, renaming, or relabeling Mission Control robots.
metadata:
  author: NVIDIA Isaac Team <info@nvidia.com>
  version: 1.0.0
  permissions:
    file_read:
      - app/config/defaults.yaml
      - docker-compose/bringup_services.yaml
    file_write:
      - app/config/defaults.yaml
      - docker-compose/bringup_services.yaml
    execute:
      - skills/change-fleet-composition/scripts/preflight.sh
      - skills/change-fleet-composition/scripts/set_fleet.py
---

# Change fleet composition

## Purpose

Change which robots Mission Control boots with: add or remove AMRs, rename robots, set labels, set heartbeat timeout, and control which robots are included in the simulator command.

Use this when the user wants to change which or how many robots the stack boots with, for example "run with two AMRs", "add a third carter", "rename carter01 to amr_lobby", or "drop the sim robots, I'm bringing real ones".

**Do not edit `app/config/defaults.yaml` or `docker-compose/bringup_services.yaml` by hand.** Invoke `skills/change-fleet-composition/scripts/set_fleet.py` instead. The script handles both files together, keeps them in sync, validates input, and preserves surrounding formatting.

## Prerequisites

```bash
bash skills/change-fleet-composition/scripts/preflight.sh
```

Run it to check all of these at once. It is read-only and
writes nothing; it exits non-zero and names what is missing.

### Required on the host

- `python3`. `set_fleet.py` uses only the standard library, so nothing needs
  installing, but an interpreter must be on `PATH`.
- Write access to the workspace. The script creates `$MC_WORKSPACE` and writes
  both files into it.

### Required from the user

- **A complete desired fleet definition as JSON.** The script replaces the whole
  `robots:` block, so a partial definition deletes the robots it omits. Ask for
  the full fleet, not the delta. `--show` returns the current fleet in the same
  shape the script accepts, including `sim` and any spawn pose, so it is a valid
  starting point.
- **Numeric `x` and `y` for any robot newly added to the simulator.** Existing
  simulated robots keep their pose; real robots need none.
- **Confirmation after a `--dry-run` review** before applying, for the same
  reason.

### Not required

- **A Mission Control checkout.** The skill ships what it reads under
  `resources/`: `app/config/defaults.yaml` and
  `docker-compose/bringup_services.yaml`. A fresh machine with no clone can run
  this skill.
- **A running Mission Control, Docker, or network access.** The script edits two
  files and makes no subprocess calls.
- **`bring-up-cloud-stack`.** Not needed to run this skill, but the edit does
  nothing until that skill restarts the stack. Install it from the
  mission-control repository if you want to apply the fleet.

### Optional

- `MC_WORKSPACE` (default `./skills-workspace`) selects where the edited
  `defaults.yaml` and `bringup_services.yaml` are written. It is resolved
  against the caller's cwd, so running from two directories edits two different
  workspaces. Export it to pin one.

## Instructions

1. Read the current fleet first with `--show` so additive or rename requests preserve existing robots correctly.
2. Construct the whole desired fleet as JSON; the input is declarative and replaces the current `robots:` block.
3. Run `--dry-run` and show the user the proposed `app/config/defaults.yaml` robots block and `docker-compose/bringup_services.yaml` simulator command.
4. Apply the change only after explicit user confirmation. Applying without `--dry-run` overwrites the existing fleet block and robot-simulator command.
5. If the change affects a running stack, ask before restarting services. `bring-up-cloud-stack --recreate` interrupts active services and must not run while robot missions are active.

Prefer `run_script()` with `skills/change-fleet-composition/scripts/set_fleet.py` when the environment provides a script runner:

```python
run_script("skills/change-fleet-composition/scripts/set_fleet.py", args=["--show"])
run_script("skills/change-fleet-composition/scripts/set_fleet.py", args=["--dry-run", "--fleet-json", "[...]"])
run_script("skills/change-fleet-composition/scripts/set_fleet.py", args=["--fleet-json", "[...]"])
run_script("skills/change-fleet-composition/scripts/set_fleet.py", args=["--fleet-file", "path/to/fleet.json"])
```

## Available Scripts

| Script | Purpose | Arguments |
|---|---|---|
| `skills/change-fleet-composition/scripts/preflight.sh` | Read-only host check. Run before `set_fleet.py`; writes nothing, exits non-zero and names what is missing. | `-h` |
| `skills/change-fleet-composition/scripts/set_fleet.py` | Replace the Mission Control `robots:` block and synchronize the compose `robot-simulator` command. | `--show`, `--fleet-json`, `--fleet-file`, `--dry-run`, `--defaults-yaml`, `--bringup-yaml` |

## How the script's input maps to user intent

The script takes a single JSON list, the whole desired fleet, via `--fleet-json` or `--fleet-file`. It is declarative: pass the fleet you want, and the script makes the file look like that. For incremental edits like "add a robot" or "rename one", first read the current fleet, modify it, then pass the modified list.

JSON schema per robot:

```json
{
  "name": "carter01",
  "labels": ["test", "carter", "ros"],
  "heartbeat_timeout": 30,
  "sim": true,
  "x": 0.0,
  "y": 0.0
}
```

Required fields: `name`, plus `x` and `y` when `sim` is true. Robot names must be unique and contain only letters, digits, underscores, and dashes. Optional defaults are `labels: ["test", "carter", "ros"]`, `heartbeat_timeout: 30`, and `sim: true`.

## Examples

Read the current fleet:

```bash
python3 skills/change-fleet-composition/scripts/set_fleet.py --show
```

Dry-run a proposed two-robot simulated fleet before asking the user to confirm:

```bash
python3 skills/change-fleet-composition/scripts/set_fleet.py --dry-run --fleet-json '[
  {"name":"carter01","x":0.0,"y":0.0},
  {"name":"carter02","x":2.0,"y":0.0}
]'
```

Apply only after the user confirms the dry-run output:

```bash
python3 skills/change-fleet-composition/scripts/set_fleet.py --fleet-json '[...]'
```

For long fleets, write the JSON to a file and pass `--fleet-file path/to/fleet.json`.

## Choosing spawn poses

**Choosing where a robot spawns is out of scope for this skill. Ask the user for
`x` and `y`; do not invent them.**

A pose is only meaningful against a specific map. `(0, 0)` is open floor in
`carter_warehouse_navigation` and a boundary wall in `nvidia_galileo`, because
their origins differ. Nothing here reads the map, so a coordinate this skill
accepts may put the robot in a wall or outside the building entirely, and no
step reports it — not this script, not `bring-up-cloud-stack`, not Mission
Control. `set_fleet.py` enforces this by refusing any simulated robot without
numeric `x` and `y`.

This only comes up for a robot **newly** added to the simulator. Existing
simulated robots keep the pose they already have, and real robots need none, so
most requests need no coordinates at all. When one does:

- Ask. Name the map currently configured in `app/config/defaults.yaml` so they
  know which frame the numbers are in.
- If they do not know, point them at the map: the Nav2 yaml beside the image
  gives `resolution` and `origin`, and `--show` reports the poses of any robots
  already simulated.
- Do not reuse an existing robot's pose. Robots spawning on the same
  coordinates collide.

## Sim vs real robots

`sim: false` registers the robot with Mission Control/Dispatch but does not add it to the simulator command line. Use it for real hardware. The script omits real robots from the `--robots` string.

Mission Control itself has no notion of simulated versus real: `defaults.yaml`
stores only name, labels and heartbeat timeout. `sim` decides one thing, whether
the robot joins the simulator's `--robots` argument, and it is never written to
`defaults.yaml`.

When a robot does not state `sim`, the script infers it from the current
simulator command:

- **Already in `--robots`** — stays simulated, keeping the pose it already has.
  Adding a robot never silently un-simulates the existing fleet.
- **Not in `--robots`** — real hardware, unless the request supplies `x` and
  `y`, which only make sense for a simulated robot.

That default matches what Mission Control actually runs: the `robot-simulator`
service is behind a profile, so no documented launch starts it. Removing a robot
from the simulator therefore takes an explicit `sim: false`, and the script
prints a note naming what it dropped.

If `bringup_services.yaml` has no `robot-simulator` service, for example when the user is on `bringup_demo_services.yaml`, the script skips the sim-side edit and prints a note. Mention that to the user.

## After applying

If the running stack must reread the fleet, first preview the recreate command and ask the user to confirm that no missions are active:

```bash
skills/bring-up-cloud-stack/scripts/up.sh --with-sim --recreate --dry-run
```

After explicit confirmation, surface this once:

```bash
skills/bring-up-cloud-stack/scripts/up.sh --with-sim --recreate
```

`--with-sim` enables the `robot-simulator` profile; the service only runs under it. `--recreate` is required because `defaults.yaml` is bind-mounted and `up` alone will not restart `mission-control` to re-read the new fleet.

If the user removed a robot that already exists in the mission-database, that registration persists across restarts. Cleanup is a separate operation; mention it but do not attempt it as part of this skill unless asked.

## Troubleshooting

- **Invalid JSON:** show the parse error, keep the current files untouched, and ask for corrected fleet JSON.
- **Duplicate robot names:** choose unique names before applying; the script rejects duplicates.
- **Missing spawn pose:** every simulated robot needs numeric `x` and `y`.
- **No `robot-simulator` service:** the script still updates `defaults.yaml` and reports that simulator sync was skipped.
- **Robot removed but still visible in mission-database:** registration cleanup is separate and should be done only on request.
- **Stack does not pick up changes:** preview and then confirm `bring-up-cloud-stack --recreate`; do not recreate services during active missions.

## Limitations

- Per-robot config beyond `name`, `labels`, and `heartbeat_timeout`, such as dock assignments or custom behavior trees.
- Editing tutorial bringup files under `docs/tutorial/docker-compose/` or `docs/objectives_tutorial/docker-compose/`.
- Map-side validation of spawn poses.
- Mission-database registration cleanup for removed robots.
