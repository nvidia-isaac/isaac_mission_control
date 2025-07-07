# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import httpx
import unittest

from app.api.clients.mission_control_client import MissionControlClient
from app.api.clients.mission_database_client import MissionDatabaseClient
from app.tests import test_context
from app.tests.test_context import TestConfigKey

MISSION_A = {
    "mission_id": "mission_a",
    "mission_template": "simple_navigation_mission",
    "mission_data": {"route": [{"x": 8, "y": 8}]}
}

MISSION_B = {
    "mission_id": "mission_b",
    "mission_template": "simple_navigation_mission",
    "mission_data": {"start_location": {"x": 8, "y": 8},
                     "route": [{"x": 8, "y": 10}
                               ],
                     "iterations": 1
                     }
}

MISSION_C = {
    "mission_id": "mission_c",
    "mission_template": "simple_navigation_mission",
    "mission_data": {"start_location": {"x": 8, "y": 8},
                     "end_location": {"x": 8, "y": 10},
                     "route": [{"x": 8, "y": 10}
                               ],
                     "iterations": 5
                     }
}

MISSION_ELEVATOR = {
    "mission_id": "elevator_office",
    "mission_template": "simple_navigation_mission",
    "mission_data": {"route": [{"x": 5.0, "y": 19.0}]}
}

MISSION_GALILEO_HUBBLE = {
    "mission_id": "galileo_hubble",
    "mission_template": "simple_navigation_mission",
    "mission_data": {"route": [{"x": 43.138, "y": 12.437}]}
}


