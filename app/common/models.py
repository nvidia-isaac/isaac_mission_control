# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import enum
import pydantic
from typing import Optional
from app.common.utils import Point
from cloud_common.objects.common import ICSUsageError


class NVActionType(str, enum.Enum):
    LOAD_MAP = "load_map"
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
    points: list[Point] = []
    actions: dict[str, list[int]] = {}


class MissionData(pydantic.BaseModel):
    """ Data """
    route: list[Point]
    start_location: Optional[Point] = None
    end_location: Optional[Point] = None
    iterations: int = 1
    timeout: int = 3600
    solver: SolverType = SolverType.NVIDIA_CUOPT
    teleop: list[int] = pydantic.Field(
        default=[],
        description="The indexes of points where the robot needs to switch to teleop.")

    @pydantic.root_validator(pre=True)
    def _validate_teleop(cls, values):
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
    waypoints: list[Point] = pydantic.Field(
        description="User-specified waypoints that define the mission's goals. "
                    "Drawn as colored dots (green start, red intermediate, blue end)."
    )
    route_path: list[Point] = pydantic.Field(
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
