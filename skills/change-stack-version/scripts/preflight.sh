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
SET_IMAGE="$SKILL_DIR/scripts/set_image.py"

usage() {
  cat <<EOF
Usage: $0 --service SERVICE (--tag TAG | --image IMAGE) [--images-file PATH]

Verify that the exact set_image.py operation can run successfully. The script
is read-only: it exercises set_image.py with --dry-run and writes nothing.

Arguments are the same as set_image.py. Use --images-file to override the
default target at \$MC_WORKSPACE/docker-compose/images.conf.

Exit codes: 0 = ready, 1 = at least one FAIL, 2 = bad usage.
EOF
}

if [[ $# -eq 0 ]]; then
  usage >&2
  exit 2
fi

OPERATION_ARGS=()
IMAGES_FILE="$MC_WORKSPACE/docker-compose/images.conf"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --images-file|--images-env|--compose-config|--env)
      if [[ $# -lt 2 ]]; then
        echo "missing value for $1" >&2
        usage >&2
        exit 2
      fi
      IMAGES_FILE="$2"
      OPERATION_ARGS+=("$1" "$2")
      shift 2
      ;;
    --images-file=*|--images-env=*|--compose-config=*|--env=*)
      IMAGES_FILE="${1#*=}"
      OPERATION_ARGS+=("$1")
      shift
      ;;
    --dry-run)
      # Preflight always adds this flag; accepting it keeps the CLI compatible
      # with set_image.py without changing the result.
      shift
      ;;
    *)
      OPERATION_ARGS+=("$1")
      shift
      ;;
  esac
done

FAILURES=0

pass() { printf '  [ PASS ] %s\n' "$*"; }
fail() { printf '  [ FAIL ] %s\n' "$*"; FAILURES=$((FAILURES + 1)); }
hint() { printf '           %s\n' "$*"; }
section() { printf '\n%s\n' "$*"; }

echo "Mission Control change-stack-version preflight"
echo "  skill:     $SKILL_DIR"
echo "  workspace: $MC_WORKSPACE"
echo "  target:    $IMAGES_FILE"

section "Host tooling"

if ! command -v python3 >/dev/null 2>&1; then
  fail "python3 is not on PATH"
  hint "set_image.py uses only the standard library, but it requires python3."
else
  pass "python3 available ($(python3 --version 2>&1))"
fi

if [[ -r "$SET_IMAGE" ]]; then
  pass "set_image.py available: $SET_IMAGE"
else
  fail "set_image.py is missing or unreadable: $SET_IMAGE"
  hint "Reinstall the skill from a complete Mission Control checkout."
fi

section "Destination"

if [[ -e "$IMAGES_FILE" ]]; then
  if [[ ! -f "$IMAGES_FILE" ]]; then
    fail "target exists but is not a regular file: $IMAGES_FILE"
  elif [[ ! -w "$IMAGES_FILE" ]]; then
    fail "target is not writable: $IMAGES_FILE"
  else
    pass "target file is writable"
  fi
else
  ancestor="$(dirname "$IMAGES_FILE")"
  while [[ ! -e "$ancestor" && "$ancestor" != "/" && "$ancestor" != "." ]]; do
    ancestor="$(dirname "$ancestor")"
  done

  if [[ ! -d "$ancestor" ]]; then
    fail "target cannot be created because an ancestor is not a directory: $ancestor"
  elif [[ ! -w "$ancestor" || ! -x "$ancestor" ]]; then
    fail "target cannot be created under: $ancestor"
  else
    pass "target can be created under $ancestor"
  fi
fi

section "Operation dry-run"

if command -v python3 >/dev/null 2>&1 && [[ -r "$SET_IMAGE" ]]; then
  if dry_run_output="$(python3 "$SET_IMAGE" "${OPERATION_ARGS[@]}" --dry-run 2>&1)"; then
    pass "set_image.py accepted the requested operation"
    while IFS= read -r line; do
      printf '           %s\n' "$line"
    done <<< "$dry_run_output"
  else
    fail "set_image.py rejected the requested operation"
    while IFS= read -r line; do
      hint "$line"
    done <<< "$dry_run_output"
  fi
else
  fail "operation dry-run skipped because host tooling is unavailable"
fi

section "Summary"
if [[ $FAILURES -eq 0 ]]; then
  echo "  READY — rerun set_image.py with the same arguments to apply the change."
  exit 0
fi
echo "  NOT READY — $FAILURES failure(s). Resolve the FAIL items above."
exit 1
