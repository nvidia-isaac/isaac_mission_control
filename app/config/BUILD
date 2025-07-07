exports_files([
    "defaults.yaml",
    "test_base.yaml",
    "test_overrides.yaml"
])

filegroup(
    name="etc_dir",
    data=glob(["etc/*"]),
    tags=["nolint"],
    visibility=["//visibility:public"],
)

filegroup(
    name="map_dir",
    data=glob(["maps/*"]),
    visibility=["//visibility:public"],
)
