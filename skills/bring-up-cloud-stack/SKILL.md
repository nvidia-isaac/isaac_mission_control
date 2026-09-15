---
name: bring-up-cloud-stack
license: Apache-2.0
description: Use when starting Mission Control cloud services from the repository compose stack.
metadata:
  author: NVIDIA Isaac Team <info@nvidia.com>
  version: 1.0.0
  permissions:
    file_read:
      - resources/docker-compose/bringup_services.yaml
      - resources/docker-compose/.env
      - resources/docker-compose/images.conf
      - resources/app/config/defaults.yaml
    file_write: []
    execute:
      - skills/bring-up-cloud-stack/scripts/preflight.sh
      - skills/bring-up-cloud-stack/scripts/up.sh
---

# Bring up cloud stack

## Purpose

Start the Mission Control cloud services when the user says "bring up the stack", "start mission control", "boot the cloud stack", or "run mission control with the sim". This skill covers release-quality/prebuilt image bringup for the repository compose stack.

The source of truth is:

- `docker-compose/bringup_services.yaml` for services, profiles, startup ownership, and dependencies.
- Exported compose variables for images, ports, MQTT transport, credentials, and `CONFIG_DIR`.

Do not hard-code a latest release tag or a fixed port in this skill. Update compose variables through `change-stack-version` or an explicit user-requested edit, then use this skill to pull/start what those variables select.

**Do not invoke `docker compose` by hand for normal stack bringup.** Use `skills/bring-up-cloud-stack/scripts/up.sh` so profile selection, config resolution, variable preflight, detach mode, pull semantics, and recreate behavior stay consistent.

## Prerequisites

Run `scripts/preflight.sh` to check all of these at once. It is read-only and
starts nothing; it exits non-zero and names what is missing.

### Required on the host

- Docker Engine with a reachable daemon.
- Docker Compose **v2** (`docker compose`, not the legacy `docker-compose` binary).
- An NVIDIA GPU, driver, and the NVIDIA Container Toolkit registered with
  Docker. `wpg` and `cuopt` request GPU access and will not start without it.
- Free host ports for `MQTT_PORT_TCP`, `MQTT_PORT_WEBSOCKET`,
  `POSTGRES_DATABASE_PORT`, `DATABASE_API_PORT`, `DATABASE_CONTROLLER_PORT`,
  `CUOPT_PORT`, and `MC_PORT`. Every service is `network_mode: host`, so an
  occupied port surfaces as a container or health-check failure, not as a
  bringup error.
- Registry credentials **only if** a selected image is not public. The images
  pinned in `resources/docker-compose/images.conf` do not require a login.

### Not required

- **A Mission Control checkout.** The skill ships everything it reads under
  `resources/`: the compose file, `.env`, `images.conf`, and
  `app/config/defaults.yaml`. A fresh machine with no clone can run this skill.
- **Exported compose variables.** `up.sh` sources the resolved `.env` and
  `images.conf` itself. Its required-variable check is a guard against a
  damaged install, not a request for the caller to export 18 values.

### Optional

- `MC_WORKSPACE` (default `./skills-workspace`) selects a directory whose files
  override the shipped ones, path for path. It starts empty; the mutation
  skills (`change-map`, `change-fleet-composition`, `change-stack-version`)
  write into it. Point it at a Mission Control checkout to drive that checkout
  instead, since `resources/` mirrors the product repo layout exactly — note
  that `up.sh` fills any gap in that checkout's `app/config/` so the mount is
  complete, which can leave an untracked file behind.

## Configuration Resolution

`up.sh` reads each of these files from the workspace if it is there, else from
the skill's own `resources/`:

| Relative path | Workspace override | Shipped fallback |
|---|---|---|
| `docker-compose/bringup_services.yaml` | `$MC_WORKSPACE/...` | `resources/...` |
| `docker-compose/.env` | `$MC_WORKSPACE/...` | `resources/...` |
| `docker-compose/images.conf` | `$MC_WORKSPACE/...` | `resources/...` |

