---
name: build-mission-control-image
license: Apache-2.0
description: Build Mission Control images; reads Docker credentials from $HOME/.docker.
metadata:
  author: NVIDIA Isaac Team <info@nvidia.com>
  credential_access: Mounts $HOME/.docker read-only into the dev container for registry pulls.
---

# Build the Mission Control image

## Purpose

Build the Mission Control OCI image through the repository's Bazel bundle target
inside the developer container, load it into the local Docker daemon, and tag it
for later use. Prefer this skill over ad hoc `bazel` or `docker tag` commands
when the user asks to build, rebuild, bundle, or tag the Mission Control image.

## Prerequisites

- Run from a host with a reachable Docker daemon; `docker info` should work for
  the current user.
- This skill reads Docker credentials from `$HOME/.docker` and mounts that directory read-only into the dev container. Those credentials may be used for `nvcr.io` or other registry pulls required by the dev image or Bazel image dependencies.
- Expect `scripts/build_dev_image.sh` to build or refresh
  `isaac-mission-control-dev` before the Bazel image bundle runs.
- Use the repository root as the working directory unless the caller provides an
  absolute script path.

## Available Scripts

| Script | Purpose | Arguments |
| --- | --- | --- |
| `skills/build-mission-control-image/scripts/build_image.sh` | Ensure the dev container image exists, run `bazel build --output_groups=+tarball -- app/mission-control-img-bundle` inside it, load the generated tarball, and tag the result. | Optional single `repo:tag`; defaults to `mission-control-test:latest`. |

## Instructions

Use the bundled host-side script. It runs non-interactively, so an agent can call
it directly without entering `./scripts/run_dev.sh`.

When a `run_script()` helper is available, prefer it so the bundled script is the
single execution surface. When invoking through a shell from the repository
root, use the equivalent script path.

```python
run_script("skills/build-mission-control-image/scripts/build_image.sh")
run_script("skills/build-mission-control-image/scripts/build_image.sh", "my-repo/mc:v1.2.3")
```

When invoking through a shell from the repository root, use the equivalent
commands:

```bash
./skills/build-mission-control-image/scripts/build_image.sh
./skills/build-mission-control-image/scripts/build_image.sh my-repo/mc:v1.2.3
```

Pass the requested `repo:tag` as the only argument. Omit it when the user did
not ask for a specific tag; the script then tags the image as
`mission-control-test:latest`. See the Examples section below for invocation
patterns and expected tags.

## Verify Success

Treat the build as successful when the script output includes the Bazel tarball build, Docker load message, tag confirmation, and final image listing:

```
Loaded image: bazel-image:latest
=== Tagging bazel-image:latest -> <repo:tag> ===
=== Done. Tagged image as: <repo:tag> ===
IMAGE                  ID            ...
<repo>:<tag>           34c67bbf7102  ...
```

The script builds the `tarball` output group from the bundle's `oci_load` rule (`//app:mission-control-img-bundle`, defined in `bzl/python.bzl`), then loads that tarball on the host as `bazel-image:latest` and retags it to your `repo:tag`.

## Examples

Build with the default local test tag:

```bash
./skills/build-mission-control-image/scripts/build_image.sh
```

Expected final tag: `mission-control-test:latest`.

Build and tag for a specific registry path:

```bash
./skills/build-mission-control-image/scripts/build_image.sh my-repo/mc:v1.2.3
```

Expected final tag: `my-repo/mc:v1.2.3`.

Equivalent `run_script()` examples:

```python
run_script("skills/build-mission-control-image/scripts/build_image.sh")
run_script("skills/build-mission-control-image/scripts/build_image.sh", "my-repo/mc:v1.2.3")
```

## Limitations

- The script builds the local Mission Control image only; it does not push images to a registry.
- Docker credentials from `$HOME/.docker` are mounted read-only into the dev container when the build script runs.
- The build depends on the repository Bazel target `//app:mission-control-img-bundle`, its `tarball` output group, and the temporary `bazel-image:latest` tag.
- Build time and registry access depend on local Docker state, network access, and available registry credentials.

## Troubleshooting

- Error: Docker daemon unavailable. Cause: the current user cannot reach Docker. Solution: run `docker info` and fix daemon or group access before invoking the script.
- Error: registry pull is unauthorized. Cause: `$HOME/.docker` lacks valid credentials for the required registry, such as `nvcr.io`. Solution: authenticate to the registry, then rerun the script.
- Error: image pulls time out. Cause: slow registry or network access. Solution: export `PULLER_TIMEOUT=3000` as documented in `README.md`.
- Error: expected image tarball is missing. Cause: the Bazel `oci_load` tarball output path changed or the build failed before producing it. Solution: update `skills/build-mission-control-image/scripts/build_image.sh` to match the generated tarball path.
- Error: `docker tag bazel-image:latest` fails. Cause: the Bazel tarball loaded a different repo tag. Solution: update `skills/build-mission-control-image/scripts/build_image.sh` to match the `oci_load` repo tag.

## Notes

- If `docker load` prints a `Loaded image:` tag other than `bazel-image:latest`,
  the script's `docker tag` step will fail. That means `bzl/python.bzl` changed
  the `oci_load` repo_tag, and `skills/build-mission-control-image/scripts/build_image.sh` needs the same update.
- If image pulls time out during the build, `README.md` documents
  `export PULLER_TIMEOUT=3000`.
- `bazel-image:latest` is overwritten on each build; the `repo:tag` you pass is
  the stable name to push or run.
