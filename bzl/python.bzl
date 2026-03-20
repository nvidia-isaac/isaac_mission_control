# Copyright (c) 2022-2026, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

load("@python_third_party_linting//:requirements.bzl", "requirement")
load("@aspect_rules_py//py:defs.bzl", "py_binary", "py_image_layer", "py_library", "py_pytest_main")                                                           
load("@rules_oci//oci:defs.bzl", "oci_image", "oci_load")

def py_type_test(name, srcs, deps):
    native.py_test(
        name = name,
        main = "@nvidia_isaac_mission_control//bzl:pytype.py",
        srcs = ["@nvidia_isaac_mission_control//bzl:pytype.py"],
        data = srcs,
        deps = deps + [requirement("mypy")],
        args = ["$(location {})".format(src) for src in srcs],
        tags = ["lint"],
    )

def py_lint_test(name, srcs):
    native.py_test(
        name = name,
        main = "@nvidia_isaac_mission_control//bzl:pylint.py",
        srcs = ["@nvidia_isaac_mission_control//bzl:pylint.py"],
        data = srcs + ["@nvidia_isaac_mission_control//bzl:pylintrc"],
        deps = [requirement("pylint")],
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
    # Disable lint/type tests for now - causing issues with file references
    # py_type_test(
    #     name = kwargs["name"] + "-type-test",
    #     srcs = kwargs.get("srcs", []),
    #     deps = kwargs.get("deps", []),
    # )
    # py_lint_test(
    #     name = kwargs["name"] + "-lint-test",
    #     srcs = kwargs.get("srcs", []),
    # )

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

    py_image_layer(
        name = kwargs["name"] + "-image-layer",
        binary = kwargs["name"],
    )

    oci_image(
        name = image_kwargs["name"],
        # This is defined by an oci.pull() call in /MODULE.bazel
        base = "@python",
        entrypoint = ["/app/" + kwargs["name"]],
        tars = [kwargs["name"] + "-image-layer"],
    )

    oci_load(
        name = image_kwargs["name"] + "-bundle",
        image = image_kwargs["name"],
        repo_tags = ["bazel-image:latest"],
        visibility = ["//visibility:public"],
    )