class TestMissions(unittest.IsolatedAsyncioTestCase):
    """Test an end-to-end mission"""

    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(timeout=60.0)

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_single_mission(self):
        """ Test a simple mission example """
        async with test_context.TestContext(config_overrides=None,  # Use base config
                                            async_client=self.client) as ctx:
            mission_control_client = MissionControlClient(
                config=ctx.mission_control_config, client=self.client)
            mission_database_client = MissionDatabaseClient(
                ctx.mission_database_config, client=self.client)

            # Verify Control is running & health endpoint has test coverage
            mc_online = await mission_control_client.wait_for_mc_alive()
            assert mc_online

            # Wait for robots to be ready
            robots_online = await mission_database_client.wait_for_robots(robots=["robot_a"])
            assert robots_online

            mission = await mission_control_client.send_mission(MISSION_A)
            for sub_mission_uuid in mission["sub_mission_uuids"]:
                mission_state = await test_context.wait_for_mission_to_complete(
                    ctx, sub_mission_uuid, timeout=900)
                self.assertEqual(mission_state, "COMPLETED")

    async def test_mission_with_iteration(self):
        """ Test a simple mission example """
        async with test_context.TestContext(config_overrides=None,  # Use base config
                                            async_client=self.client) as ctx:
            mission_control_client = MissionControlClient(
                config=ctx.mission_control_config, client=self.client)
            mission_database_client = MissionDatabaseClient(
                ctx.mission_database_config, client=self.client)

            mc_online = await mission_control_client.wait_for_mc_alive()
            assert mc_online

            # Wait for robots to be ready
            robots_online = await mission_database_client.wait_for_robots(robots=["robot_a"])
            assert robots_online

            mission = await mission_control_client.send_mission(MISSION_B)
            for sub_mission_uuid in mission["sub_mission_uuids"]:
                mission_state = await test_context.wait_for_mission_to_complete(
                    ctx, sub_mission_uuid, timeout=900)
                self.assertEqual(mission_state, "COMPLETED")

    async def test_patrol_mission(self):
        """ Test a simple mission example """
        async with test_context.TestContext(config_overrides=None,  # Use base config
                                            async_client=self.client) as ctx:
            mission_control_client = MissionControlClient(
                config=ctx.mission_control_config, client=self.client)
            mission_database_client = MissionDatabaseClient(
                ctx.mission_database_config, client=self.client)

            mc_online = await mission_control_client.wait_for_mc_alive()
            assert mc_online

            # Wait for robots to be ready
            robots_online = await mission_database_client.wait_for_robots(robots=["robot_a"])
            assert robots_online

            mission = await mission_control_client.send_mission(MISSION_C)
            for sub_mission_uuid in mission["sub_mission_uuids"]:
                mission_state = await test_context.wait_for_mission_to_complete(
                    ctx, sub_mission_uuid, timeout=900)
                self.assertEqual(mission_state, "COMPLETED")

    async def test_consecutive_missions(self):
        """ Test consecutive missions example """
        async with test_context.TestContext(config_overrides=None,  # Use base config
                                            async_client=self.client) as ctx:
            mission_control_client = MissionControlClient(
                config=ctx.mission_control_config, client=self.client)
            mission_database_client = MissionDatabaseClient(
                ctx.mission_database_config, client=self.client)

            mc_online = await mission_control_client.wait_for_mc_alive()
            assert mc_online

            # Wait for robots to be ready
            robots_online = await mission_database_client.wait_for_robots(robots=["robot_a"])
            assert robots_online

            for i in range(2):
                MISSION_A["mission_id"] = f"mission_a_{i}"
                mission = await mission_control_client.send_mission(MISSION_A)
                for sub_mission_uuid in mission["sub_mission_uuids"]:
                    mission_state = await test_context.wait_for_mission_to_complete(
                        ctx, sub_mission_uuid, timeout=900)
                    self.assertEqual(mission_state, "COMPLETED")

    # async def test_mission_with_semantic_map(self):
    #     """ Test a simple mission with a semantic map file example """
    #     async with test_context.TestContext(
    #             config_file=test_context.TEST_CONFIG["map_file_semantic"],
    #             async_client=self.client) as ctx:
    #         mission_control_client = MissionControlClient(
    #             config=ctx.mission_control_config, client=self.client)
    #         mission_database_client = MissionDatabaseClient(
    #             ctx.mission_database_config, client=self.client)

    #         mc_online = await mission_control_client.wait_for_mc_alive()
    #         assert mc_online

    #         # Wait for robots to be ready
    #         robots_online = await mission_database_client.wait_for_robots(robots=["robot_a"])
    #         assert robots_online

    #         mission = await mission_control_client.send_mission(MISSION_ELEVATOR)
    #         for sub_mission_uuid in mission["sub_mission_uuids"]:
    #             mission_state = await test_context.wait_for_mission_to_complete(
    #                 ctx, sub_mission_uuid, timeout=1000)
    #             self.assertEqual(mission_state, "COMPLETED")

    async def test_charging_mission_with_occupancy_map(self):
        """ Test charging mission """
        robot_a = test_context.RobotInit("robot_a", 44.28, 18.49, battery=10)
        async with test_context.TestContext(
                config_overrides=test_context.get_test_config(TestConfigKey.GALILEO_HUBBLE),
                robots=[robot_a],
                async_client=self.client) as ctx:
            mission_control_client = MissionControlClient(
                config=ctx.mission_control_config, client=self.client)
            mission_database_client = MissionDatabaseClient(
                ctx.mission_database_config, client=self.client)

            mc_online = await mission_control_client.wait_for_mc_alive()
            assert mc_online

            # Wait for robots to be ready
            robots_online = await mission_database_client.wait_for_robots(robots=["robot_a"])
            assert robots_online

            mission = await mission_control_client.send_charging_mission("robot_a")
            for sub_mission_uuid in mission["sub_mission_uuids"]:
                print(f"sub_mission_uuid: {sub_mission_uuid}", flush=True)
                mission_state = await test_context.wait_for_mission_to_complete(
                    ctx, sub_mission_uuid, timeout=900)
                self.assertEqual(mission_state, "COMPLETED")

    # async def test_charging_mission_with_semantic_map_file(self):
    #     """ Test charging mission """
    #     robot_a = test_context.RobotInit("robot_a", 7.35, 2.04, battery=10)
    #     async with test_context.TestContext(
    #             config_file=test_context.TEST_CONFIG["map_file_semantic_with_dock"],
    #             robots=[robot_a],
    #             async_client=self.client) as ctx:
    #         mission_control_client = MissionControlClient(
    #             config=ctx.mission_control_config, client=self.client)
    #         mission_database_client = MissionDatabaseClient(
    #             ctx.mission_database_config, client=self.client)

    #         mc_online = await mission_control_client.wait_for_mc_alive()
    #         assert mc_online

    #         # Wait for robots to be ready
    #         robots_online = await mission_database_client.wait_for_robots(robots=["robot_a"])
    #         assert robots_online

    #         mission = await mission_control_client.send_charging_mission("robot_a")
    #         for sub_mission_uuid in mission["sub_mission_uuids"]:
    #             print(f"sub_mission_uuid: {sub_mission_uuid}", flush=True)
    #             mission_state = await test_context.wait_for_mission_to_complete(
    #                 ctx, sub_mission_uuid, timeout=900)
    #             self.assertEqual(mission_state, "COMPLETED")


if __name__ == "__main__":
    unittest.main()
