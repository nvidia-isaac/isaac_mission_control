# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import unittest
import httpx

from app.api.clients.mission_control_client import MissionControlClient
from app.core.mission_control_config import MissionControlConfig
from app.tests import test_context
from app.tests.test_context import TestConfigKey


class TestDocking(unittest.IsolatedAsyncioTestCase):
    """Test docking functionalities"""

    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(timeout=60.0)

    async def asyncTearDown(self):
        await self.client.aclose()

    def test_dock_config(self):
        config = MissionControlConfig("app/config/test_base.yaml",
                                      test_context.get_test_config(TestConfigKey.DOCKS))
        map_config = config.get_map_config()
        assert len(map_config.docks) == 3

    async def test_route_to_nearest_dock(self):
        """ Test charging mission """
        robot_a = test_context.RobotInit("robot_a", 9.611, 14.6, battery=10)
        robot_b = test_context.RobotInit("robot_b", 13.946, 32.525, battery=10)
        robot_c = test_context.RobotInit("robot_c", 17.226, 9.68, battery=10)

        config = MissionControlConfig("app/config/test_base.yaml",
                                      test_context.get_test_config(TestConfigKey.DOCKS))
        dock_configs = config.get_map_config().docks

        with test_context.TestContext(
                config_overrides=test_context.get_test_config(TestConfigKey.DOCKS),
                robots=[robot_a, robot_b, robot_c], async_client=self.client) as ctx:
            mission_control_client = MissionControlClient(
                ctx.mission_control_config, client=self.client)

            # Verify Control is running
            mc_online = await mission_control_client.wait_for_mc_alive()
            assert mc_online

            # Wait for robots to be ready
            robots_online = await ctx.mission_database_client.wait_for_robots(robots=["robot_a"])
            assert robots_online

            # Send charging mission to robot_a
            mission = await mission_control_client.send_charging_mission("robot_a")
            # Check that dock01 is returned from mission
            assert mission["docks"][0] == "dock01"
            for sub_mission_uuid in mission["sub_mission_uuids"]:
                mission_state = await test_context.wait_for_mission_to_complete(
                    ctx, sub_mission_uuid, timeout=900)
                self.assertEqual(mission_state, "COMPLETED")

            # Verify that robot_a goes to dock 1
            db_robot_a = await ctx.mission_database_client.get_robot("robot_a")
            assert (db_robot_a.status.pose.x == dock_configs[0].dock_pose.x
                    ), f"Robot x is at {db_robot_a.status.pose.x}"
            assert (db_robot_a.status.pose.y == dock_configs[0].dock_pose.y
                    ), f"Robot y is at {db_robot_a.status.pose.y}"

            # Send charging mission to robot_b
            mission = await mission_control_client.send_charging_mission("robot_b")
            # Check that dock02 is returned from mission
            assert mission["docks"][0] == "dock02"
            for sub_mission_uuid in mission["sub_mission_uuids"]:
                mission_state = await test_context.wait_for_mission_to_complete(
                    ctx, sub_mission_uuid, timeout=900)
                self.assertEqual(mission_state, "COMPLETED")

            # Verify that robot_b goes to dock 2
            db_robot_b = await ctx.mission_database_client.get_robot("robot_b")
            assert (db_robot_b.status.pose.x == dock_configs[1].dock_pose.x
                    ), f"Robot x is at {db_robot_b.status.pose.x}"
            assert (db_robot_b.status.pose.y == dock_configs[1].dock_pose.y
                    ), f"Robot y is at {db_robot_b.status.pose.y}"

            # Send charging mission to robot_c
            mission = await mission_control_client.send_charging_mission("robot_c")
            # Check that dock03 is returned from mission
            assert mission["docks"][0] == "dock03"
            for sub_mission_uuid in mission["sub_mission_uuids"]:
                mission_state = await test_context.wait_for_mission_to_complete(
                    ctx, sub_mission_uuid, timeout=900)
                self.assertEqual(mission_state, "COMPLETED")

            # Verify that robot_c goes to dock 3
            db_robot_c = await ctx.mission_database_client.get_robot("robot_c")
            assert (db_robot_c.status.pose.x == dock_configs[2].dock_pose.x
                    ), f"Robot x is at {db_robot_c.status.pose.x}"
            assert (db_robot_c.status.pose.y == dock_configs[2].dock_pose.y
                    ), f"Robot y is at {db_robot_c.status.pose.y}"


if __name__ == "__main__":
    unittest.main()
