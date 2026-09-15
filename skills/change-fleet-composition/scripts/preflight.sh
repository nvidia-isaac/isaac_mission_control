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

usage() {
  cat <<EOF
Usage: $0 [-h|--help]

Check that this host can run 'scripts/set_fleet.py'. Read-only: writes nothing.

Exit codes: 0 = ready, 1 = at least one FAIL, 2 = bad usage.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    *)         echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
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

DEFAULTS_YAML="$SKILL_DIR/resources/app/config/defaults.yaml"
BRINGUP_YAML="$SKILL_DIR/resources/docker-compose/bringup_services.yaml"

echo "Mission Control change-fleet-composition preflight"
echo "  skill:     $SKILL_DIR"
echo "  workspace: $MC_WORKSPACE"

section "Host tooling"

if ! command -v python3 >/dev/null 2>&1; then
  fail "python3 is not on PATH"
  hint "set_fleet.py is a python3 script. It uses only the standard library,"
  hint "so no packages need installing, but an interpreter is required."
else
  pass "python3 available ($(python3 --version 2>&1))"
fi

section "Shipped resources"

if [[ -f "$DEFAULTS_YAML" ]]; then
  if grep -qE '^robots:[[:space:]]*$' "$DEFAULTS_YAML"; then
    pass "app defaults with a robots: block: $DEFAULTS_YAML"
  else
    fail "no 'robots:' block in $DEFAULTS_YAML"
    hint "set_fleet.py splices the fleet into that block; without it the"
    hint "script cannot place the new definition."
  fi
else
  fail "app defaults not found: $DEFAULTS_YAML"
  hint "The skill ships this under resources/; a missing file means a damaged install."
fi

if [[ -f "$BRINGUP_YAML" ]]; then
  pass "compose file: $BRINGUP_YAML"
  if grep -qE '^  robot-simulator:' "$BRINGUP_YAML"; then
    if awk '/^  robot-simulator:/{f=1; next} f && /^  [^ ]/{f=0} f && /^    command:[[:space:]]*\[/{found=1} END{exit !found}' "$BRINGUP_YAML"; then
      pass "robot-simulator service has a command: line to rewrite"
    else
      fail "robot-simulator service has no 'command: [...]' line"
      hint "set_fleet.py rewrites that line to match the simulated fleet. Without"
      hint "it the simulator keeps spawning its built-in robots while"
      hint "defaults.yaml advertises the new ones, and the script cannot warn you."
    fi
  else
    fail "no 'robot-simulator' service in $BRINGUP_YAML"
    hint "The simulated fleet is driven by that service's command: line."
  fi
else
  fail "compose file not found: $BRINGUP_YAML"
  hint "The skill ships this under resources/; a missing file means a damaged install."
fi

section "Workspace"

if [[ -e "$MC_WORKSPACE" ]]; then
  if [[ -w "$MC_WORKSPACE" ]]; then
    pass "workspace exists and is writable"
  else
    fail "workspace exists but is not writable: $MC_WORKSPACE"
  fi
else
  parent="$(dirname "$MC_WORKSPACE")"
  if [[ -w "$parent" ]]; then
    pass "workspace will be created under $parent"
  else
    fail "cannot create the workspace; $parent is not writable"
  fi
fi

if ! env | grep -q '^MC_WORKSPACE='; then
  warn "MC_WORKSPACE is unset; it defaults to ./skills-workspace in the caller's cwd"
  hint "Running from a different directory edits a different workspace. Export"
  hint "MC_WORKSPACE to pin it."
fi

WS_BRINGUP="$MC_WORKSPACE/docker-compose/bringup_services.yaml"
WS_DEFAULTS="$MC_WORKSPACE/app/config/defaults.yaml"
if [[ -f "$WS_DEFAULTS" && ! -f "$WS_BRINGUP" ]]; then
  warn "workspace has defaults.yaml but no docker-compose/bringup_services.yaml"
  hint "set_fleet.py would edit the fleet and skip the simulator sync, leaving"
  hint "the simulator spawning the previous robots. Run bring-up-cloud-stack's"
  hint "scripts/up.sh once to seed the workspace, or remove the partial copy."
fi

if [[ -f "$WS_BRINGUP" ]]; then
  if ! grep -qE '^  robot-simulator:' "$WS_BRINGUP"; then
    fail "no 'robot-simulator' service in $WS_BRINGUP"
    hint "The workspace copy overrides the shipped one. set_fleet.py edits this"
    hint "file, so the fleet would reach defaults.yaml and never reach the simulator."
  elif ! awk '/^  robot-simulator:/{f=1; next} f && /^  [^ ]/{f=0} f && /^    command:[[:space:]]*\[/{found=1} END{exit !found}' "$WS_BRINGUP"; then
    fail "robot-simulator service in $WS_BRINGUP has no 'command: [...]' line"
    hint "Most often a workspace seeded from an older stack. set_fleet.py would"
    hint "report no-op for this file and exit 0 with the fleet only half applied."
  else
    pass "workspace compose has a robot-simulator command: line to rewrite"
  fi
fi

section "Applying the change"

if [[ -x "$SKILL_DIR/../bring-up-cloud-stack/scripts/up.sh" ]]; then
  pass "bring-up-cloud-stack is installed alongside this skill"
else
  warn "bring-up-cloud-stack not found next to this skill"
  hint "This skill only edits configuration. Mission Control reads it at startup,"
  hint "so the change has no effect until the stack is (re)started with"
  hint "bring-up-cloud-stack's scripts/up.sh --recreate. Install that skill from"
  hint "the mission-control repository to apply the fleet."
fi

section "Summary"
if [[ $FAILURES -eq 0 ]]; then
  echo "  READY — $WARNINGS warning(s). scripts/set_fleet.py should run cleanly."
  exit 0
fi
echo "  NOT READY — $FAILURES failure(s), $WARNINGS warning(s). Resolve the FAIL items above."
exit 1
