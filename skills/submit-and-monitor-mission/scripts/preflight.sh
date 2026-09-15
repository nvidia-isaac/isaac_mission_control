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

usage() {
  cat <<EOF
Usage: $0 [mission.json] [-h|--help]

Check that this host can run 'scripts/submit_mission.sh'. Read-only: starts
nothing and submits nothing.

  mission.json  Optional path to the mission payload to check for.
                Defaults to 'mission.json' in the caller's cwd, matching
                submit_mission.sh's own default.

Exit codes: 0 = ready, 1 = at least one FAIL, 2 = bad usage.
EOF
}

MISSION_JSON="mission.json"
case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  -*)        echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  ?*)        MISSION_JSON="$1" ;;
esac
if [[ $# -gt 1 ]]; then
  echo "unexpected extra argument: $2" >&2
  echo "this script takes at most one mission payload path" >&2
  usage >&2
  exit 2
fi

FAILURES=0
WARNINGS=0
PAYLOAD_UNVALIDATED=0

pass() { printf '  [ PASS ] %s\n' "$*"; }
warn() { printf '  [ WARN ] %s\n' "$*"; WARNINGS=$((WARNINGS + 1)); }
fail() { printf '  [ FAIL ] %s\n' "$*"; FAILURES=$((FAILURES + 1)); }
hint() { printf '           %s\n' "$*"; }
section() { printf '\n%s\n' "$*"; }

echo "Mission Control submit-and-monitor-mission preflight"
echo "  skill:        $SKILL_DIR"
echo "  mission.json: $MISSION_JSON"

section "Host tooling"

if command -v curl >/dev/null 2>&1; then
  pass "curl available"
else
  fail "curl is not on PATH"
  hint "submit_mission.sh and the polling pattern in SKILL.md both use curl."
fi

if command -v docker >/dev/null 2>&1; then
  pass "docker available (used for log correlation)"
else
  warn "docker not on PATH"
  hint "Only needed to correlate Mission Dispatch and robot runtime logs"
  hint "after a mission reaches a terminal state."
fi

section "Environment"

if [[ -n "${MC_PORT:-}" ]]; then
  pass "MC_PORT=$MC_PORT"
else
  fail "MC_PORT is not exported"
  hint "submit_mission.sh requires MC_PORT; export it before running this skill."
fi

if [[ -n "${DATABASE_CONTROLLER_PORT:-}" ]]; then
  pass "DATABASE_CONTROLLER_PORT=$DATABASE_CONTROLLER_PORT"
else
  fail "DATABASE_CONTROLLER_PORT is not exported"
  hint "Required to poll Mission Database for the mission and robot terminal state."
fi

section "Mission payload"

if [[ -f "$MISSION_JSON" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    if python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$MISSION_JSON" >/dev/null 2>&1; then
      pass "mission payload is valid JSON: $MISSION_JSON"
    else
      fail "mission payload is not valid JSON: $MISSION_JSON"
      hint "submit_mission.sh passes this file's bytes straight through to"
      hint "curl --data; Mission Control will reject a malformed payload."
    fi
  else
    PAYLOAD_UNVALIDATED=1
    warn "mission payload found but unvalidated: $MISSION_JSON"
    hint "python3 is not on PATH, so its JSON was never checked. A malformed"
    hint "payload will fail at submission instead of here."
  fi
else
  warn "mission payload not present yet: $MISSION_JSON"
  hint "Not a blocker. Write the route or mission definition there before"
  hint "calling submit_mission.sh, or pass a different path as its first"
  hint "argument. submit_mission.sh fails if the file is still absent then."
fi

section "Summary"
if [[ $FAILURES -eq 0 ]]; then
  if (( PAYLOAD_UNVALIDATED )); then
    echo "  READY — $WARNINGS warning(s), but $MISSION_JSON was not validated; a malformed payload will fail at submission."
  elif [[ -f "$MISSION_JSON" ]]; then
    echo "  READY — $WARNINGS warning(s). scripts/submit_mission.sh should run cleanly."
  else
    echo "  READY — $WARNINGS warning(s). Write $MISSION_JSON, then scripts/submit_mission.sh should run cleanly."
  fi
  exit 0
fi
echo "  NOT READY — $FAILURES failure(s), $WARNINGS warning(s). Resolve the FAIL items above."
exit 1
