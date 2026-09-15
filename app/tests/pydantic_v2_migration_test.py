# SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

"""Regression tests for Mission Control's Pydantic 2 migration."""

import datetime
import json
import unittest
import warnings
from typing import Annotated
from unittest.mock import AsyncMock

import pydantic
from fastapi import FastAPI, Query
from fastapi.testclient import TestClient
from pydantic.warnings import PydanticDeprecatedSince20

from app.api.clients.esp_client import ESPServiceClient, MTMCTracks, RouteESP
from app.api.clients.mas_client import MASServiceClient
from app.api.clients.metropolis_client import GetUniqueObjects, MetropolisClient
from app.api.clients.mission_control_client import MissionControlClient
from app.api.clients.mission_database_client import MissionDatabaseClient
from app.common.models import MultiObjectPickPlaceData, MultiObjectPickPlaceTargetPoses
from app.common.utils import Blockage
from app.core.mission_control_config import MapConfig
from cloud_common.objects.mission import (
    MissionSpecV1,
    MissionStateV1,
    MissionStatusV1,
    MissionObjectV1,
)
from cloud_common.objects.robot import RobotObjectV1, RobotQueryParamsV1


warnings.filterwarnings("error", category=PydanticDeprecatedSince20)


class TestPydanticV2Serialization(unittest.TestCase):
    """Verify that Pydantic 2 keeps the existing Mission Control wire format."""

    def test_mission_timeout_uses_numeric_seconds(self):
        deadline = datetime.datetime(2026, 9, 3, tzinfo=datetime.timezone.utc)
        mission = MissionSpecV1.model_validate({
            "robot": "robot_a",
            "mission_tree": [{"sequence": {}}],
            "timeout": datetime.timedelta(minutes=5),
            "deadline": deadline,
        })

        payload = mission.model_dump(mode="json")

        self.assertEqual(payload["timeout"], 300.0)
        self.assertIsInstance(payload["deadline"], str)
        self.assertEqual(json.loads(mission.model_dump_json()), payload)
        self.assertEqual(MissionSpecV1.model_validate(payload).timeout,
                         datetime.timedelta(minutes=5))
        timeout_schema = MissionSpecV1.model_json_schema(
            mode="serialization")["properties"]["timeout"]
        self.assertEqual(timeout_schema["type"], "number")

    def test_fastapi_response_keeps_numeric_mission_timeout(self):
        app = FastAPI()

        @app.get("/mission", response_model=MissionSpecV1)
        def get_mission():
            return MissionSpecV1.model_validate({
                "robot": "robot_a",
                "mission_tree": [{"sequence": {}}],
                "timeout": datetime.timedelta(minutes=5),
            })

        response = TestClient(app).get("/mission")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["timeout"], 300.0)

    def test_python_and_json_enum_serialization_are_distinct(self):
        status = MissionStatusV1.model_validate({"state": MissionStateV1.RUNNING})

        self.assertIs(status.model_dump()["state"], MissionStateV1.RUNNING)
        self.assertEqual(status.model_dump(mode="json")["state"], "RUNNING")

    def test_robot_names_are_parsed_as_query_parameters(self):
        app = FastAPI()

        @app.get("/robots")
        def get_robots(query: Annotated[RobotQueryParamsV1, Query()]):
            return query.model_dump(mode="json")

        client = TestClient(app)
        default_response = client.get("/robots")
        names_response = client.get("/robots?names=robot_a&names=robot_b")

        self.assertEqual(default_response.status_code, 200)
        self.assertIsNone(default_response.json()["names"])
        self.assertEqual(names_response.status_code, 200)
        self.assertEqual(names_response.json()["names"], ["robot_a", "robot_b"])

    def test_default_specs_are_json_safe(self):
        self.assertEqual(MissionObjectV1.default_spec()["timeout"], 300.0)
        self.assertEqual(RobotObjectV1.default_spec()["heartbeat_timeout"], 30.0)
        json.dumps(MissionObjectV1.default_spec())
        json.dumps(RobotObjectV1.default_spec())

    def test_map_config_payload_dumps_nested_metadata(self):
        config = MapConfig.model_validate({
            "map_file": "/tmp/map.png",
            "metadata": {"map_id": "warehouse"},
        })

        payload = config.to_wpg_data()

        self.assertEqual(payload["map_id"], "warehouse")
        json.dumps(payload)

    def test_invalid_multi_object_request_raises_validation_error(self):
        with self.assertRaises(pydantic.ValidationError):
            MultiObjectPickPlaceData.model_validate({
                "class_ids": [],
                "target_poses": MultiObjectPickPlaceTargetPoses.model_validate({
                    "frame_id": "map",
                    "poses": [{
                        "position": {"x": 0, "y": 0, "z": 0},
                        "orientation": {"w": 1, "x": 0, "y": 0, "z": 0},
                    }],
                }),
            })


