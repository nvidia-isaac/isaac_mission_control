exports_files([
    "defaults.yaml",
    "test_base.yaml",
    "test_overrides.yaml",
    "test_map_s3_metadata.yaml"
])

filegroup(
    name="etc_dir",
    data=glob(["etc/*"], allow_empty=True),
    tags=["nolint"],
    visibility=["//visibility:public"],
)

filegroup(
    name="map_dir",
    data=glob(["maps/*"]),
    visibility=["//visibility:public"],
)
