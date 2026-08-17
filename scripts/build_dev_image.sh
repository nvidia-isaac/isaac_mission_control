#!/bin/bash
# Copyright (c) 2026, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

# Builds the local developer container image used by run_dev.sh.
#
# Usage:
#   ./scripts/build_dev_image.sh           # build only if missing or stale
#   ./scripts/build_dev_image.sh --force   # always rebuild with --pull --no-cache

set -e

ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )"/.. >/dev/null 2>&1 && pwd )"
IMAGE_NAME="isaac-mission-control-dev"
MAX_IMAGE_AGE_SECONDS=28800
DOCKER_GROUP_ID="$(getent group docker | cut -d: -f3)"

FORCE=0
if [ "${1:-}" = "--force" ]; then
  FORCE=1
fi

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

build_dev_image() {
  local extra_args=("$@")
  docker build --network host "${extra_args[@]}" -t "$IMAGE_NAME" "${ROOT}/docker" \
    --build-arg docker_id="$DOCKER_GROUP_ID"
}

if [ "$FORCE" -eq 1 ]; then
  echo "Forcing rebuild of dev container image: $IMAGE_NAME"
  build_dev_image --pull --no-cache
elif ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
  echo "Building local dev container image: $IMAGE_NAME"
  build_dev_image
else
  created_at="$(docker image inspect "$IMAGE_NAME" --format '{{.Created}}')"
  created_epoch="$(date -d "$created_at" +%s)"
  now_epoch="$(date +%s)"
  age_seconds=$((now_epoch - created_epoch))

  age_days=$((age_seconds / 86400))
  age_hours=$(((age_seconds % 86400) / 3600))
  age_minutes=$(((age_seconds % 3600) / 60))

  if [ "$age_days" -gt 0 ]; then
    age_display="${age_days}d ${age_hours}h"
  elif [ "$age_hours" -gt 0 ]; then
    age_display="${age_hours}h ${age_minutes}m"
  else
    age_display="${age_minutes}m"
  fi

  if [ "$age_seconds" -ge "$MAX_IMAGE_AGE_SECONDS" ]; then
    echo "Cached dev container image is stale: $IMAGE_NAME (created $age_display ago); rebuilding without cache"
    build_dev_image --pull --no-cache
  else
    echo "Using cached dev container image: $IMAGE_NAME (created $age_display ago)"
  fi
fi
