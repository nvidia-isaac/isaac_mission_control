# Copyright (c) 2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

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
        tracks_cleaned = tracks.dict()
        tracks_cleaned["timestamp"] = tracks.timestamp.isoformat(
            timespec="milliseconds").replace("+00:00", "Z")
        logging.debug(tracks_cleaned)
        result = self.make_request_with_logs(
            "post", tracks_endpoint,
            "Failed to send tracks to ESP", "Sent tracks to ESP",
            json={"tracks_collection": tracks_cleaned, "routes": routes})
        return result

    def send_amr_routes(self, routes: dict[str, RouteESP]):
        """Send tracks and routes"""
        amr_routes_endpoint = self._base_url + \
            str(self._endpoints["amr_routes"]["path"])
        for key in routes:
            routes[key] = routes[key].dict()  # type: ignore
        self.make_request_with_logs(
            "post", amr_routes_endpoint,
            "Failed to send amr routes to ESP", "Sent amr routes to ESP",
            json=routes)