`images.conf` is sourced after `.env` so an image set by `change-stack-version`
wins over a stale duplicate in an older workspace copy.

`app/config/` is not resolved that way, because mission-control bind-mounts it
as one directory rather than reading files from it individually. Picking the
tier per file would mount a directory holding whatever the mutation skills
wrote and nothing else — an edited `defaults.yaml` with no `maps/` beside it,
which mission-control serves as a 503. `CONFIG_DIR` is therefore always
`$MC_WORKSPACE/app/config`, and `up.sh` copies in every file the workspace is
missing, never over one already there. Nothing is written back to `resources/`.

`bringup_services.yaml` is byte-identical to Mission Control's own
`docker-compose/bringup_services.yaml`. It mounts `./init-db.sh`, which compose
resolves next to the compose file, so `up.sh` puts `init-db.sh` beside a
workspace copy the same way; the shipped tier already ships the two together.

Variables the resolved files supply: `MOSQUITTO_IMAGE`, `POSTGRES_IMAGE`,
`MISSION_DATABASE_IMAGE`, `MISSION_DISPATCH_IMAGE`, `WPG_IMAGE`, `CUOPT_IMAGE`,
`MISSION_CONTROL_IMAGE`, `MQTT_PORT_TCP`, `MQTT_PORT_WEBSOCKET`,
`MQTT_TRANSPORT`, `POSTGRES_DATABASE_USERNAME`, `POSTGRES_DATABASE_PASSWORD`,
`POSTGRES_DATABASE_NAME`, `POSTGRES_DATABASE_PORT`, `DATABASE_API_PORT`,
`DATABASE_CONTROLLER_PORT`, `CUOPT_PORT`. Export any of them yourself only to
deliberately override the resolved value. `CONFIG_DIR` is the exception:
`.env` defines it and preflight counts it among the 18, but `up.sh` overwrites
it after sourcing, so neither the value in `.env` nor one you export has any
effect.

## Instructions

1. Read the requested mode: cloud only, cloud plus simulator, foreground logs, image pull, config reread, or dry run.
2. Run `skills/bring-up-cloud-stack/scripts/preflight.sh` and resolve every
   `FAIL` before invoking the runner. It is read-only and starts nothing. See
   the Preflight section for what it checks and what remains a judgment call.
3. Prefer `run_script()` with `skills/bring-up-cloud-stack/scripts/up.sh` when the environment provides a script runner:

   ```python
   run_script("skills/bring-up-cloud-stack/scripts/up.sh")
   run_script("skills/bring-up-cloud-stack/scripts/up.sh", args=["--with-sim"])
   run_script("skills/bring-up-cloud-stack/scripts/up.sh", args=["--pull"])
   run_script("skills/bring-up-cloud-stack/scripts/up.sh", args=["--with-sim", "--pull", "--dry-run"])
   ```

4. If `run_script()` is unavailable, run the same script directly by its absolute or repo-relative path.
5. Use `--recreate` only after a dry-run preview, explicit user confirmation, and confirmation that no active robot missions are in progress. `--recreate` interrupts running services.
6. Use `--pull` after image references change, for example after
   `change-stack-version` rewrites `images.conf`.
7. After detached startup, check Mission Control health and logs as described below.

## Available Scripts

| Script | Purpose | Arguments |
|---|---|---|
| `skills/bring-up-cloud-stack/scripts/preflight.sh` | Read-only readiness check: host tooling, resolved config files, compose variables, GPU and container toolkit, host port availability, existing containers, local images. Exits 1 when anything required is missing. Starts nothing and performs no network access. | `--with-sim`, `--pull`, `-h`/`--help` |
| `skills/bring-up-cloud-stack/scripts/up.sh` | Bring up the compose stack through the resolved `bringup_services.yaml` and the variables sourced from the resolved `.env` and `images.conf`. | `--with-sim`, `--foreground`, `--pull`, `--recreate`, `--dry-run`, `-h`/`--help` |

