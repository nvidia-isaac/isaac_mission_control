# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import enum
import math
import json
import logging
import mimetypes
import os
from typing import Optional

import pydantic
import requests
import yaml
import numpy as np

from app.common.utils import MissionCtrlError
from app.api.clients.s3_client import S3Client


logger = logging.getLogger("Isaac Mission Control")

class MapMetadata(pydantic.BaseModel):
    """Map metadata required for WPG graph generation"""
    map_id: Optional[str] = pydantic.Field(None, description="Map ID to generate the graph from.")
    safety_distance: Optional[float] = pydantic.Field(
        0.45, description="Safety distance in meters to maintain from obstacles.", gt=0.0
    )
    resolution: Optional[float] = pydantic.Field(
        0.05, description="Map resolution in meters per pixel.", gt=0.0
    )
    occupancy_threshold: int = pydantic.Field(
        129, description="Threshold for determining occupied cells (0-255).", ge=0, le=255
    )
    x_offset: float = pydantic.Field(0.0, description="X offset of map origin in world coordinates (meters).")
    y_offset: float = pydantic.Field(0.0, description="Y offset of map origin in world coordinates (meters).")
    rotation: float = pydantic.Field(0.0, description="Rotation of map about Z axis in radians.")

class ROSMapMetadata(pydantic.BaseModel):
    """ROS Map metadata from yaml format"""
    image: str = pydantic.Field("default", description="Image file name")
    resolution: float = pydantic.Field(0.05, description="Resolution in meters per pixel")
    origin: list[float] = pydantic.Field([0.0, 0.0, 0.0], description="Origin of the map")
    negate: int = pydantic.Field(0, description="Negate")
    occupied_thresh: float = pydantic.Field(0.65, description="Threshold for occupied cells")
    free_thresh: float = pydantic.Field(0.196, description="Threshold for free cells")
    safety_distance: float = pydantic.Field(default=0.45, description="Safety distance in meters")

    @pydantic.validator('origin')
    def check_origin_length(cls, v):
        if len(v) != 3:
            raise ValueError('origin must have exactly 3 items')
        return v
    
    def get_scaled_occupied_thresh(self):
        return int(self.occupied_thresh * 255)

class DockPose(pydantic.BaseModel):
    """
        x, y, yaw is the pose of the physical dock.
        Routing uses the staging pose, which is the dock's pose
        shifted by the offset.
    """
    x: float = pydantic.Field(..., description="x")
    y: float = pydantic.Field(..., description="y")
    yaw: float = pydantic.Field(..., description="yaw")
    staging_offset: float = pydantic.Field(
        0.5, description="Offset used to calculate the staging pose.")

    def to_parameter_str(self):
        return str(self.x) + "," + str(self.y) + "," + str(self.yaw)

    def get_staging_pose(self):
        negative_yaw = self.yaw + math.pi
        delta_x = self.staging_offset * math.cos(negative_yaw)
        delta_y = self.staging_offset * math.sin(negative_yaw)

        x_staging = self.x + delta_x
        y_staging = self.y + delta_y
        return {"x": x_staging, "y": y_staging, "yaw": self.yaw}


class DockConfig(pydantic.BaseModel):
    dock_id: str = pydantic.Field(..., description="Dock ID")
    dock_type: str = pydantic.Field(..., description="Dock type")
    dock_pose: DockPose = pydantic.Field(..., description="Dock pose (x,y,yaw)")


