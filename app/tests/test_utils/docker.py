# Copyright (c) 2022-2026, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import json
import os
import re
import socket
import subprocess
import time
import uuid

# Top level bash script to run as init process (PID 1) in each docker container to make sure that
# the docker container exits when the calling python process exits
SH_TEMPLATE = """
EXIT_CODE_FILE=$(mktemp)
cleanup() {
    EXIT_CODE=$(cat $EXIT_CODE_FILE)
    exit $EXIT_CODE
}
trap cleanup INT
( COMMAND ; echo $? > $EXIT_CODE_FILE ; kill -s INT $$ ) &
read _
"""

# How often to poll to see if a container is running
CONTAINER_CHECK_PERIOD = 0.1


def check_container_running(name: str) -> bool:
    result = subprocess.run(["docker", "container", "inspect", name],  # pylint: disable=subprocess-run-check
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    return result.returncode == 0


def wait_for_container(name: str, timeout: float = float("inf")):
    end_time = time.time() + timeout
    while time.time() < end_time:
        if check_container_running(name):
            return
        time.sleep(CONTAINER_CHECK_PERIOD)
    raise ValueError("Container did not start in time")


def get_container_ip(name: str) -> str:
    process = subprocess.run(["docker", "inspect", "-f",
                              "{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}", name],
                             stdout=subprocess.PIPE, check=True)
    ip_address = process.stdout.decode("utf-8").strip()
    if not ip_address or ip_address == "invalid IP": # Host network mode can sometimes return "invalid IP"
        if os.environ.get("DOCKER_HOST", "") != "":
            hostname = os.environ.get("DOCKER_HOST").split("//")[1].split(":")[0]
            try:
                return socket.gethostbyname(hostname)
            except socket.gaierror:
                # If hostname resolution fails, fall back to 127.0.0.1
                return "127.0.0.1"
        return "127.0.0.1"
    return ip_address


def _image_id_after_load(manifest: list) -> str:
    """
    Resolve the image ID to use after loading. Prefer the ID Docker assigned to
    the repo tag (the image we just loaded); fall back to the manifest config
    digest if the tag is not found. This avoids mismatches when the manifest
    digest and the image Docker reports differ (e.g. different paths, platform).
    """
    repotags = manifest[0].get("RepoTags") or []
    for tag in repotags:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.Id}}", tag],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.decode("utf-8").strip()
    # Fallback: use config digest from manifest
    return "sha256:" + manifest[0]["Config"].split("/")[-1]


def run_docker_target(bazel_target: str, args: list[str],
                      docker_args: list[str],
                      start_timeout: float = 120,
                      delay: int = 0,
                      name: str = None) -> tuple[subprocess.Popen, str, str]:
    # Get the path of the bazel image
    regex = r"//(.+):(.+)"
    match = re.match(regex, bazel_target)
    if not match:
        raise ValueError(
            f"bazel_target \"{bazel_target}\" does not match regex: \"{regex}\"")
    package, target = match.groups()
    bundle_script = f"{package}/{target}.sh"
    subprocess.run([bundle_script], stdout=subprocess.PIPE, check=True)
    bundle_manifest = f"{package}/{target}/manifest.json"
    with open(bundle_manifest, "r") as f:
        manifest = json.load(f)
    image_hash = _image_id_after_load(manifest)

    # Get the entrypoint command
    result = subprocess.run(["docker", "inspect", "-f", "{{.Config.Entrypoint}}", image_hash],
                            stdout=subprocess.PIPE, check=True).stdout.decode("utf-8")
    args = result[1:-2].split(" ") + args
    if delay != 0:
        args = ["sleep", str(delay), ";"] + args

    # Run a the container inside a special bash script that will exit if
    # the calling process dies, so the container will always exit
    if name is None:
        name = f"bazel-test-{str(uuid.uuid4())}"
    script = SH_TEMPLATE.replace("COMMAND", " ".join(args))
    docker_cmd = ["docker", "run", "-i", "--rm",
                  "--entrypoint", "sh", "--name", name]
    if docker_args:
        docker_cmd.extend(docker_args)
    docker_cmd.extend([image_hash, "-c", script])
    process = subprocess.Popen(docker_cmd, stdin=subprocess.PIPE)
    try:
        wait_for_container(name, timeout=start_timeout)
        address = get_container_ip(name).strip()
    except:
        process.kill()
        raise
    return process, address, name


def run_docker_target_shelless(bazel_target: str, args: list[str],
                            docker_args: list[str],
                            start_timeout: float = 120) -> tuple[str, str]:
    # Get the path of the bazel image
    regex = r"//(.+):(.+)"
    match = re.match(regex, bazel_target)
    if not match:
        raise ValueError(
            f"bazel_target \"{bazel_target}\" does not match regex: \"{regex}\"")
    package, target = match.groups()
    bundle_script = f"{package}/{target}.sh"

    # Run the bundle script to add the image to the docker daemon
    subprocess.run([bundle_script], stdout=subprocess.PIPE, check=True)

    bundle_manifest = f"{package}/{target}/manifest.json"
    with open(bundle_manifest, "r") as f:
        manifest = json.load(f)
    image_hash = _image_id_after_load(manifest)

    # Start the container
    name = f"bazel-test-{str(uuid.uuid4())}"
    docker_cmd = ["docker", "run", "-d", "--rm",
                  "--name", name]
    if docker_args:
        docker_cmd.extend(docker_args)
    docker_cmd.extend([image_hash])
    if args:
        docker_cmd.extend(args)
    # print(" ".join(docker_cmd), flush=True)
    try:
        start_container = subprocess.run(docker_cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to start container: {e}")
        print(f"Error: {e.stderr}")
        raise

    # Get the container ID from the output
    container_id = start_container.stdout.strip()
    wait_for_container(container_id, timeout=start_timeout)
    address = get_container_ip(container_id).strip()

    # Return the container ID and address
    return container_id, address

def kill_container(container_id):
    try:
        # Kill the Docker container
        subprocess.run(
            ["docker", "kill", container_id], check=False
        )
        # print(f"Killed container with ID: {container_id}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to kill container: {e}")

def create_docker_volume_from_dir(dir_path: str, volume_name: str):
    # Use a docker volume to store the config file for remote docker daemons
    helper_container_name = f"helper-{uuid.uuid4().hex[:8]}"
    if os.path.exists(dir_path):
        if os.path.isdir(dir_path):
            dir_path = dir_path + "/."
    else:
        raise Exception(f"Path {dir_path} does not exist")

    result = subprocess.run(["docker", "volume", "create", volume_name])
    if result.returncode != 0:
        raise Exception(f"Failed to create docker volume: {result.stderr}")
    result = subprocess.run(["docker", "create", "-v", f"{volume_name}:/data", "--name", helper_container_name, "busybox", "true"])
    if result.returncode != 0:
        raise Exception(f"Failed to create docker container: {result.stderr}")
    result = subprocess.run(["docker", "cp", dir_path, helper_container_name + ":/data"])
    if result.returncode != 0:
        raise Exception(f"Failed to copy config file to docker container: {result.stderr}")
    result = subprocess.run(["docker", "rm", helper_container_name])
    if result.returncode != 0:
        raise Exception(f"Failed to remove docker container: {result.stderr}")

def remove_docker_volume(volume_name: str):
    result = subprocess.run(["docker", "volume", "rm", volume_name])
    if result.returncode != 0:
        raise Exception(f"Failed to remove docker volume: {result.stderr}")