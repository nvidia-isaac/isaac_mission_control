#!/usr/bin/env bash
# SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MC_WORKSPACE="${MC_WORKSPACE:-$PWD/skills-workspace}"

WITH_SIM=0
FOR_PULL=0

usage() {
  cat <<EOF
Usage: $0 [--with-sim] [--pull] [-h|--help]

Check that this host can run 'scripts/up.sh'. Read-only: starts nothing.

  --with-sim  Also check the robot-simulator profile's image.
  --pull      Treat absent images as must-pull rather than pull-on-first-up,
              and remind about registry credentials. Performs no network access.
  -h, --help  Show this help.

Exit codes: 0 = ready, 1 = at least one FAIL, 2 = bad usage.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-sim) WITH_SIM=1 ;;
    --pull)     FOR_PULL=1 ;;
    -h|--help)  usage; exit 0 ;;
    *)          echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

FAILURES=0
WARNINGS=0

pass() { printf '  [ PASS ] %s\n' "$*"; }
warn() { printf '  [ WARN ] %s\n' "$*"; WARNINGS=$((WARNINGS + 1)); }
fail() { printf '  [ FAIL ] %s\n' "$*"; FAILURES=$((FAILURES + 1)); }
hint() { printf '           %s\n' "$*"; }
section() { printf '\n%s\n' "$*"; }

. "$SKILL_DIR/scripts/lib/compose-config.sh"

resolved_tier() {
  local path="$1"
  if [[ "$path" == "$MC_WORKSPACE/"* ]]; then printf 'workspace'; else printf 'shipped'; fi
}

PORT_VARS=(
  MQTT_PORT_TCP MQTT_PORT_WEBSOCKET POSTGRES_DATABASE_PORT
  DATABASE_API_PORT DATABASE_CONTROLLER_PORT CUOPT_PORT MC_PORT
)

COMPOSE_SERVICES=(
  mosquitto postgres mission-database mission-dispatch wpg cuopt mission-control
  robot-simulator
)

echo "Mission Control cloud stack preflight"
echo "  skill:     $SKILL_DIR"
echo "  workspace: $MC_WORKSPACE"

section "Host tooling"

if ! command -v docker >/dev/null 2>&1; then
  fail "docker is not on PATH"
  hint "Install Docker Engine; every service in this stack is a container."
elif ! docker info >/dev/null 2>&1; then
  fail "docker is installed but the daemon is not reachable"
  hint "Start the daemon, or add your user to the 'docker' group and re-login."
else
  pass "docker daemon reachable"
fi

if docker compose version >/dev/null 2>&1; then
  pass "docker compose v2 available ($(docker compose version --short 2>/dev/null))"
else
  fail "docker compose v2 plugin not available"
  hint "up.sh calls 'docker compose' (v2). The legacy 'docker-compose' binary will not work."
fi

if command -v setfacl >/dev/null 2>&1; then
  pass "setfacl available"
else
  fail "setfacl not on PATH"
  hint "up.sh runs 'set -e' and uses setfacl to grant mission-control's"
  hint "container user write access to CONFIG_DIR/uploaded_maps without"
  hint "making it world-writable. Missing setfacl aborts up.sh before"
  hint "'docker compose' ever runs. Install the 'acl' package."
fi

section "Configuration files"

COMPOSE_FILE="$(resolve docker-compose/bringup_services.yaml)"
ENV_FILE="$(resolve docker-compose/.env)"
IMAGES_FILE="$(resolve docker-compose/images.conf)"
DEFAULTS_YAML="$(resolve app/config/defaults.yaml)"

for entry in \
  "compose file:$COMPOSE_FILE" \
  "credentials/ports:$ENV_FILE" \
  "image pins:$IMAGES_FILE" \
  "app defaults:$DEFAULTS_YAML"
do
  label="${entry%%:*}"
  path="${entry#*:}"
  if [[ -f "$path" ]]; then
    pass "$label ($(resolved_tier "$path")): $path"
  else
    fail "$label not found: $path"
    hint "The skill ships this under resources/; a missing file means a damaged install."
  fi
done

if [[ -d "$MC_WORKSPACE" ]]; then
  pass "workspace present (overrides in use where files exist)"
else
  pass "no workspace yet — all config read from the skill's shipped resources"
fi

section "Compose variables"

