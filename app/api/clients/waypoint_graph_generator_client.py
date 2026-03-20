# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

from typing import Optional

import asyncio
import time
import requests
import numpy as np
from scipy.spatial.transform import Rotation as R
from httpx import HTTPError

from app.api.clients.base_api_client import BaseAPIClient
from app.core.mission_control_config import MissionControlConfig
from app.common.waypoint_graph import WaypointGraph
from cloud_common.objects.common import Pose2D


class WaypointGraphGeneratorClient(BaseAPIClient):
    """ Client for WayPoint Generator API """
    _endpoints = {
        "generate": {
            "path": "/v1/graph/generate",
        },
        "nearest_nodes": {
            "path": "/v1/graph/nearest_nodes",
        },
        "graph": {
            "path": "/v1/graph",
        },
        "health": {
            "path": "/v1/health",
        },
        "visualize": {
            "path": "/v1/graph/visualize",
        }
    }
    _timeout = 300

    async def request_new_graph(self):
        """ Request for a new graph from the API with retry logic for timeouts"""
        self._logger.info("Requesting new graph from API")
        map_config = MissionControlConfig.get_instance().get_map_config()
        
        metadata = map_config.metadata.copy()
        data = metadata.dict()
        self._logger.debug("WPG Data: %s", str(data))
        files = None
        if map_config.map_file or map_config.map_s3:
            files = map_config.get_map_file()
        
        self._logger.debug("Binary Files?: " + "Yes" if files is not None else "No")
        endpoint = self._base_url + str(self._endpoints["generate"]["path"])
        
        if map_config.map_uri:
            data['map_uri'] = map_config.map_uri
        
        # Use built-in retry logic from BaseAPIClient
        graph_data = await self.make_request_with_logs(
            "post", endpoint,
            "WPG service error",
            "Received Graph from WPG",
            data=data,
            files=files,
            suppress_msg=True,
            retry_safe=True,
        )

        return WaypointGraph(**graph_data, map_id=metadata.map_id)

    async def get_nearest_nodes(self, coordinates):
        """
        Get the nodes id corresponding to the nodes closest to the passed coordinates.
        Coordinates are expected in ROS world frame.
        """
        if not coordinates:
            return []

        self._logger.info("Getting nearest nodes")
        endpoint = self._base_url + str(self._endpoints["nearest_nodes"]["path"])

        if isinstance(coordinates[0], Pose2D):
            points = [{"x": node.x, "y": node.y} for node in coordinates]
        else:
            points = coordinates

        data = {"points": points}
        params = {"map_id": MissionControlConfig.get_instance().get_map_config().map_id()}
        
        self._logger.debug("Getting nearest node ids for coordinates: %s", str(data))
        result = await self.make_request_with_logs("post", endpoint, "WPG service error",
                                                   "Got list of locations", params=params,
                                                   json=data)
        return result

    def get_visualization(self, map_id: str):
        """
        Returns the image from visualization.
        """
        endpoint = self._base_url + str(self._endpoints["visualize"]["path"])
        params = {
            "map_id": map_id
        }
        result = requests.get(endpoint, params=params, stream=True, timeout=30)
        return result

    async def health(self, suppress_error_msg=False):
        """
        Return true if 200, else false
        """
        endpoint = self._base_url + str(self._endpoints["health"]["path"])
        try:
            await self.make_request_with_logs("get", endpoint, "WPG service error",
                                              "WPG is online", suppress_msg=suppress_error_msg)
        except HTTPError:
            return False
        return True

    async def poll_health(self, timeout=120, freq=1):
        self._logger.debug("Polling WPG Health")
        start_time = time.time()
        while time.time() - start_time < timeout:
            wpg_online = await self.health(suppress_error_msg=True)
            if wpg_online:
                self._logger.debug("WPG is reachable")
                return True
            await asyncio.sleep(1/freq)
        self._logger.error("WPG cannot be reached")
        return False
