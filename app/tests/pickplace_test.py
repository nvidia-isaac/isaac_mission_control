# SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
# Copyright (c) 2022-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import unittest
import httpx

from app.api.clients.mission_control_client import MissionControlClient
from app.api.clients.mission_database_client import MissionDatabaseClient
from app.tests import test_context
from app.tests.test_context import TestConfigKey
from cloud_common.objects.robot import VDA5050AgvClass

from httpx import HTTPStatusError


class TestPickPlace(unittest.IsolatedAsyncioTestCase):
    """Ensure pick-place works for manipulators and fails for other robots;
    also, ensures navigation missions aren't sent to manipulators"""

    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(timeout=60.0)

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_pickplace_on_manipulator(self):
        """Ensure that pickplace works for manipulator robots"""
        robots = [test_context.RobotInit(
            "robot_a", 35, 35, battery=100, robot_type=VDA5050AgvClass.MANIPULATOR)]
        with test_context.TestContext(
                config_overrides=test_context.get_test_config(TestConfigKey.PICKPLACE),
                robots=robots,
                async_client=self.client) as ctx:
            mission_control_client = MissionControlClient(
                ctx.mission_control_config,
                client=self.client)
            mission_database_client = MissionDatabaseClient(
                ctx.mission_database_config,
                client=self.client)

            mc_online = await mission_control_client.wait_for_mc_alive()
            assert mc_online
            # Wait for robots to be ready
            robots_online = await mission_database_client.wait_for_robots(robots=["robot_a"])
            assert robots_online

            await mission_control_client.send_pickplace_mission(
                "robot_a", 0, "macaroni_box", 0, 0, 0, 0, 0, 0, 0)

    async def test_pickplace_on_amr(self):
        robots = [test_context.RobotInit(
            "robot_b", 35, 35, battery=100, robot_type=VDA5050AgvClass.CARRIER)]
        with test_context.TestContext(
                config_overrides=test_context.get_test_config(TestConfigKey.PICKPLACE),
                robots=robots,
                async_client=self.client) as ctx:
            mission_control_client = MissionControlClient(
                ctx.mission_control_config,
                client=self.client)
            mission_database_client = MissionDatabaseClient(
                ctx.mission_database_config,
                client=self.client)

            mc_online = await mission_control_client.wait_for_mc_alive()
            assert mc_online
            # Wait for robots to be ready
            robots_online = await mission_database_client.wait_for_robots(robots=["robot_b"])
            assert robots_online

            with self.assertRaises(HTTPStatusError):
                await mission_control_client.send_pickplace_mission(
                    "robot_b", 0, "macaroni_box", 0, 0, 0, 0, 0, 0, 0)


if __name__ == "__main__":
    unittest.main()
