# Copyright (c) 2022-2026, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import enum
import pydantic.v1 as pydantic
from typing import Optional
from cloud_common.objects.common import ICSUsageError, Point2D, Pose3D


class NVActionType(str, enum.Enum):
    """Instant-action type names used in Mission Control.

    The map-related values below (*downloadMap*, *enableMap*, *deleteMap*) are
    **official VDA 5050 actions** as specified in chapter 6.7 of the standard
    (release 2.1).
    A legacy alias `LOAD_MAP` is kept temporarily to avoid breaking older code
    that used a non-standard name.
    """

    DOWNLOAD_MAP = "downloadMap"
    ENABLE_MAP = "enableMap"
    DELETE_MAP = "deleteMap"

    # Legacy alias (deprecated)
    LOAD_MAP = "enableMap"
    PAUSE_ORDER = "pause_order"


class SolverType(str, enum.Enum):
    CPU_DIJKSTRA = "CPU_DIJKSTRA"
    NVIDIA_CUOPT = "NVIDIA_CUOPT"


class WarehouseOrderStatus(str, enum.Enum):
    """Warehouse order status options"""
    OPEN = ""  # Open orders
    CONFIRMED = "C"  # Confirmed orders
    CANCELLED = "A"  # Cancelled orders
    IN_PROGRESS = "D"  # In progress orders


class AssembledMission(pydantic.BaseModel):
    points: list[Point2D] = pydantic.Field(default_factory=list)
    actions: dict[str, list[int]] = pydantic.Field(default_factory=dict)

class Waypoint2D(Point2D):
    """
    Waypoint2D is a 2D point with an optional theta
    If exact is True, the robot will navigate to the exact pose.

    x: float = 0
    y: float = 0
    theta: Optional[float]
    exact: bool = False
    """
    theta: Optional[float] = None
    exact: bool = False

class MissionData(pydantic.BaseModel):
    """ Data """
    route: list[Point2D]
    start_location: Optional[Point2D] = None
    end_location: Optional[Waypoint2D] = None
    iterations: int = 1
    timeout: int = 3600
    solver: SolverType = SolverType.NVIDIA_CUOPT
    teleop: list[int] = pydantic.Field(
        default=[],
        description="The indexes of points where the robot needs to switch to teleop.")

    @pydantic.root_validator(pre=True)
    def _validate_mission_data(cls, values):
        if values.get("teleop"):
            if len(values["teleop"]) > len(values["route"]):
                raise ICSUsageError(
                    "The number of teleop action should be smaller than the number of points.")
            for idx in values["teleop"]:
                if idx >= len(values["route"]):
                    raise ICSUsageError(
                        "The index should be smaller than the number of points.")
                if idx < 0:
                    raise ICSUsageError(
                        "The index should not be negative.")
            values["teleop"] = sorted(values["teleop"])
        return values

    @property
    def exact_end_location(self):
        return self.end_location and self.end_location.exact

    def get_assembled_mission(self):
        """ Return an assembled list of nav actions """
        assembled_mission = AssembledMission()
        iterations = self.iterations
        if iterations <= 0:
            raise ValueError("Negative iterations not allowed")

        if iterations > 100:
            raise ValueError(">100 iterations is unsupported at this time")

        assembled_teleop: list[int] = []
        if self.teleop:
            # Append action indexes if the iterations is larger than 1.
            for i in range(self.iterations):
                assembled_teleop = assembled_teleop + \
                    [idx + len(self.route)*i for idx in self.teleop]

        if self.start_location:
            assembled_mission.points.append(self.start_location)
            if self.teleop:
                assembled_teleop = [i + 1 for i in assembled_teleop]

        assembled_mission.points.extend(self.route * iterations)

        if self.end_location:
            assembled_mission.points.append(self.end_location)

        if len(assembled_mission.points) < 1:
            raise ValueError("Not enough nav points for a mission")
        if self.teleop:
            assembled_mission.actions.update(
                {NVActionType.PAUSE_ORDER: assembled_teleop})
        return assembled_mission


class MissionDataExtend(MissionData):
    sub_mission_uuids: list[str] = []
    robots: list[str] = []
    docks: list[str] = []


class MissionType(enum.Enum):
    SIMPLE_NAVIGATION = "SIMPLE_NAVIGATION"
    CHARGING = "CHARGING"


class ReplanData(pydantic.BaseModel):
    replanning: dict[str, bool] = {}
    affected_robots: list[str] = []
    blockages: list[dict] = []


class RouteVisualizationData(pydantic.BaseModel):
    """Contains all data needed for route visualization"""
    waypoints: list[Point2D] = pydantic.Field(
        description="User-specified waypoints that define the mission's goals. "
                    "Drawn as colored dots (green start, red intermediate, blue end)."
    )
    route_path: list[Point2D] = pydantic.Field(
        description="Calculated path through the navigation graph. "
                    "Represents the actual path the robot would take, drawn as a continuous line."
    )
    metadata: dict = pydantic.Field(
        description="Additional information about the route (i.e. map_id and routing_solver used)."
    )


class PickPlaceData(pydantic.BaseModel):
    object_id: int
    class_id: str
    pos_x: float
    pos_y: float
    pos_z: float
    quat_x: float
    quat_y: float
    quat_z: float
    quat_w: float

class MultiObjectPickPlaceModes(str, enum.Enum):
    SINGLE_BIN = "SINGLE_BIN"
    MULTI_BIN = "MULTI_BIN"

class MultiObjectPickPlaceTargetPoses(pydantic.BaseModel):
    frame_id: str
    poses: list[Pose3D]

    @pydantic.validator("poses")
    def _validate_poses(cls, v):
        if len(v) == 0:
            raise ICSUsageError("poses must be a non-empty list")
        return v

class MultiObjectPickPlaceData(pydantic.BaseModel):
    """ Schema for a Multi Object Pick and Place mission"""
    mode: MultiObjectPickPlaceModes
    class_ids: list[str]
    target_poses: MultiObjectPickPlaceTargetPoses

    @pydantic.validator("class_ids")
    def _validate_class_ids(cls, v, values):
        if values["mode"] == MultiObjectPickPlaceModes.MULTI_BIN and len(v) == 0:
            raise ICSUsageError("Multi bin mode requires a non-empty class_ids")
        return v

    @pydantic.validator("target_poses")
    def _validate_target_poses(cls, v, values):
        if values["mode"] == MultiObjectPickPlaceModes.MULTI_BIN and \
            len(v.poses) != len(values["class_ids"]):
            raise ICSUsageError(
                "For multi bin mode, the number of target poses must be equal to the number of "
                "class_ids")
        if values["mode"] == MultiObjectPickPlaceModes.SINGLE_BIN and len(v.poses) != 1:
            raise ICSUsageError("Single bin mode requires exactly 1 target pose")
        return v
