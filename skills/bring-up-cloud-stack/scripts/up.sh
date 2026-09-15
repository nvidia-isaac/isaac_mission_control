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

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MC_WORKSPACE="${MC_WORKSPACE:-$PWD/skills-workspace}"
export COMPOSE_DISABLE_ENV_FILE=1

. "$SKILL_DIR/scripts/lib/compose-config.sh"

COMPOSE_FILE="$(resolve docker-compose/bringup_services.yaml)"
ENV_FILE="$(resolve docker-compose/.env)"
IMAGES_FILE="$(resolve docker-compose/images.conf)"

WITH_SIM=0
FOREGROUND=0
PULL=0
RECREATE=0
DRY_RUN=0

usage() {
  cat <<EOF
Usage: $0 [--with-sim] [--foreground] [--pull] [--recreate] [--dry-run]

Bring up the Mission Control cloud stack (mosquitto, postgres,
mission-database, mission-dispatch, wpg, cuopt, mission-control) via
docker compose, using ${COMPOSE_FILE}, exported compose variables, and the
enable_mission_control profile.

Options:
  --with-sim    Also enable the robot-simulator profile.
  --foreground  Run 'docker compose up' attached (default: -d).
  --pull        Run 'docker compose pull' before 'up'.
  --recreate    Add '--force-recreate' to 'up' so bind-mounted config is reread.
  --dry-run     Print the docker compose commands without running them.
  -h, --help    Show this message.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-sim)   WITH_SIM=1 ;;
    --foreground) FOREGROUND=1 ;;
    --pull)       PULL=1 ;;
    --recreate)   RECREATE=1 ;;
    --dry-run)    DRY_RUN=1 ;;
    -h|--help)    usage; exit 0 ;;
    *)            echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

PROFILES=(--profile enable_mission_control)
if [[ $WITH_SIM -eq 1 ]]; then
  PROFILES+=(--profile robot-simulator)
fi

check_required_environment() {
  local missing=()
  local name

  for name in "${REQUIRED_COMPOSE_VARS[@]}"; do
    if [[ -z "${!name:-}" ]]; then
      missing+=("$name")
    fi
  done

  if [[ ${#missing[@]} -gt 0 ]]; then
    {
      echo "Missing required compose environment variables:"
      printf "  %s\n" "${missing[@]}"
      echo
      echo "Export these variables in the shell before running this script."
      echo "Before using --pull, ensure registry credentials are already available through approved Docker or environment-based authentication."
    } >&2
    return 2
  fi
}

set -a
# shellcheck disable=SC1091
. "$ENV_FILE"
if [[ -f "$IMAGES_FILE" ]]; then
  # shellcheck disable=SC1091
  . "$IMAGES_FILE"
else
  echo "warning: image variable file not found at $IMAGES_FILE;" >&2
  echo "         falling back to whatever *_IMAGE values the credentials file supplied." >&2
fi
CONFIG_DIR="$MC_WORKSPACE/app/config"
set +a

check_required_environment

COMPOSE=(docker compose -f "$COMPOSE_FILE" "${PROFILES[@]}")

run() {
  echo "+ $*"
  if [[ $DRY_RUN -eq 0 ]]; then "$@"; fi
}

CONFIG_SRC="$SKILL_DIR/resources/app/config"
while IFS= read -r -d '' src; do
  rel="${src#"$CONFIG_SRC/"}"
  [[ -e "$CONFIG_DIR/$rel" ]] && continue
  run mkdir -p "$(dirname "$CONFIG_DIR/$rel")"
  run cp "$src" "$CONFIG_DIR/$rel"
done < <(find "$CONFIG_SRC" -type f -print0)

COMPOSE_DIR="$(dirname "$COMPOSE_FILE")"
if [[ ! -f "$COMPOSE_DIR/init-db.sh" ]]; then
  run cp "$SKILL_DIR/resources/docker-compose/init-db.sh" "$COMPOSE_DIR/init-db.sh"
fi

run mkdir -p "$CONFIG_DIR/uploaded_maps"
run setfacl -m u:1000:rwx "$CONFIG_DIR/uploaded_maps"

if [[ $PULL -eq 1 ]]; then
  run "${COMPOSE[@]}" pull
fi

UP_ARGS=(up)
if [[ $RECREATE -eq 1 ]]; then
  UP_ARGS+=(--force-recreate)
fi
if [[ $FOREGROUND -eq 0 ]]; then
  UP_ARGS+=(-d)
fi

run "${COMPOSE[@]}" "${UP_ARGS[@]}"
