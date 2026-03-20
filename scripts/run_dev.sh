#!/bin/bash
# Copyright (c) 2022-2026, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

set -e

# Create bazel cache directory if it doesn't exist
if [ ! -d "$HOME/.cache/bazel" ]; then
  # Folder does not exist, so create it
  mkdir "$HOME/.cache/bazel"
fi

# Create pip-tools cache directory if it doesn't exist
if [ ! -d "$HOME/.cache/pip-tools" ]; then
  # Folder does not exist, so create it
  mkdir "$HOME/.cache/pip-tools"
fi

ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )"/.. >/dev/null 2>&1 && pwd )"
docker build --network host -t isaac-mission-control-dev "${ROOT}/docker" \
--build-arg docker_id="$(getent group docker | cut -d: -f3)"

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
--group-add $(getent group docker | cut -d: -f3) \
isaac-mission-control-dev /bin/bash
