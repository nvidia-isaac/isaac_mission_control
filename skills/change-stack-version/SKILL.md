---
name: change-stack-version
license: Apache-2.0
description: Change the image (registry path or tag) of any Mission Control stack service — mission-control, mission-dispatch, mission-database, mission-simulator, mosquitto, postgres, wpg, cuopt, ota, esp, mas. Updates docker-compose/images.conf via skills/change-stack-version/scripts/set_image.py.
metadata:
  author: NVIDIA Isaac Team <info@nvidia.com>
  version: 1.0.0
  permissions:
    file_read:
      - docker-compose/images.conf
    file_write:
      - docker-compose/images.conf
    execute:
      - skills/change-stack-version/scripts/preflight.sh
      - skills/change-stack-version/scripts/set_image.py
---


# Change stack version

Use this when the user wants to change the compose image for one or more services — for example "change the mission-control compose image tag to 4.6.0", "pin mission-dispatch to a staging tag", or "bump cuopt". This skill only edits the image configuration; it does not start or restart the stack.

**Do not edit `docker-compose/images.conf` by hand.** Invoke `skills/change-stack-version/scripts/set_image.py` instead. The script is the source of truth for which `*_IMAGE` variable each service maps to and handles tag-only swaps without disturbing the registry path.

## Prerequisites

Before changing an image, run the preflight with the same operation arguments
you will pass to `set_image.py`:

```bash
bash skills/change-stack-version/scripts/preflight.sh \
  --service mission-control --tag 5.0.0
```

The preflight is read-only. It checks that `python3` and the shipped script are
available, verifies that the destination file is writable (or can be created),
and exercises the actual `set_image.py` code path with `--dry-run`. It exits
non-zero and names the problem if the selected service is absent from the
resolved `images.conf`, a tag-only swap cannot be made, or another prerequisite
is missing.

Pass `--images-file` to both commands when overriding the target file. For
multiple services, preflight each service separately. A successful preflight
validates the exact operation at that moment; use the same arguments for the
write.

## Inputs to collect

1. **Which service(s).** Valid values: `mission-control`, `mission-dispatch`, `mission-database`, `mission-simulator`, `mosquitto`, `postgres`, `wpg` (alias `swagger`), `cuopt`, `ota`, `esp`, `mas`.
2. **New value.** Either:
   - A full image ref (`nvcr.io/nvidia/isaac/mission-control:5.0.0`) → pass as `--image`.
   - Only a tag (`4.6.0`, `latest`, `25.10.0-cuda12.8-py3.12`) → pass as `--tag`. The script keeps the existing registry path and replaces only the substring after the final `:`.

If the user is vague ("use the new mission-control"), ask which tag — don't guess.

## How to invoke

Reads `docker-compose/images.conf` from `$MC_WORKSPACE` (default workspace: `./skills-workspace` in the caller's cwd) if the user has edited it there, else from this skill's shipped `resources/`. Writes the edited `images.conf` to `$MC_WORKSPACE`. Override the target file with `--images-file` if needed.

**This skill never reads or writes the compose credentials file.** Image references live in their own `images.conf` so that swapping a tag does not mean rewriting the file that holds the MQTT and postgres secrets. `bring-up-cloud-stack` sources the credentials file first and `images.conf` second, so an image set here wins over a stale duplicate left behind in an older workspace copy.

```bash
# Swap only the tag (preferred when the registry path is unchanged):
bash skills/change-stack-version/scripts/preflight.sh --service mission-control --tag 5.0.0
python3 skills/change-stack-version/scripts/set_image.py --service mission-control --tag 5.0.0

# Replace the entire image ref:
bash skills/change-stack-version/scripts/preflight.sh --service cuopt --image nvidia/cuopt:25.10.0-cuda12.8-py3.12
python3 skills/change-stack-version/scripts/set_image.py --service cuopt --image nvidia/cuopt:25.10.0-cuda12.8-py3.12

# Preview without writing:
bash skills/change-stack-version/scripts/preflight.sh --service mission-dispatch --tag 5.0.0
```

For multiple services, call the scripts once per service. The preflight output
is the dry-run preview, so stop after it if the user is exploring.

## After applying

Surface this once to the user — do not run it yourself unless asked, since it affects a live stack:

```bash
bash skills/bring-up-cloud-stack/scripts/up.sh --pull --recreate
```

`--pull` fetches the new tag (compose `up` won't re-pull a tag it already has cached); `--recreate` forces the affected container to actually swap to the new image.

`OTA_IMAGE`, `ESP_IMAGE`, and `MAS_IMAGE` are only used by certain bringup files; mention the relevant file when those are changed (`ESP_IMAGE` / `MAS_IMAGE` → `bringup_demo_services.yaml`; `OTA_IMAGE` is currently commented out in `bringup_services.yaml`).

## Out of scope

- The dev container image (`isaac-mission-control-dev`, built by `scripts/run_dev.sh`).
- Helm chart values under `helm-chart/`.
- Locally-built/Bazel-built images.
