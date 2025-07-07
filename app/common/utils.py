# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import math

from pydantic import BaseModel, Field


class Point(BaseModel):
    """ 3D Point """
    x: float = Field(title="X coordinate of a point")
    y: float = Field(title="Y coordinate of a point")
    z: float = Field(title="Optional Z coordinate of a point", default=0.0)


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


def angle_between_points(p1: Point, p2: Point):
    """
    Calculate the angle between two points
    """
    delta_x = p2.x - p1.x
    delta_y = p2.y - p1.y
    ret_val = math.atan2(delta_y, delta_x)
    return ret_val