class MapConfig(pydantic.BaseModel):
    """ Map Config """
    map_file: Optional[str] = pydantic.Field(None, alias="map_file")
    map_uri: Optional[str] = pydantic.Field(None, alias="map_uri")
    map_s3: Optional[str] = pydantic.Field(None, alias="map_s3")
    metadata_yaml: str = pydantic.Field("", alias="metadata_yaml")
    metadata: Optional[MapMetadata] = pydantic.Field(None, alias="metadata")
    map_file_loaded: Optional[dict] = pydantic.Field(None)
    docks: list[DockConfig] = pydantic.Field(default=[])
    push_map_on_startup: bool = pydantic.Field(default=True)
    save_route_visualization: bool = pydantic.Field(default=False)
    route_visualization_path: str = pydantic.Field(default="/tmp/config/routes/")

    def apply_metadata_yaml(self):
        logger.info("Metadata yaml: %s", self.metadata_yaml)
        try:
            if self.metadata_yaml:
                logger.info("Overriding metadata with metadata_yaml")
                if self.metadata_yaml.startswith("s3://"):
                    logger.info("Getting map metadata from S3")
                    s3_client = S3Client.get_instance()
                    s3_bucket, s3_key = self.metadata_yaml.split("/", 3)[2], self.metadata_yaml.split("/", 3)[3]
                    file_content, _ = s3_client.get_object(bucket_name=s3_bucket, object_key=s3_key)
                    ROS_metadata = ROSMapMetadata(**yaml.safe_load(file_content))
                elif os.path.exists(self.metadata_yaml):
                    logger.info("Getting map metadata from local file path")
                    with open(self.metadata_yaml, "r") as f:
                        ROS_metadata = ROSMapMetadata(**yaml.safe_load(f))
                else:
                    logger.info("Provided metadata_yaml is not a valid path")
                    return
                safety_distance_override = (self.metadata.safety_distance if self.metadata
                                            else ROS_metadata.safety_distance)
                overrides = {
                    "map_id": ROS_metadata.image,
                    "safety_distance": safety_distance_override,
                    "resolution": ROS_metadata.resolution,
                    "occupancy_threshold": ROS_metadata.get_scaled_occupied_thresh(),
                    "x_offset": ROS_metadata.origin[0],
                    "y_offset": ROS_metadata.origin[1],
                    "rotation": 0.0,
                }
                self.metadata = MapMetadata(**overrides)
        except Exception as e:  # pylint: disable=broad-except
            logger.error("Error applying metadata yaml: %s", e)

    @pydantic.root_validator(pre=True)
    def validate_one_of_map_sources(cls, values):
        if sum([bool(values.get("map_file")),
                bool(values.get("map_uri")),
                bool(values.get("map_s3"))]) != 1:
            raise ValueError(
                "One and only one of map_file or map_uri or map_s3 must be set")
        if not values.get("metadata") and not values.get("metadata_yaml"):
            raise ValueError(
                "Either metadata or metadata_yaml must be set")
        return values

    def get_map_contents(self):
        logger.debug("Getting map file contents")
        logger.debug(os.getcwd())
        try:
            if self.map_uri:
                curr_map = self.map_uri
                logger.info("Reading map file from: %s", curr_map)
                response = requests.get(curr_map, timeout=30)
                file_content = response.content
                content_type, _ = mimetypes.guess_type(
                    str(curr_map), strict=False)
                content_type = content_type or response.headers.get("content-type")
                logger.info("Map file type: %s", content_type)
                return {"content_type": content_type, "file_content": file_content}
            elif self.map_s3:
                try:
                    s3_client = S3Client.get_instance()
                    s3_path = str(self.map_s3)
                    s3_bucket, s3_key = s3_path.split("/", 3)[2], s3_path.split("/", 3)[3]
                    file_content, content_type = s3_client.get_object(bucket_name=s3_bucket, object_key=s3_key)
                    logger.debug("S3 Map file type: %s", content_type)
                    return {"content_type": content_type, "file_content": file_content}
                except Exception as e:
                    raise MissionCtrlError(f"Error getting map from S3: {e}") from e
            elif self.map_file:
                try:
                    with open(self.map_file, "rb") as image_file:
                        image_data = image_file.read()
                        content_type, _ = mimetypes.guess_type(self.map_file, strict=False)
                        return {"content_type": content_type, "file_content": image_data}
                except FileNotFoundError as exc:
                    raise MissionCtrlError(f"Cannot find map at {self.map_file}") from exc
                except IOError as exc:
                    raise MissionCtrlError(
                        f"An IO error ocurred when opening map at {self.map_file}") from exc
            else:
                raise ValueError("Need map_file or map_uri to get map contents")
        except requests.exceptions.HTTPError as exc:
            raise MissionCtrlError(
                f"Could not load Map with err: {exc}") from exc

    def get_map_file(self) -> dict:
        if self.map_file_loaded is None:
            logger.debug("Get map file with url...")
            file = self.get_map_contents()
            curr_map = self.map_file or self.map_uri or self.map_s3
            filename = os.path.basename(curr_map) if curr_map else ""
            self.map_file_loaded = {
                "map_file": (
                    filename,
                    file["file_content"],
                    file["content_type"]
                )
            }
        return self.map_file_loaded

    def to_wpg_data(self) -> dict:
        data = {}
        if self.map_file:
            data.update({"map_file": self.map_file})
        elif self.map_uri:
            data.update({"map_uri": self.map_uri})
        if self.metadata and (self.map_file or self.map_uri or self.map_s3):
            data.update(self.metadata)
        return data

    def map_id(self) -> str:
        if (self.map_file or self.map_uri or self.map_s3) and self.metadata:
            return self.metadata.map_id
        logger.warning("Map is not provided.")
        return ""

    def update_map_uri(self, map_uri: str):
        self.map_uri = map_uri


