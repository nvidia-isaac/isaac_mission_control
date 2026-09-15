#!/bin/bash
# SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
# Copyright (c) 2022-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

# Enters the developer container. The image is built (if missing or stale) by
# scripts/build_dev_image.sh.

set -e

# Create bazel cache directory if it doesn't exist
if [ ! -d "$HOME/.cache/bazel" ]; then
  # Folder does not exist, so create it
  mkdir -p "$HOME/.cache/bazel"
fi

# Create pip-tools cache directory if it doesn't exist
if [ ! -d "$HOME/.cache/pip-tools" ]; then
  # Folder does not exist, so create it
  mkdir -p "$HOME/.cache/pip-tools"
fi

ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )"/.. >/dev/null 2>&1 && pwd )"
IMAGE_NAME="isaac-mission-control-dev"
DOCKER_GROUP_ID="$(getent group docker | cut -d: -f3)"

# Ensure the dev container image exists and is fresh.
"${ROOT}/scripts/build_dev_image.sh"

docker run -it --rm \
--gpus all \
--network host \
--workdir "$PWD" \
-e "WORKSPACE=$ROOT" \
--env AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
--env AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
--env AWS_REGION=$AWS_REGION \
--env AWS_ENDPOINT_URL=$AWS_ENDPOINT_URL \
--env DEEPMAP_VEHICLE_TOKEN=$DEEPMAP_VEHICLE_TOKEN \
-v "$ROOT:$ROOT" \
-v /etc/passwd:/etc/passwd:ro \
-v /etc/timezone:/etc/timezone:ro \
-v /etc/group:/etc/group:ro \
-v "$HOME/.docker:$HOME/.docker:ro" \
-v "$HOME/.docker/buildx:$HOME/.docker/buildx" \
-v "$HOME/.kube:$HOME/.kube:ro" \
-v "/etc/timezone:/etc/timezone:ro" \
-v "$HOME/.cache/bazel:$HOME/.cache/bazel" \
-v "$HOME/.cache/pip-tools:$HOME/.cache/pip-tools" \
-v /var/run/docker.sock:/var/run/docker.sock \
-u $(id -u) \
--group-add "$DOCKER_GROUP_ID" \
"$IMAGE_NAME" /bin/bash
