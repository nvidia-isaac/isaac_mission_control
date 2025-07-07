# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

load("//bzl:python.bzl", "mission_control_py_library")
load("@io_bazel_rules_docker//container:container.bzl", "container_bundle", "container_image")

mission_control_py_library(
    name = "test_utils",
    srcs = [
        "__init__.py",
        "docker.py",
        "network.py",
    ],
    visibility = ["//visibility:public"],
)

container_image(
    name = "mosquitto-img",
    base = "@mosquitto_base//image",
    entrypoint = [
        "sh",
        "mosquitto.sh",
    ],
    files = [
        "mosquitto.sh",
    ],
)

container_bundle(
    name = "mosquitto-img-bundle",
    images = {
        "bazel-image": ":mosquitto-img",
    },
    visibility = ["//visibility:public"],
)

container_bundle(
    name = "postgres-database-img-bundle",
    images = {
        "bazel-image": "@postgres_database_base//image",
    },
    visibility = ["//visibility:public"],
)

container_bundle(
    name = "mission-simulator-img-bundle",
    images = {
        "bazel-image": "@mission_simulator_base//image",
    },
    visibility = ["//visibility:public"],
)

container_bundle(
    name = "mission-dispatch-img-bundle",
    images = {
        "bazel-image": "@mission_dispatch_base//image",
    },
    visibility = ["//visibility:public"],
)

container_bundle(
    name = "mission-database-img-bundle",
    images = {
        "bazel-image": "@mission_database_base//image",
    },
    visibility = ["//visibility:public"],
)

container_bundle(
    name = "waypoint-graph-generator-img-bundle",
    images = {
        "bazel-image": "@waypoint_graph_generator_base//image",
    },
    visibility = ["//visibility:public"],
)

container_bundle(
    name = "ota-file-service-img-bundle",
    images = {
        "bazel-image": "@ota_file_service_base//image",
    },
    visibility = ["//visibility:public"],
)

container_bundle(
    name = "cuopt-img-bundle",
    images = {
        "bazel-image": "@cuopt_base//image",
    },
    visibility = ["//visibility:public"],
)