class TestPydanticV2ClientPayloads(unittest.IsolatedAsyncioTestCase):
    """Verify JSON payloads produced at Mission Control service boundaries."""

    async def test_robot_heartbeat_uses_total_seconds(self):
        client = MissionDatabaseClient({"base_url": "http://database"}, AsyncMock())
        mock_request = AsyncMock(return_value={})
        client.make_request_with_logs = mock_request  # type: ignore[method-assign]
        robot = RobotObjectV1.model_validate({
            "name": "robot_a",
            "heartbeat_timeout": datetime.timedelta(days=1, seconds=30),
            "status": {},
        })

        await client.create_robot(robot)

        assert mock_request.await_args is not None
        payload = mock_request.await_args.kwargs["json"]
        self.assertEqual(payload["heartbeat_timeout"], 86430.0)
        json.dumps(payload)

    async def test_metropolis_query_uses_aliases_and_values(self):
        client = MetropolisClient({"base_url": "http://metropolis"}, AsyncMock())
        mock_request = AsyncMock(return_value={})
        client.make_request_with_logs = mock_request  # type: ignore[method-assign]
        query = GetUniqueObjects.model_validate({
            "place": "warehouse",
            "timeWindowInMs": 2500,
        })

        await client.get_traffic(query)

        assert mock_request.await_args is not None
        params = mock_request.await_args.kwargs["params"]
        self.assertEqual(params, {"place": "warehouse", "timeWindowInMs": 2500})

    async def test_mission_control_client_payload_is_json_safe(self):
        client = MissionControlClient({"base_url": "http://mission-control"}, AsyncMock())
        mock_request = AsyncMock(return_value={})
        client.make_request_with_logs = mock_request  # type: ignore[method-assign]
        mission = {
            "mission_id": "mission-1",
            "mission_data": {
                "route": [{"x": 1.0, "y": 2.0}],
                "solver": "NVIDIA_CUOPT",
            },
        }

        await client.send_mission(mission)

        assert mock_request.await_args is not None
        payload = mock_request.await_args.kwargs["json"]
        self.assertEqual(payload["solver"], "NVIDIA_CUOPT")
        json.dumps(payload)

    async def test_nested_esp_models_are_dumped_for_json(self):
        client = ESPServiceClient({"base_url": "http://esp"}, AsyncMock())
        mock_request = AsyncMock(return_value={})
        client.make_request_with_logs = mock_request  # type: ignore[method-assign]
        tracks = MTMCTracks.model_validate({
            "timestamp": "2026-09-03T12:34:56Z",
            "tracks": [{"id": 1, "pos_x": 2.0, "pos_y": 3.0}],
        })
        routes = {
            "robot_a": RouteESP.model_validate({
                "waypoints": [{"pos_x": 4.0, "pos_y": 5.0}],
            }),
        }

        await client.send_tracks(tracks, routes)

        assert mock_request.await_args is not None
        payload = mock_request.await_args.kwargs["json"]
        self.assertEqual(payload["routes"]["robot_a"]["waypoints"][0]["pos_x"], 4.0)
        json.dumps(payload)

    async def test_mas_blockage_models_are_dumped_for_json(self):
        client = MASServiceClient({"base_url": "http://mas"}, AsyncMock())
        mock_request = AsyncMock(return_value={})
        client.make_request_with_logs = mock_request  # type: ignore[method-assign]
        blockages = [Blockage.model_validate({"center": [1.0, 2.0], "radius": 3.0})]

        await client.send_blockages(blockages)

        assert mock_request.await_args is not None
        payload = mock_request.await_args.kwargs["json"]
        self.assertEqual(payload, {"circles": [{"center": [1.0, 2.0], "radius": 3.0}]})
        json.dumps(payload)


if __name__ == "__main__":
    unittest.main()