## What this skill brings up

From the resolved `docker-compose/bringup_services.yaml` (see Configuration
Resolution) under `--profile enable_mission_control`:

- `mosquitto` - MQTT broker
- `postgres` - DB for mission-database
- `mission-database` - REST API for mission state
- `mission-dispatch` - VDA5050 dispatcher
- `wpg` - waypoint graph service, requires GPU
- `cuopt` - routing solver, requires GPU
- `mission-control` - the orchestrator, only under `enable_mission_control`

With `--with-sim`, the runner also enables `--profile robot-simulator`, which starts the `mission-simulator` container using the `--robots` command in `bringup_services.yaml`.

`--with-sim` starts the *generic* simulator. Orchestration skills that supply
their own robot runtime, such as `mission-control-showcase` with Nova Carter
SIL, must not pass it.

## Preflight

Run the script first; it covers everything mechanically checkable:

```bash
skills/bring-up-cloud-stack/scripts/preflight.sh
skills/bring-up-cloud-stack/scripts/preflight.sh --with-sim --pull
```

It reports `PASS`/`WARN`/`FAIL` per check and exits 1 if any check failed:

| Check | Severity when unmet |
|---|---|
| Docker daemon reachable | FAIL |
| Docker Compose v2 present | FAIL |
| All four config files resolve (and from which tier) | FAIL |
| All 18 required compose variables resolved | FAIL |
| NVIDIA driver responding | FAIL |
| NVIDIA container runtime registered with Docker | FAIL |
| Each host port free | FAIL |
| Stack containers already running | WARN |
| Images not present locally | WARN |

Both scripts resolve configuration through `scripts/lib/compose-config.sh`,
so the preflight and the runner cannot disagree about which files they read.
`--pull` is offline: it reports which images are absent locally and does not
contact a registry.

These remain judgment calls the script deliberately does not make:

- Confirm `app/config/defaults.yaml` matches the desired map and fleet. Use
  `change-map` and `change-fleet-composition` before bringup when it does not.
- Before `--recreate`, confirm no active robot missions are in progress and
  show the user the `--dry-run` output for the exact command. `--recreate`
  interrupts running services.
- If a stack container is already running, decide whether reusing it is correct
  for the requested mode, or whether its image and command still match the
  resolved compose file.

## Flags

- `--with-sim` - also enable the `robot-simulator` profile.
- `--foreground` - run `up` attached. Default is detached `-d`.
- `--pull` - run `docker compose pull` before `up`. Use after the resolved `images.conf` changes, for example after `change-stack-version`.
- `--recreate` - add `--force-recreate` to `up`. This interrupts running services; use only after dry-run review, explicit user confirmation, and confirmation that no active missions are running.
- `--dry-run` - print the compose commands without executing them.

## Examples

