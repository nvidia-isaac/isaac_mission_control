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

resolve() {
  local rel="$1"
  if [[ -f "$MC_WORKSPACE/$rel" ]]; then
    printf '%s' "$MC_WORKSPACE/$rel"
  else
    printf '%s' "$SKILL_DIR/resources/$rel"
  fi
}

REQUIRED_COMPOSE_VARS=(
  MOSQUITTO_IMAGE
  MQTT_PORT_TCP
  MQTT_PORT_WEBSOCKET
  POSTGRES_IMAGE
  POSTGRES_DATABASE_USERNAME
  POSTGRES_DATABASE_PASSWORD
  POSTGRES_DATABASE_NAME
  POSTGRES_DATABASE_PORT
  MISSION_DATABASE_IMAGE
  DATABASE_API_PORT
  DATABASE_CONTROLLER_PORT
  MISSION_DISPATCH_IMAGE
  MQTT_TRANSPORT
  WPG_IMAGE
  CUOPT_IMAGE
  CUOPT_PORT
  MISSION_CONTROL_IMAGE
  CONFIG_DIR
)
