# Copyright (c) 2022-2026, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

load("@python_third_party_linting//:requirements.bzl", "requirement")
load("@aspect_rules_py//py:defs.bzl", "py_image_layer")
load("@rules_oci//oci:defs.bzl", "oci_image", "oci_load")

# OCI base is @python (nvidia/distroless/python). Python on PATH for that image;
# keep in sync with the base image (see MODULE.bazel oci.pull name = "python").
_PY_OCI_BASE_PYTHON = "/usr/local/bin/python3"

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

    _layer = kwargs["name"] + "-image-layer"

    # Isolate setuptools into its own layer group so it can be omitted from the
    # image (see oci_image.tars below). setuptools is a build-time tool pulled
    # into the runtime closure only transitively (kratos-pycloudevents lists it
    # as a dependency) and is never imported at runtime. Dropping it also drops
    # the vulnerable copies of wheel and jaraco.context that setuptools vendors
    # under setuptools/_vendor. Custom layer_groups are matched before the
    # default "packages" group, so all other site-packages still ship normally.
    py_image_layer(
        name = _layer,
        binary = kwargs["name"],
        layer_groups = {
            "setuptools": "/site-packages/setuptools",
        },
    )

    # Do not use the py_binary bootstrap: it execs the hermetic interpreter from
    # runfiles. Run main.py with the distroless base Python and RUNFILES_DIR instead.
    # Omit py_image_layer's "interpreter" tar so the hermetic toolchain is not in the image.
    _pkg = native.package_name()
    _main = kwargs.get("main", kwargs["name"] + ".py")
    _runfiles_main = "_main/{}/{}".format(_pkg, _main) if _pkg else "_main/{}".format(_main)

    # Thin tar layer: shared launcher that prepends _main + all .../site-packages
    # to sys.path (what the rules_python bootstrap would do for PYTHONPATH).
    native.genrule(
        name = kwargs["name"] + "_oci_launcher_layer",
        srcs = ["//bzl:oci_runfiles_launcher.py"],
        outs = [kwargs["name"] + "_oci_launcher_layer.tar.gz"],
        cmd = (
            "mkdir -p $$(dirname $@)/oci_launch_staging/app && " +
            "cp $(location //bzl:oci_runfiles_launcher.py) $$(dirname $@)/oci_launch_staging/app/oci_runfiles_launcher.py && " +
            "tar -C $$(dirname $@)/oci_launch_staging -czf $@ ."
        )
    )

    # oci_image only accepts entrypoint as a list or a file label; emit a
    # newline-separated entrypoint (exec-form): base python, launcher, then main.
    native.genrule(
        name = kwargs["name"] + "_oci_entrypoint",
        outs = [kwargs["name"] + "_oci_entrypoint.txt"],
        cmd = (
            "printf '%s\\n%s\\n%s\\n' '{py}' '/app/oci_runfiles_launcher.py' " +
            "'/app/{name}.runfiles/{runfiles_main}' > $@"
        ).format(
            py = _PY_OCI_BASE_PYTHON,
            name = kwargs["name"],
            runfiles_main = _runfiles_main
        )
    )

    oci_image(
        name = image_kwargs["name"],
        # This is defined by an oci.pull() call in /MODULE.bazel
        base = "@python",
        entrypoint = kwargs["name"] + "_oci_entrypoint",
        env = {
            "RUNFILES_DIR": "/app/{}.runfiles".format(kwargs["name"])
        },
        # Note: ":" + _layer + "_setuptools" is intentionally omitted so the
        # build-time-only setuptools tree (and its vendored wheel/jaraco.context)
        # is not shipped in the runtime image.
        tars = [
            ":" + _layer + "_packages",
            ":" + _layer + "_default",
            ":" + kwargs["name"] + "_oci_launcher_layer"
        ]
    )

    oci_load(
        name = image_kwargs["name"] + "-bundle",
        image = image_kwargs["name"],
        repo_tags = ["bazel-image:latest"],
        visibility = ["//visibility:public"]
    )
