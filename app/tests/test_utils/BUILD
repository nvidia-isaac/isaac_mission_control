# Copyright (c) 2022-2026, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

load("//bzl:python.bzl", "mission_control_py_library")
load("@rules_oci//oci:defs.bzl", "oci_image", "oci_load")

mission_control_py_library(
    name = "test_utils",
    srcs = [
        "__init__.py",
        "docker.py",
        "network.py",
    ],
    visibility = ["//visibility:public"],
)

oci_image(
    name = "mosquitto-img",
    base = "@mosquitto_base",
    entrypoint = [
        "sh",
        "/mosquitto.sh",
    ],
    tars = [":mosquitto-files-layer"],
)

# Create a tar layer for mosquitto files
genrule(
    name = "mosquitto-files-layer",
    srcs = ["mosquitto.sh"],
    outs = ["mosquitto-files.tar"],
    cmd = "tmpdir=$$(mktemp -d) && cp $(SRCS) $$tmpdir/ && tar -czf $@ -C $$tmpdir . && rm -rf $$tmpdir",
)

oci_load(
    name = "mosquitto-img-bundle",
    image = ":mosquitto-img",
    repo_tags = ["bazel/app/tests/test_utils/mosquitto:latest"],
    visibility = ["//visibility:public"],
)

oci_image(
    name = "postgres-database-img",
    base = "@postgres_database_base",
    visibility = ["//visibility:public"],
)

oci_load(
    name = "postgres-database-img-bundle",
    image = ":postgres-database-img",
    repo_tags = ["bazel/app/tests/test_utils/postgres-database:latest"],
    visibility = ["//visibility:public"],
)

oci_image(
    name = "mission-simulator-img",
    base = "@mission_simulator_base",
    visibility = ["//visibility:public"],
)
oci_load(
    name = "mission-simulator-img-bundle",
    image = ":mission-simulator-img",
    repo_tags = ["bazel/app/tests/test_utils/mission-simulator:latest"],
    visibility = ["//visibility:public"],
)

oci_image(
    name = "mission-dispatch-img",
    base = "@mission_dispatch_base",
    visibility = ["//visibility:public"],
)
oci_load(
    name = "mission-dispatch-img-bundle",
    image = ":mission-dispatch-img",
    repo_tags = ["bazel/app/tests/test_utils/mission-dispatch:latest"],
    visibility = ["//visibility:public"],
)

oci_image(
    name = "mission-database-img",
    base = "@mission_database_base",
    visibility = ["//visibility:public"],
)
oci_load(
    name = "mission-database-img-bundle",
    image = ":mission-database-img",
    repo_tags = ["bazel/app/tests/test_utils/mission-database:latest"],
    visibility = ["//visibility:public"],
)

oci_image(
    name = "waypoint-graph-generator-img",
    base = "@waypoint_graph_generator_base",
    visibility = ["//visibility:public"],
)
oci_load(
    name = "waypoint-graph-generator-img-bundle",
    image = ":waypoint-graph-generator-img",
    repo_tags = ["bazel/app/tests/test_utils/waypoint-graph-generator:latest"],
    visibility = ["//visibility:public"],
)

oci_image(
    name = "cuopt-img",
    base = "@cuopt_base",
    visibility = ["//visibility:public"],
)
oci_load(
    name = "cuopt-img-bundle",
    image = ":cuopt-img",
    repo_tags = ["bazel/app/tests/test_utils/cuopt:latest"],
    visibility = ["//visibility:public"],
)
