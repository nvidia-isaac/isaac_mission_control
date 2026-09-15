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

Check that this host can run 'scripts/set_map.py'. Read-only: writes nothing.

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

MAPS_DIR="$SKILL_DIR/resources/app/config/maps"
DEFAULTS_YAML="$SKILL_DIR/resources/app/config/defaults.yaml"

echo "Mission Control change-map preflight"
echo "  skill:     $SKILL_DIR"
echo "  workspace: $MC_WORKSPACE"

section "Host tooling"

if ! command -v python3 >/dev/null 2>&1; then
  fail "python3 is not on PATH"
  hint "set_map.py is a python3 script. It uses only the standard library,"
  hint "so no packages need installing, but an interpreter is required."
else
  pass "python3 available ($(python3 --version 2>&1))"
fi

section "Shipped resources"

if [[ -f "$DEFAULTS_YAML" ]]; then
  pass "app defaults: $DEFAULTS_YAML"
else
  fail "app defaults not found: $DEFAULTS_YAML"
  hint "The skill ships this under resources/; a missing file means a damaged install."
fi

if [[ -d "$MAPS_DIR" ]]; then
  map_count=$(find "$MAPS_DIR" -maxdepth 1 -type f -name '*.png' 2>/dev/null | wc -l)
  if [[ "$map_count" -gt 0 ]]; then
    pass "$map_count bundled map image(s) in $MAPS_DIR"
  else
    fail "no map images in $MAPS_DIR"
    hint "--map has nothing to resolve. The skill ships its maps under resources/."
  fi
else
  fail "bundled maps directory not found: $MAPS_DIR"
fi

if [[ -d "$MAPS_DIR" && "${map_count:-0}" -gt 0 ]]; then
  malformed=()
  sidecarless=()
  while IFS= read -r png; do
    if [[ "$(head -c 8 "$png" | od -An -tx1 | tr -d ' \n')" != "89504e470d0a1a0a" ]]; then
      malformed+=("$(basename "$png")")
    fi
    if [[ ! -f "${png%.png}.yaml" ]]; then
      sidecarless+=("$(basename "$png")")
    fi
  done < <(find "$MAPS_DIR" -maxdepth 1 -type f -name '*.png' 2>/dev/null)

  if [[ ${#malformed[@]} -eq 0 ]]; then
    pass "map images carry a valid PNG signature"
  else
    fail "${#malformed[@]} map(s) are not PNG images: ${malformed[*]}"
    hint "Most often these are unresolved Git LFS pointers. Mission Control cannot"
    hint "read one as a map. Run 'git lfs pull' in the source repository, or"
    hint "reinstall the skill from a checkout that materialized its LFS objects."
  fi

  if [[ ${#sidecarless[@]} -eq 0 ]]; then
    pass "every bundled map has its sibling Nav2 yaml"
  else
    warn "${#sidecarless[@]} map(s) ship without a Nav2 yaml: ${sidecarless[*]}"
    hint "--map cannot resolve metadata for these; they need --metadata-yaml."
  fi
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

section "Applying the change"

if [[ -x "$SKILL_DIR/../bring-up-cloud-stack/scripts/up.sh" ]]; then
  pass "bring-up-cloud-stack is installed alongside this skill"
else
  warn "bring-up-cloud-stack not found next to this skill"
  hint "This skill only edits configuration. Mission Control reads it at startup,"
  hint "so the change has no effect until the stack is (re)started with"
  hint "bring-up-cloud-stack's scripts/up.sh --recreate. Install that skill from"
  hint "the mission-control repository to apply the map."
fi

section "Summary"
if [[ $FAILURES -eq 0 ]]; then
  echo "  READY — $WARNINGS warning(s). scripts/set_map.py should run cleanly."
  exit 0
fi
echo "  NOT READY — $FAILURES failure(s), $WARNINGS warning(s). Resolve the FAIL items above."
exit 1