class Constants(pydantic.BaseModel):
    """ Configurable constants """
    MIN_BATTERY: float = pydantic.Field(
        20.0, description="Minimum battery for mission execution.")
    BATTERY_ALERT_URL: str = pydantic.Field(
        "", description="URL to notify when battery is low"
    )
    STARTUP_TIMEOUT: int = pydantic.Field(
        1200, description="Timeout for startup of Mission Control")
    PROXIMITY_THRESHOLD: float = pydantic.Field(
        2.0, description="A threshold in meter that defines when a person is considered \
            near a node.")
    SCALING_FACTOR: float = pydantic.Field(
        1.0, description="It determines how much the edge weight changes by scaling the \
            influence factor.")
    SEND_TELEMETRY: bool = pydantic.Field(
        False, description="Enable submission of telemetry")


class KafkaConfig(pydantic.BaseModel):
    """ Kafka config """
    push_to_kafka: bool = pydantic.Field(
        False, description="Enable kafka")
    kafka_server: str = pydantic.Field(
        "localhost:9092", description="Kafka server")
    kafka_producer_topic: str = pydantic.Field(
        "mdx-amr", description="Kafka producer topic")
    kafka_place: str = pydantic.Field(
        "city=Santa Clara/building=NVIDIA Voyager/room=Visitor Lobby")
    kafka_consumer_topic: str = pydantic.Field(
        "test-topic", description="Kafka consumer topic")
    kafka_consumer_frequency_seconds: float = pydantic.Field(
        0.5, description="Seconds in between each poll from kafka consumer")


class SapConfig(pydantic.BaseModel):
    """SAP EWM configuration"""
    enable_sap_ewm: bool = pydantic.Field(
        False, description="Enable SAP EWM background task system")
    base_url: str = pydantic.Field(
        "https://api/sap",
        description="Base URL for SAP EWM API")
    warehouse: str = pydantic.Field(
        "",
        description="Warehouse identifier for SAP EWM")
    username: str = pydantic.Field(
        "",
        description="Username for SAP EWM API authentication")
    password: str = pydantic.Field(
        "",
        description="Password for SAP EWM API authentication")
    max_orders_to_process: int = pydantic.Field(
        1,
        description="Maximum number of orders to process (0 = unlimited)")


