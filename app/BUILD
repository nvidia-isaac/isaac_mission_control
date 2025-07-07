# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

load("//bzl:python.bzl", "mission_control_py_binary")
load("@python_third_party//:requirements.bzl", "requirement")

mission_control_py_binary(
    name = "mission-control",
    srcs = ["main.py"],
    main = "main.py",
    visibility = ["//visibility:public"],
    deps = [
        "//app/api",
        "//app/common",
        "//app/core",
        requirement("fastapi"),
        requirement("uvicorn"),
        requirement("pydantic"),
        requirement("httpx"),
        requirement("opentelemetry-api"),
        requirement("opentelemetry-sdk"),
        requirement("opentelemetry-instrumentation-fastapi"),
        requirement("opentelemetry-exporter-otlp-proto-grpc"),
        requirement("numpy"),
        requirement("scipy"),
        requirement("requests"),
    ],
    data = [
        "//app/config:map_dir",
    ]
)