The script reads the compose file, `.env`, and `images.conf` from a workspace at `$MC_WORKSPACE` (default `./skills-workspace` in the caller's cwd) if the user has edited them there, else from the skill's bundled `resources/`; `app/config/` is always mounted from the workspace and seeded from `resources/`. It does not require a mission-control source checkout.

The credentials file and `images.conf` are deliberately separate: the former carries ports and the MQTT/postgres secrets, while `images.conf` carries only `*_IMAGE` references so `change-stack-version` can rewrite image tags without touching a file that holds secrets. The runner sources the credentials file first and `images.conf` second, so an image set by `change-stack-version` wins over a stale duplicate in an older workspace copy.

```bash
# Default: cloud services only, detached, no pull
skills/bring-up-cloud-stack/scripts/up.sh

# Cloud + sim robots, detached
skills/bring-up-cloud-stack/scripts/up.sh --with-sim

# Refresh images first, for example right after change-stack-version
skills/bring-up-cloud-stack/scripts/up.sh --pull

# Preview a recreate command before asking the user to confirm it
skills/bring-up-cloud-stack/scripts/up.sh --recreate --dry-run

# After explicit confirmation and no active missions: recreate containers so bind-mounted config is reread
skills/bring-up-cloud-stack/scripts/up.sh --recreate

# Live logs in the foreground
skills/bring-up-cloud-stack/scripts/up.sh --foreground

# Preview commands without running
skills/bring-up-cloud-stack/scripts/up.sh --with-sim --pull --dry-run
```

Equivalent `run_script()` examples:

```python
run_script("skills/bring-up-cloud-stack/scripts/up.sh")
run_script("skills/bring-up-cloud-stack/scripts/up.sh", args=["--with-sim"])
run_script("skills/bring-up-cloud-stack/scripts/up.sh", args=["--pull"])
run_script("skills/bring-up-cloud-stack/scripts/up.sh", args=["--foreground"])
run_script("skills/bring-up-cloud-stack/scripts/up.sh", args=["--with-sim", "--pull", "--dry-run"])
run_script("skills/bring-up-cloud-stack/scripts/up.sh", args=["--recreate", "--dry-run"])
```

The script can be called via either an absolute or relative path. The workspace it reads user edits from is `$MC_WORKSPACE` (default `./skills-workspace` in the caller's cwd); anything not present there is read straight from the skill's bundled `resources/`.

## Troubleshooting

### Container Recovery

Avoid destructive recovery unless the user explicitly asks. Do not use:

- `docker compose down -v`
- `docker rm`
- `docker system prune`

If an existing container has the wrong image or command, preview `skills/bring-up-cloud-stack/scripts/up.sh --recreate --dry-run`, then run the recreate command only after explicit user confirmation and confirmation that no active missions are in progress. Use a service-scoped `docker compose ... up -d --force-recreate <service>` only when preserving the rest of the stack matters. Use a new compose project name when preserving old containers for inspection matters.

### Dispatch Transport

Mission Dispatch should use the transport configured in compose variables:

- `MQTT_TRANSPORT=websockets` uses `MQTT_PORT_WEBSOCKET`.
- `MQTT_TRANSPORT=tcp` uses `MQTT_PORT_TCP`.

If the desired broker topology is not represented, ask for explicit approval before changing the resolved compose variables, editing `bringup_services.yaml`, or editing an appropriate compose profile. Do not run a separate Mission Dispatch container by hand.

### Startup Health

If launched detached, surface this once:

```bash
# Tail logs across the stack
docker compose -f docker-compose/bringup_services.yaml \
  --profile enable_mission_control logs -f

# Tail one service
docker compose -f docker-compose/bringup_services.yaml logs -f mission-control
```

Read `MC_PORT` from the resolved `.env`, then check Mission Control health:

```bash
curl -fsS http://localhost:${MC_PORT}/api/v1/health
```

If that 404s or refuses, Mission Control either has not finished startup or crashed. Check compose logs.

Mission Control stack bringup is not fully validated until a mission completes through Mission Database and Dispatch. Use `submit-and-monitor-mission` for that final check.

## Stopping

Stop the same profiles that were started, without deleting images or volumes:

```bash
docker compose -f docker-compose/bringup_services.yaml \
  --profile enable_mission_control stop

# Or, if --with-sim was used:
docker compose -f docker-compose/bringup_services.yaml \
  --profile enable_mission_control \
  --profile robot-simulator stop
```

## Limitations

- `bringup_demo_services.yaml`, the replan/SAP demo variant with `esp`/`mas` instead of `cuopt`.
- Helm chart deployment under `helm-chart/`.
- Building images locally via Bazel or `scripts/run_dev.sh`; this skill only orchestrates prebuilt compose services.
- Editing `images.conf`, `.env`, or `defaults.yaml`; use `change-stack-version`, `change-map`, and `change-fleet-composition`.
- Bringing up isolated subsets of services. Compose accepts service positional args, but selective bringup is not this skill's purpose.
