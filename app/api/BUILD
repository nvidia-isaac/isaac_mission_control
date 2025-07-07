# Copyright (c) 2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

load("@rules_python//python:defs.bzl", "py_library")
load("@python_third_party//:requirements.bzl", "requirement")

py_library(
    name = "api",
    srcs = [
        "endpoints/mission_control_api.py",
        "endpoints/sap_api.py",
        "clients/base_api_client.py",
        "clients/cuopt_client.py",
        "clients/cuopt_service_client.py",
        "clients/esp_client.py",
        "clients/mas_client.py",
        "clients/metropolis_client.py",
        "clients/mission_control_client.py",
        "clients/mission_database_client.py",
        "clients/mission_dispatch_client.py",
        "clients/ota_file_service_client.py",
        "clients/waypoint_graph_generator_client.py",
        "clients/s3_client.py",
        "clients/sap_ewm_client.py",
    ],
    visibility = ["//visibility:public"],
    deps = [
        "//app/common",
        "//:cloud_common_objects",
        requirement("httpx"),
        requirement("numpy"),
        requirement("pydantic"),
        requirement("requests"),
        requirement("scipy"),
        requirement("boto3"),
    ],
) 