set -a
# shellcheck disable=SC1090
[[ -f "$ENV_FILE" ]] && . "$ENV_FILE"
# shellcheck disable=SC1090
[[ -f "$IMAGES_FILE" ]] && . "$IMAGES_FILE"
set +a

missing=()
for name in "${REQUIRED_COMPOSE_VARS[@]}"; do
  [[ -z "${!name:-}" ]] && missing+=("$name")
done

if [[ ${#missing[@]} -eq 0 ]]; then
  pass "all ${#REQUIRED_COMPOSE_VARS[@]} required compose variables resolved"
else
  fail "${#missing[@]} required compose variable(s) unset: ${missing[*]}"
  hint "These normally come from the resolved .env and images.conf above."
  hint "Export them, or restore the missing resource file."
fi

section "GPU (required by wpg and cuopt)"

if ! command -v nvidia-smi >/dev/null 2>&1; then
  fail "nvidia-smi not found — no usable NVIDIA driver"
elif ! nvidia-smi >/dev/null 2>&1; then
  fail "nvidia-smi present but failing — driver or device problem"
else
  pass "NVIDIA driver responding ($(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -n1))"
fi

if docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q nvidia; then
  pass "nvidia container runtime registered with Docker"
else
  fail "nvidia container runtime not registered with Docker"
  hint "Install the NVIDIA Container Toolkit; wpg and cuopt request GPU access."
fi

section "Host ports (all services use network_mode: host)"

port_in_use() {
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
}

for var in "${PORT_VARS[@]}"; do
  port="${!var:-}"
  if [[ -z "$port" ]]; then
    fail "$var is unset; the service has no port to bind"
    continue
  fi
  if port_in_use "$port"; then
    fail "$var=$port is already in use"
    hint "Free the port or change $var; host networking gives no isolation."
  else
    pass "$var=$port free"
  fi
done

section "Existing containers"

if docker info >/dev/null 2>&1; then
  running=()
  while IFS=$'\t' read -r cname csvc; do
    for svc in "${COMPOSE_SERVICES[@]}"; do
      [[ "$csvc" == "$svc" ]] && running+=("$cname")
    done
  done < <(docker ps --format '{{.Names}}\t{{.Label "com.docker.compose.service"}}' 2>/dev/null)

  if [[ ${#running[@]} -eq 0 ]]; then
    pass "no stack containers currently running"
  else
    warn "${#running[@]} stack container(s) already running: ${running[*]}"
    hint "up.sh will reuse them. Use --recreate only after confirming no active missions."
  fi
fi

section "Images"

images=(
  "${MOSQUITTO_IMAGE:-}" "${POSTGRES_IMAGE:-}" "${MISSION_DATABASE_IMAGE:-}"
  "${MISSION_DISPATCH_IMAGE:-}" "${WPG_IMAGE:-}" "${CUOPT_IMAGE:-}" "${MISSION_CONTROL_IMAGE:-}"
)
if [[ $WITH_SIM -eq 1 ]]; then
  if [[ -n "${MISSION_SIMULATOR_IMAGE:-}" ]]; then
    images+=("$MISSION_SIMULATOR_IMAGE")
  else
    fail "--with-sim was requested but MISSION_SIMULATOR_IMAGE is unset"
    hint "The robot-simulator profile has no image to start; up.sh --with-sim"
    hint "would fail on the missing reference."
  fi
fi

local_count=0
absent=()
for image in "${images[@]}"; do
  [[ -z "$image" ]] && continue
  if docker image inspect "$image" >/dev/null 2>&1; then
    local_count=$((local_count + 1))
  else
    absent+=("$image")
  fi
done

pass "$local_count of ${#images[@]} image(s) already present locally"
if [[ ${#absent[@]} -gt 0 ]]; then
  if [[ $FOR_PULL -eq 1 ]]; then
    warn "${#absent[@]} image(s) must be pulled: ${absent[*]}"
    hint "This check is offline: it reports what is absent locally, and does"
    hint "not contact any registry. Confirm credentials separately if needed."
  else
    warn "${#absent[@]} image(s) not local; compose will pull on first up: ${absent[*]}"
  fi
fi

section "Summary"
if [[ $FAILURES -eq 0 ]]; then
  echo "  READY — $WARNINGS warning(s). scripts/up.sh should start cleanly."
  exit 0
fi
echo "  NOT READY — $FAILURES failure(s), $WARNINGS warning(s). Resolve the FAIL items above."
exit 1