class MissionControlConfig:
    """
        Configuration for the full project.
        Loads the configuration passed from the CLI
        as well as provides getters for service specific configuration
    """
    _instance = None

    @staticmethod
    def get_instance():
        """ Static access method. """
        if not MissionControlConfig._instance:
            raise MissionCtrlError("Mission control has not been created!")
        return MissionControlConfig._instance

    def __init__(self, config_file: str, config_overrides=None):
        """ Loads the config file """
        self._config_file = config_file
        logger.info("Reading configuration from %s...", self._config_file)
        logger.info("Config file: %s", config_file)
        with open(self._config_file, "r", encoding="utf-8") as configyaml:
            yaml_config = yaml.safe_load(configyaml)
            self._config = yaml_config
        
        # Apply overrides if provided
        if config_overrides:
            logger.info("Applying configuration overrides: %s", config_overrides)
            self._merge_overrides(self._config, config_overrides)
            logger.info("Config after overrides applied: %s", self._config)
        
        self._map_config = MapConfig(**self._config["map"])
        # Log the map configuration after initialization
        logger.info("Map configuration initialized: docks=%s", self._map_config.docks)
        if "constants" in self._config:
            self._constants = Constants(**self._config["constants"])
        else:
            self._constants = Constants()  # type: ignore
        if "kafka" in self._config:
            self._kafka_config = KafkaConfig(**self._config["kafka"])
        else:
            self._kafka_config = KafkaConfig()  # type: ignore
        if "sap" in self._config:
            self._sap_config = SapConfig(**self._config["sap"])
        else:
            self._sap_config = SapConfig()  # type: ignore
        MissionControlConfig._instance = self

    def _merge_overrides(self, base_config, overrides):
        """Recursively merge overrides into base config.
        
        Args:
            base_config: Base configuration dictionary
            overrides: Overrides dictionary
        """
        for key, value in overrides.items():
            if isinstance(value, dict) and key in base_config and isinstance(base_config[key], dict):
                self._merge_overrides(base_config[key], value)
            else:
                base_config[key] = value

    def get_wpg_config(self) -> dict:
        """ Returns a dict with the configuration for the WPG service """
        return self._config["services"]["waypoint_graph"]

    def get_ota_config(self) -> dict:
        """ Returns a dict with the configuration for the OTA service """
        if "ota" in self._config["services"]:
            return self._config["services"]["ota"]
        return {}

    def get_cuopt_config(self) -> dict:
        """ Returns a dict with the configuration for the cuOpt service """
        cuopt_config = self._config["services"]["cuopt"]
        logger.info("Mission Control configured to use self-hosted cuOpt")

        return cuopt_config

    def get_mission_dispatch_config(self) -> dict:
        """ Returns a dict with the configuration for the Mission Dispatch service """
        return self._config["services"]["mission_dispatch"]

    def get_mission_database_config(self) -> dict:
        """ Returns a dict with the configuration for the Mission Database service """
        return self._config["services"]["mission_database"]

    def get_robots_config(self) -> list:
        """ Returns a list of configurations for each robot as loaded from file """
        return self._config["robots"]

    def get_waypoint_config(self) -> dict:
        """ Returns a list of configurations for wpg class as loaded from file """
        return self._config.get("waypoint", {})

    def get_map_config(self) -> MapConfig:
        return self._map_config

    def get_metropolis_config(self) -> Optional[dict]:
        """ Returns metropolis config """
        if "metropolis" in self._config["services"]:
            return self._config["services"]["metropolis"]
        else:
            return None

    def get_esp_config(self) -> Optional[dict]:
        """ Returns ESP config """
        if "esp" in self._config["services"]:
            return self._config["services"]["esp"]
        else:
            return None

    def get_mas_config(self) -> Optional[dict]:
        """ Returns MAS config """
        if "mas" in self._config["services"]:
            return self._config["services"]["mas"]
        else:
            return None
        
    def get_s3_config(self) -> Optional[dict]:
        """ Returns S3 config """
        s3_config = {
            "AWS_ACCESS_KEY_ID": "",
            "AWS_SECRET_ACCESS_KEY": "",
            "AWS_REGION": "",
            "AWS_ENDPOINT_URL": ""
        }
        if "s3" in self._config:
            logger.debug("Getting S3 config from config file")
            s3_config["AWS_ACCESS_KEY_ID"] = self._config["s3"].get("AWS_ACCESS_KEY_ID", "")
            s3_config["AWS_SECRET_ACCESS_KEY"] = self._config["s3"].get("AWS_SECRET_ACCESS_KEY", "")
            s3_config["AWS_REGION"] = self._config["s3"].get("AWS_REGION", "")
            s3_config["AWS_ENDPOINT_URL"] = self._config["s3"].get("AWS_ENDPOINT_URL", "")
        if all(not v for v in s3_config.values()):
            logger.debug("Getting S3 config from environment variables")
            s3_config["AWS_ACCESS_KEY_ID"] = os.environ.get("AWS_ACCESS_KEY_ID", s3_config["AWS_ACCESS_KEY_ID"])
            s3_config["AWS_SECRET_ACCESS_KEY"] = os.environ.get("AWS_SECRET_ACCESS_KEY", s3_config["AWS_SECRET_ACCESS_KEY"])
            s3_config["AWS_REGION"] = os.environ.get("AWS_REGION", s3_config["AWS_REGION"])
            s3_config["AWS_ENDPOINT_URL"] = os.environ.get("AWS_ENDPOINT_URL", s3_config["AWS_ENDPOINT_URL"])
        if not s3_config["AWS_ACCESS_KEY_ID"] or not s3_config["AWS_SECRET_ACCESS_KEY"]:
            logger.warning("S3 AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY not provided")
        return s3_config

    def get_metrics_config(self) -> dict:
        """ Pull metrics from env, then config, enable if provided """

        ssa_client_id = os.environ.get("TELEMETRY_ID", "")
        if ssa_client_id:
            self._config["telemetry"]["TELEMETRY_ID"] = ssa_client_id
        ssa_client_id = self._config["telemetry"]["TELEMETRY_ID"]

        ssa_client_secret = os.environ.get("TELEMETRY_SECRET", "")
        if ssa_client_secret:
            self._config["telemetry"]["TELEMETRY_SECRET"] = ssa_client_secret
        ssa_client_secret = self._config["telemetry"]["TELEMETRY_SECRET"]

        if self._config["telemetry"]["TELEMETRY_ENV"]:
            if self._config["telemetry"]["TELEMETRY_ENV"] not in ["DEV", "TEST", "PROD"]:
                raise MissionCtrlError(
                    "Metrics Env must be in DEV/TEST/PROD: " +
                    self._config["telemetry"]["TELEMETRY_ENV"])

        if (not ssa_client_secret) or (not ssa_client_id):
            logger.info("Telemetry auth not provided, disabling")
            self._config["telemetry"]["TELEMETRY_ENABLED"] = False
        return self._config["telemetry"]

    def get_kafka_config(self) -> KafkaConfig:
        return self._kafka_config

    def get_sap_config(self) -> SapConfig:
        """Returns SAP configuration"""
        return self._sap_config

    @property
    def constants(self) -> Constants:
        return self._constants

def get_config() -> MissionControlConfig:
    """Get the MissionControlConfig instance."""
    return MissionControlConfig.get_instance()
