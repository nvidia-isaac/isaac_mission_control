# SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
# Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
from typing import Optional
import logging

from pydantic import BaseModel, Field

from app.api.clients.base_api_client import BaseAPIClient


class PeopleTrack(BaseModel):
    """A person track from MTMC"""
    id: int = Field(description="Track ID")
    pos_x: float = Field(description="X coordinate of track position")
    pos_y: float = Field(description="Y coordinate of track position")


class MTMCTracks(BaseModel):
    """A list of tracks from MTMC"""
    timestamp: datetime = Field(description="Timestamp")
    tracks: list[PeopleTrack] = Field(description="Human tracks")


class WaypointESP(BaseModel):
    """A waypoint along an AMR route"""
    pos_x: float = Field(description="X coordinate of the waypoint")
    pos_y: float = Field(description="Y coordinate of the waypoint")


class RouteESP(BaseModel):
    """AMR route"""
    waypoints: list[WaypointESP] = Field(
        description="List of waypoints in the route")


class ESPServiceClient(BaseAPIClient):
    """ Client for ESP API """
    _endpoints = {
        "tracks": {
            "path": "/tracks",
        },
        "amr_routes": {
            "path": "/amr_routes",
        },
        "health": {
            "path": "/health",
        }
    }

    def send_tracks(self, tracks: MTMCTracks, routes: Optional[dict[str, RouteESP]] = None):
        """Send tracks and routes"""
        tracks_endpoint = self._base_url + \
            str(self._endpoints["tracks"]["path"])
        tracks_cleaned = tracks.model_dump(mode="json")
        tracks_cleaned["timestamp"] = tracks.timestamp.isoformat(
            timespec="milliseconds").replace("+00:00", "Z")
        routes_cleaned = None if routes is None else {
            key: route.model_dump(mode="json") for key, route in routes.items()
        }
        logging.debug(tracks_cleaned)
        result = self.make_request_with_logs(
            "post", tracks_endpoint,
            "Failed to send tracks to ESP", "Sent tracks to ESP",
            json={"tracks_collection": tracks_cleaned, "routes": routes_cleaned})
        return result

    def send_amr_routes(self, routes: dict[str, RouteESP]):
        """Send tracks and routes"""
        amr_routes_endpoint = self._base_url + \
            str(self._endpoints["amr_routes"]["path"])
        routes_cleaned = {
            key: route.model_dump(mode="json") for key, route in routes.items()
        }
        self.make_request_with_logs(
            "post", amr_routes_endpoint,
            "Failed to send amr routes to ESP", "Sent amr routes to ESP",
            json=routes_cleaned)
