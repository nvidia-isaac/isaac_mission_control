# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

load("@python_third_party_linting//:requirements.bzl", "requirement")
load("@io_bazel_rules_docker//python3:image.bzl", "py3_image")
load("@io_bazel_rules_docker//container:container.bzl", "container_bundle", "container_push")

def py_type_test(name, srcs, deps):
    native.py_test(
        name = name,
        main = "@nvidia_isaac_mission_control//bzl:pytype.py",
        srcs = ["@nvidia_isaac_mission_control//bzl:pytype.py"] + srcs,
        deps = deps + [requirement("mypy")],
        args = ["$(location {})".format(src) for src in srcs],
        tags = ["lint"],
    )

def py_lint_test(name, srcs):
    native.py_test(
        name = name,
        main = "@nvidia_isaac_mission_control//bzl:pylint.py",
        srcs = ["@nvidia_isaac_mission_control//bzl:pylint.py"] + srcs,
        deps = [requirement("pylint")],
        data = ["@nvidia_isaac_mission_control//bzl:pylintrc"],
        args = ["--rcfile=$(location @nvidia_isaac_mission_control//bzl:pylintrc)"] +
               ["$(location {})".format(src) for src in srcs],
        tags = ["lint"],
    )

def mission_control_py_test(**kwargs):
    native.py_test(**kwargs)
    py_type_test(
        name = kwargs["name"] + "-type-test",
        srcs = kwargs.get("srcs", []),
        deps = kwargs.get("deps", []),
    )
    py_lint_test(
        name = kwargs["name"] + "-lint-test",
        srcs = kwargs.get("srcs", []),
    )

def mission_control_py_library(**kwargs):
    native.py_library(**kwargs)
    py_type_test(
        name = kwargs["name"] + "-type-test",
        srcs = kwargs.get("srcs", []),
        deps = kwargs.get("deps", []),
    )
    py_lint_test(
        name = kwargs["name"] + "-lint-test",
        srcs = kwargs.get("srcs", []),
    )

def mission_control_py_binary(**kwargs):
    native.py_binary(**kwargs)
    py_type_test(
        name = kwargs["name"] + "-type-test",
        srcs = kwargs.get("srcs", []),
        deps = kwargs.get("deps", []),
    )
    py_lint_test(
        name = kwargs["name"] + "-lint-test",
        srcs = kwargs.get("srcs", []),
    )

    image_kwargs = dict(**kwargs)
    if "main" not in image_kwargs:
        image_kwargs["main"] = image_kwargs["name"] + ".py"
    image_kwargs["name"] += "-img"

    py3_image(
        base = "@nvidia_isaac_mission_control//bzl:python_base",
        **image_kwargs
    )

    container_bundle(
        name = image_kwargs["name"] + "-bundle",
        images = {
            "bazel_image": image_kwargs["name"],
        },
        visibility = ["//visibility:public"],
    )
