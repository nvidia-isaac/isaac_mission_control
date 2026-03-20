"""
SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

SPDX-License-Identifier: Apache-2.0

API client for Mission Control MCP

Handles communication with the Mission Control REST API to manage robots,
submit missions, and visualize routes.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

OP_DEFAULT = "default"
OP_HEALTH_CHECK = "health_check"
OP_SUBMIT_NAVIGATION = "submit_navigation_mission"
OP_SUBMIT_CHARGING = "submit_charging_mission"
OP_SUBMIT_UNDOCK = "submit_undock_mission"


class MissionControlClientError(Exception):
    """Base exception for Mission Control MCP client errors."""


class MissionControlConnectionError(MissionControlClientError):
    """Raised when Mission Control cannot be reached."""


class MissionControlTimeoutError(MissionControlClientError):
    """Raised when Mission Control requests time out."""


class MissionControlHttpError(MissionControlClientError):
    """Raised when Mission Control responds with an HTTP error."""


class MissionControlResponseParseError(MissionControlClientError):
    """Raised when Mission Control returns malformed content."""


class MissionControlClient:
    """Client for interacting with Mission Control API"""

    def __init__(
        self,
        base_url: str = "http://localhost:8050",
        request_timeouts: Optional[Dict[str, float]] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_prefix = "/api/v1"
        self.request_timeouts: Dict[str, float] = {
            OP_DEFAULT: 30.0,
            OP_HEALTH_CHECK: 5.0,
            OP_SUBMIT_NAVIGATION: 45.0,
            OP_SUBMIT_CHARGING: 20.0,
            OP_SUBMIT_UNDOCK: 20.0,
        }
        if request_timeouts:
            self.request_timeouts.update(request_timeouts)

    def _resolve_timeout(self, operation: str, timeout: Optional[float] = None) -> float:
        """Resolve request timeout by explicit override or operation type."""
        if timeout is not None:
            return timeout
        return self.request_timeouts.get(operation, self.request_timeouts[OP_DEFAULT])

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        use_api_prefix: bool = True,
        timeout: Optional[float] = None,
        operation: str = "default",
    ) -> Any:
        """Make a request to the API with error handling"""
        prefix = self.api_prefix if use_api_prefix else ""
        url = f"{self.base_url}{prefix}/{endpoint}"
        request_timeout = self._resolve_timeout(operation, timeout)
        try:
            if method.lower() == "get":
                response = requests.get(url, params=params, timeout=request_timeout)
            elif method.lower() == "post":
                response = requests.post(
                    url, params=params, json=json_data, timeout=request_timeout
                )
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()

            # Handle different content types
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                return response.json()
            if "image/" in content_type:
                return response.content
            return response.text

        except requests.exceptions.ConnectionError as e:
            raise MissionControlConnectionError(
                f"Cannot connect to Mission Control at {self.base_url}. Is the service running?"
            ) from e
        except requests.exceptions.Timeout as e:
            raise MissionControlTimeoutError(
                f"Timeout connecting to Mission Control at {self.base_url}"
            ) from e
        except requests.exceptions.HTTPError as e:
            raise MissionControlHttpError(
                f"HTTP error {response.status_code}: {response.text}"
            ) from e
        except json.JSONDecodeError as e:
            raise MissionControlResponseParseError(
                "Invalid JSON response from Mission Control API"
            ) from e

    def health_check(self) -> Dict:
        """Check if the Mission Control API is accessible"""
        try:
            response = self._make_request(
                "get",
                "health",
                operation=OP_HEALTH_CHECK,
            )
            return {"status": "healthy", "api_accessible": True, "response": response}
        except MissionControlClientError as e:
            return {"status": "unhealthy", "api_accessible": False, "error": str(e)}

    def submit_navigation_mission(
        self,
        route: List[Dict],
        solver: str = "NVIDIA_CUOPT",
        timeout: int = 3600,
        iterations: int = 1,
        mission_id: Optional[str] = None,
        robot_name: Optional[str] = None,
    ) -> Dict:
        """Submit a navigation mission to Mission Control"""
        mission_data = {
            "route": route,
            "solver": solver,
            "timeout": timeout,
            "iterations": iterations,
        }

        params = {}
        if mission_id:
            params["mission_id"] = mission_id
        if robot_name:
            params["mandatory_robot_name"] = robot_name

        return self._make_request(
            "post",
            "mission/submit_mission",
            params=params if params else None,
            json_data=mission_data,
            operation=OP_SUBMIT_NAVIGATION,
        )

    def submit_charging_mission(self, robot_name: str, dock_id: Optional[str] = None) -> Dict:
        """Submit a charging mission for a specific robot"""
        params = {"robot_name": robot_name}
        if dock_id:
            params["dock_id"] = dock_id

        return self._make_request(
            "post",
            "mission/charging",
            params=params,
            operation=OP_SUBMIT_CHARGING,
        )

    def submit_undock_mission(self, robot_name: str) -> Dict:
        """Submit an undocking mission for a robot"""
        params = {"robot_name": robot_name}
        return self._make_request(
            "post",
            "mission/undock",
            params=params,
            operation=OP_SUBMIT_UNDOCK,
        )

    def get_available_objects(self, robot_name: str) -> List[Dict]:
        """Get available objects detected by a robot's camera"""
        params = {"robot_name": robot_name}
        return self._make_request("get", "mission/get_available_objects", params=params)

    def get_available_apriltags(self, robot_name: str) -> List[Dict]:
        """Get available AprilTags detected by a robot's camera"""
        params = {"robot_name": robot_name}
        return self._make_request("get", "mission/get_available_apriltags", params=params)

    def visualize_route(self, route: List[Dict], solver: str = "NVIDIA_CUOPT") -> bytes:
        """Get a visualization of a route without submitting a mission"""
        mission_data = {"route": route, "solver": solver}
        return self._make_request("post", "visualize_route", json_data=mission_data)

    def submit_objective(self, objective: Dict) -> str:
        """Submit an objective (behavior tree) to Mission Control"""
        return self._make_request("post", "objective/submit_objective", json_data=objective)

    def cancel_objective(self, objective_name: str) -> None:
        """Cancel a running objective"""
        params = {"objective_name": objective_name}
        return self._make_request("post", "objective/cancel_objective", params=params)

    def get_current_map(self) -> bytes:
        """Get the currently configured map file"""
        return self._make_request("get", "map")

    def get_map_metadata(self) -> Dict:
        """Get metadata for the currently configured map"""
        return self._make_request("get", "map/metadata")

    def list_maps(self) -> List[str]:
        """List IDs of maps previously uploaded to Mission Control"""
        return self._make_request("get", "map/list")

    def upload_map(
        self,
        map_id: str,
        image_path: str,
        metadata_yaml_path: Optional[str] = None,
    ) -> Dict:
        """Upload a map image and optional metadata to Mission Control"""
        url = f"{self.base_url}{self.api_prefix}/map/upload"

        with open(image_path, "rb") as img_file:
            files = {"map_image": img_file}
            data = {"map_id": map_id}

            if metadata_yaml_path:
                with open(metadata_yaml_path, "rb") as yaml_file:
                    files["metadata_yaml"] = yaml_file
                    response = requests.post(
                        url,
                        data=data,
                        files=files,
                    )
            else:
                response = requests.post(
                    url,
                    data=data,
                    files=files,
                )

        response.raise_for_status()
        return response.json()

    def select_map(self, map_id: str) -> Dict:
        """Activate an uploaded map in Mission Control"""
        return self._make_request("post", f"map/select/{map_id}")

    def update_robot_map(self, robot_name: str, map_id: str) -> Dict:
        """Download and enable a map on a specific robot"""
        return self._make_request("post", f"map/update_robot/{robot_name}/{map_id}")

    def submit_pick_and_place(
        self,
        robot_name: str,
        object_id: int,
        class_id: str,
        pos_x: float,
        pos_y: float,
        pos_z: float,
        quat_x: float,
        quat_y: float,
        quat_z: float,
        quat_w: float,
    ) -> Dict:
        """Submit a pick and place mission"""
        params = {"robot_name": robot_name}
        pick_place_data = {
            "object_id": object_id,
            "class_id": class_id,
            "pos_x": pos_x,
            "pos_y": pos_y,
            "pos_z": pos_z,
            "quat_x": quat_x,
            "quat_y": quat_y,
            "quat_z": quat_z,
            "quat_w": quat_w,
        }
        return self._make_request(
            "post",
            "mission/pick_and_place",
            params=params,
            json_data=pick_place_data,
        )

