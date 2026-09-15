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

MISSION_JSON="${1:-mission.json}"

if [[ ! -f "${MISSION_JSON}" ]]; then
  echo "error: mission payload not found: ${MISSION_JSON}" >&2
  exit 1
fi

if [[ -z "${MC_PORT:-}" ]]; then
  echo "error: MC_PORT is not set; export it before running this skill" >&2
  exit 1
fi

MISSION_ID="${MISSION_ID:-codex-mission-$(date +%s)}"
ROBOT_NAME="${ROBOT_NAME:-carter01}"

echo "Submitting mission ${MISSION_ID} for robot ${ROBOT_NAME}"

curl -fsS -X POST \
  -H "Content-Type: application/json" \
  "http://127.0.0.1:${MC_PORT}/api/v1/mission/submit_mission?mission_id=${MISSION_ID}&mandatory_robot_name=${ROBOT_NAME}" \
  --data @"${MISSION_JSON}"
