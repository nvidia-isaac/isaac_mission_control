# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

load("@io_bazel_rules_docker//repositories:deps.bzl", container_deps = "deps")
load("@io_bazel_rules_docker//container:container.bzl", "container_pull")
load("@io_bazel_rules_docker//python3:image.bzl", _py3_image_repos = "repositories")
load("@python_third_party//:requirements.bzl", python_third_deps = "install_deps")
load("@python_third_party_linting//:requirements.bzl", python_third_linting_deps = "install_deps")
load("@io_bazel_rules_docker//contrib:dockerfile_build.bzl", "dockerfile_image")
load("@io_bazel_rules_docker//container:load.bzl", "container_load")

def mission_control_workspace():
    # Install python dependencies from pip
    python_third_deps()
    python_third_linting_deps()

    # Pull dependencies needed for docker containers
    container_deps()

    container_pull(
        name = "mosquitto_base",
        registry = "dockerhub.nvidia.com",
        repository = "eclipse-mosquitto",
        tag = "latest",
    )

    container_pull(
        name = "postgres_database_base",
        registry = "docker.io/library",
        repository = "postgres",
        tag = "14.5",
        digest = "sha256:db3825afa034c78d03e301c48c1e8ed581f70e4b1c0d9dd944e3639a9d4b8b75",
    )

    container_pull(
        name = "mission_simulator_base",
        registry = "nvcr.io/nvidia/isaac",
        repository = "mission-simulator",
        tag = "3.2.0",
    )

    container_pull(
        name = "mission_dispatch_base",
        registry = "nvcr.io/nvidia/isaac",
        repository = "mission-dispatch",
        tag = "3.2.0",
    )

    container_pull(
        name = "mission_database_base",
        registry = "nvcr.io/nvidia/isaac",
        repository = "mission-database",
        tag = "3.2.0",
    )

    container_pull(
        name = "waypoint_graph_generator_base",
        registry = "nvcr.io/nvidia/isaac",
        repository = "swagger",
        tag = "1.0.0",
    )

    container_pull(
        name = "ota_file_service_base",
        registry = "nvcr.io/nvidia/isaac",
        repository = "ota-file-service",
        tag = "2024.2.27_5a01351",
    )

    container_pull(
        name = "cuopt_base",
        registry = "nvidia",
        repository = "cuopt",
        tag = "25.5.0-cuda12.8-py312",
    )

    # Enable python3 based images
    _py3_image_repos()

    # Load dockerfile_image 
    dockerfile_image(
        name = "base_docker_image",
        dockerfile = "//docker:Dockerfile.base",
        visibility = ["//visibility:public"],
    )

    # Load the image tarball.
    container_load(
        name = "loaded_base_docker_image",
        file = "@base_docker_image//image:dockerfile_image.tar",
        visibility = ["//visibility:public"],
    )

