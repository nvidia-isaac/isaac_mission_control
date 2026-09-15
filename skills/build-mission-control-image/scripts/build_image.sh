#!/bin/bash
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

# Builds the Mission Control image and tags it under a repo:tag.
#
# Runs on the HOST (it drives docker). It ensures the dev container image is
# present/fresh via scripts/build_dev_image.sh, then runs the bazel bundle
# target inside that container to build an image tarball, then loads and retags it on the host.
#
# Usage:
#   ./build_image.sh                       # tag as mission-control-test:latest
#   ./build_image.sh my-repo/mc:v1.2.3     # tag as the given repo:tag

set -euo pipefail

# Resolve repo root: skills/build-mission-control-image/scripts/ -> repo root.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
ROOT="$( cd "${SCRIPT_DIR}/../../.." >/dev/null 2>&1 && pwd )"

IMAGE_NAME="isaac-mission-control-dev"
TARGET_TAG="${1:-mission-control-test:latest}"

# 1. Ensure the dev container image exists and is fresh.
echo "=== Ensuring dev container image (scripts/build_dev_image.sh) ==="
"${ROOT}/scripts/build_dev_image.sh"

# 2. Build the Mission Control image tarball via bazel inside the dev container.
#    The host loads the tarball afterward, so the container does not need
#    access to the host Docker socket.
echo "=== Building image tarball via bazel ==="
docker run --rm \
  --network bridge \
  --workdir "$ROOT" \
  -e "WORKSPACE=$ROOT" \
  -e "HOME=$HOME" \
  -e "USER=${USER:-bazel}" \
  -v "$ROOT:$ROOT" \
  -v "$HOME/.docker:$HOME/.docker:ro" \
  -v "$HOME/.cache/bazel:$HOME/.cache/bazel" \
  -v "$HOME/.cache/pip-tools:$HOME/.cache/pip-tools" \
  -u "$(id -u):$(id -g)" \
  "$IMAGE_NAME" \
  /bin/bash -lc "bazel build --output_groups=+tarball -- app/mission-control-img-bundle"

IMAGE_TARBALL="$ROOT/bazel-bin/app/mission-control-img-bundle/tarball.tar"
if [[ ! -f "$IMAGE_TARBALL" ]]; then
  echo "error: expected image tarball not found at $IMAGE_TARBALL" >&2
  exit 1
fi

echo "=== Loading bazel-image:latest from tarball ==="
docker load -i "$IMAGE_TARBALL"

# 3. Verify that the configured non-root user can read the Python launcher.
echo "=== Verifying non-root launcher access ==="
IMAGE_USER="$(docker image inspect bazel-image:latest --format '{{.Config.User}}')"
if [[ -z "$IMAGE_USER" || "$IMAGE_USER" == "0" || "$IMAGE_USER" == "0:0" || "$IMAGE_USER" == "root" ]]; then
  echo "error: expected a non-root image user, got '${IMAGE_USER:-<empty>}'" >&2
  exit 1
fi
docker run --rm --entrypoint /usr/local/bin/python3 bazel-image:latest \
  -c 'from pathlib import Path; Path("/app/oci_runfiles_launcher.py").read_bytes()'

# 4. Tag the loaded image (bazel-image:latest) to the requested repo:tag.
echo "=== Tagging bazel-image:latest -> $TARGET_TAG ==="
docker tag bazel-image:latest "$TARGET_TAG"

echo "=== Done. Tagged image as: $TARGET_TAG ==="
docker images "${TARGET_TAG%%:*}"
