---
name: change-map
license: Apache-2.0
description: Change the map Mission Control loads on startup — switch among bundled maps, point at an uploaded file, a URI, or an S3 object, and update the associated metadata. Edits app/config/defaults.yaml via skills/change-map/scripts/set_map.py.
metadata:
  author: NVIDIA Isaac Team <info@nvidia.com>
  version: 1.0.0
---


# Change map

## Purpose

Change the map Mission Control loads on startup when the user says "switch to
the warehouse map", "use the Galileo map", "load my map from S3", or "point at
https://...". This skill edits the `map:` block of `app/config/defaults.yaml`
and nothing else.

It does not start, stop, or reload anything. Mission Control reads that file at
startup, so an edit takes effect only when the stack is next brought up — see
[After applying](#after-applying).

## Prerequisites

```bash
bash skills/change-map/scripts/preflight.sh
```

Run it to check all of these at once. It is read-only and
writes nothing; it exits non-zero and names what is missing.

### Required on the host

- `python3`. `set_map.py` uses only the standard library, so nothing needs
  installing, but an interpreter must be on `PATH`.
- Write access to the workspace. The script creates `$MC_WORKSPACE` and copies
  the bundled maps into it.

### Not required

- **A Mission Control checkout.** The skill ships everything it reads under
  `resources/`: `app/config/defaults.yaml` and the bundled maps with their Nav2
  yamls. A fresh machine with no clone can run this skill.
- **A running Mission Control, Docker, or network access.** The script edits a
  file and makes no subprocess calls.
- **`bring-up-cloud-stack`.** Not needed to run this skill, but the edit does
  nothing until that skill restarts the stack. Install it from the
  mission-control repository if you want to apply the map.

### Optional

- `MC_WORKSPACE` (default `./skills-workspace`) selects where the edited
  `defaults.yaml` and the seeded maps are written. It is resolved against the
  caller's cwd, so running from two directories edits two different workspaces.
  Export it to pin one.

Use this when the user wants to boot the stack against a different map — "switch to the GTC map", "switch to warehouse map", "load my warehouse map from S3", or "point at https://...".

**Do not edit the `map:` block in `app/config/defaults.yaml` by hand.** Invoke `skills/change-map/scripts/set_map.py` instead. The script renders a canonical `map:` block, splices it in place, and preserves trailing commented hints (e.g. the `# docks:` example block).

**Metadata is always a Nav2 yaml.** Every map this project ships with (and every map the user supplies) comes with a sibling Nav2 `*.yaml` written by `nav2_map_server`. `--metadata-yaml` points at that file; `--map` finds it for you. MC's config loader auto-converts the Nav2 schema at load time. There is no flag for supplying metadata by hand, deliberately — see below.

**Never invent `resolution` or `origin`.** They are not properties of the image. `resolution` is metres per pixel and `origin` is the world coordinate of the map's corner; both are produced by whatever captured the map, and nothing in a PNG recovers them. Guessing them, or copying them from another map's yaml, silently puts the robot's world frame in the wrong place — missions run against coordinates that do not match the building.

Deriving the *path* to a yaml is different from deriving its contents. A map is normally written alongside its yaml, so when the user names only an image, point `--metadata-yaml` at the sibling — `warehouse.png` → `warehouse.yaml` — and **say that you assumed it**. A wrong path fails loudly when Mission Control cannot fetch it; wrong values do not fail at all.

Only when there is genuinely no yaml — the user says so, or asks you to work the numbers out — **stop and ask for one.** Do not reuse another map's values, and do not write a yaml containing numbers you chose. Transcribing values the user gives you is fine; those came from their capture. Point them at the Occupancy Map Generator or `nav2_map_server` output if they do not know where the yaml is.

## Bundled maps

For a map this skill ships, pass `--map <name>` and nothing else. The script
resolves the name against the workspace then the shipped `resources/`, picks up
the sibling Nav2 yaml on its own, and writes both container paths:

```bash
python3 skills/change-map/scripts/set_map.py --map nvidia_galileo
```

A name that matches nothing, or matches more than one map, is an error listing
what is available — the path is never written on a guess. A `--metadata-yaml`
whose `image:` field names a different map is refused too: `map_id` comes from
that field and is the WPG cache key, so the pairing would serve the other map's
route graph against this image.

It also copies any shipped map the workspace does not have into
`$MC_WORKSPACE/app/config/maps/`, never overwriting. `defaults.yaml` names a map
by its container path, so the file has to be inside the directory mounted at
`/tmp/config`; writing only `defaults.yaml` would leave a `map:` block pointing
at nothing, which Mission Control reports as a 503.

Shipped maps:

| `--map` | Nav2 yaml | Notes |
|---|---|---|
| `carter_warehouse_navigation` | yes | The default. Matches the warehouse simulation. |
| `nvidia_galileo` | yes | A building map, `origin: [0, 0, 0]`. Useful for exercising a map switch; it does **not** correspond to the bundled warehouse sim, so missions run against it will not match the simulated environment. |

## Inputs to collect

Skip to `--map` above for a bundled map. For anything else:

1. **Source type** — exactly one of:
   - `file` — a path inside the mission-control container. `app/config/` is bind-mounted to `/tmp/config/`, so use `/tmp/config/maps/<file>.png` for bundled maps or `/tmp/config/uploaded_maps/<file>.png` for user-uploaded ones.
   - `uri` — an `http(s)://...` URL.
   - `s3` — an `s3://bucket/key` URL. Also requires `app/config/defaults.yaml` `s3:` credentials to be populated; flag that to the user if they're empty.
2. **Source value** — the path/URL.
3. **Metadata yaml** — container-side path or S3 URL of the Nav2 `*.yaml` that ships next to the PNG.
4. **Flags** — `--push-on-startup` (Mission Control sends the map-load action to robots on startup) and `--save-route-visualization`. Both default false; ask if you're not sure.

## Nav2 yaml → MC mapping

MC's `ROSMapMetadata` parser (`app/core/mission_control_config.py`, `apply_metadata_yaml()`) maps the Nav2 schema as follows:

| Nav2 field | MC field | Notes |
|---|---|---|
| `image:` | `map_id` | Used verbatim, **including any `.png` extension**. Strip `.png` from `image:` in the yaml if you care about the WPG cache key. |
| `resolution:` | `resolution` | Same. |
| `origin: [x, y, yaw]` | `x_offset`, `y_offset` | `origin[2]` (yaw) is **silently ignored** — MC hardcodes `rotation: 0.0`. Surface this if the map needs non-zero rotation. |
| `occupied_thresh:` | `occupancy_threshold` | Multiplied by 255 (e.g. `0.65` → `166`). |
| `mode:`, `negate:`, `free_thresh:` | — | Ignored. |
| (none) | `safety_distance` | Defaults to `0.45m`. Override by adding `safety_distance: <value>` to the Nav2 yaml — pydantic accepts the extra field. |

## How to invoke

Discover available bundled maps:
```bash
python3 skills/change-map/scripts/set_map.py --list-bundled
```

Preview a change:
```bash
# Bundled map, resolved by name (preferred):
python3 skills/change-map/scripts/set_map.py --dry-run --map nvidia_galileo

# The same thing spelled out, for a map that is not bundled:
python3 skills/change-map/scripts/set_map.py --dry-run \
  --source-type file --source /tmp/config/maps/carter_warehouse_navigation.png \
  --metadata-yaml /tmp/config/maps/carter_warehouse_navigation.yaml

# URI source:
python3 skills/change-map/scripts/set_map.py --dry-run \
  --source-type uri --source https://example.com/map.png \
  --metadata-yaml https://example.com/map.yaml

# S3 source, push to robots on startup:
python3 skills/change-map/scripts/set_map.py --dry-run \
  --source-type s3 --source s3://my-bucket/maps/warehouse.png \
  --metadata-yaml s3://my-bucket/maps/warehouse.yaml \
  --push-on-startup
```

Drop `--dry-run` to write.

## Things to flag

- `map_id` (derived from the Nav2 `image:` field) is the WPG cache key. Changing the source map but reusing an old `map_id` will serve the stale graph — call this out.
- If the Nav2 yaml's `origin[2]` (yaw) is non-zero, MC drops it. Surface that to the user; suggest pre-rotating the map image instead.
- `resolution`/`origin` in the yaml must match how the map was actually captured. Never guess these, and never borrow them from another map — see the rule at the top.
- Both shipped yamls write `image:` with the `.png` still on it, so `map_id` carries the extension. That is stable and unique, but it differs from the bare `carter_warehouse_navigation` in the inline block the skill ships by default — switching that map to its yaml changes the WPG cache key.

## After applying

Surface this once:

```bash
bash skills/bring-up-cloud-stack/scripts/up.sh --recreate
```

`--recreate` is required: `defaults.yaml` is bind-mounted, so the container spec doesn't change and plain `up` won't restart `mission-control` to re-read it.

If `--source-type s3` was used and the `s3:` section in `defaults.yaml` is empty, Mission Control will fail to fetch the map — mention this to the user.

## Out of scope

- Generating a Nav2 yaml from a raw map image (resolution / origin must come from the map's capture process).
- Editing `app/config/test_*.yaml` — those are test inputs, not the runtime config.
- Editing Helm chart map config under `helm-chart/`.
- Uploading new map files to `app/config/uploaded_maps/` — the user places files there; this skill only points the config at them. Seeding copies the maps this skill ships, and nothing else.
