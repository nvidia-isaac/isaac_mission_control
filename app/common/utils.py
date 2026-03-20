# Copyright (c) 2022-2026, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import math
from pydantic.v1 import BaseModel, Field
from cloud_common.objects.common import ICSUsageError, Point2D


class Blockage(BaseModel):
    """Blockage used by ESP"""
    center: list[float] = Field(
        default=[0.0, 0.0], description="The X, Y location of the circular blockage in map")
    radius: float = Field(
        default=0.0, description="The size of the circular blockage")


class MissionCtrlError(Exception):
    """
    Base class for exceptions in mission control.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def __repr__(self):
        return f"{self.__class__.__name__}: {self.message}"

    def __str__(self):
        return self.message


def angle_between_points(p1: Point2D, p2: Point2D):
    """
    Calculate the angle between two points
    """
    delta_x = p2.x - p1.x
    delta_y = p2.y - p1.y
    ret_val = math.atan2(delta_y, delta_x)
    return ret_val

def cos_theta_between_three_points(p1: Point2D, p2: Point2D, p3: Point2D):
    """
    Calculate the angle between three points
    """
    v1 = (p2.x - p1.x, p2.y - p1.y)
    v2 = (p3.x - p2.x, p3.y - p2.y)
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    magnitude_v1 = math.sqrt(v1[0]**2 + v1[1]**2)
    magnitude_v2 = math.sqrt(v2[0]**2 + v2[1]**2)
    if magnitude_v1 == 0 or magnitude_v2 == 0:
        raise ICSUsageError("Zero vector in cos_theta_between_three_points")
    cos_theta = dot / (magnitude_v1 * magnitude_v2)
    return cos_theta
