# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

# mypy: disable-error-code="union-attr"

import httpx
import unittest
from datetime import datetime, timedelta

from app.api.clients.mission_control_client import MissionControlClient
from app.api.clients.mission_database_client import MissionDatabaseClient
from app.core.mission_control_config import MissionControlConfig
from app.tests import test_context
from app.tests.test_context import TestConfigKey, verify_objective_node_states
from cloud_common.objects.robot import VDA5050AgvClass


OBJECTIVE_A = {
    "node_class": "BEHAVIOR",
    "node_type": "NAVIGATION",
    "parameters": {
        "route": [
            {
                "x": 8,
                "y": 8
            }
        ]
    }
}

OBJECTIVE_A_EXPECTED = {
    "node_class": "BEHAVIOR",
    "node_type": "NAVIGATION",
    "state": "COMPLETED"
}

OBJECTIVE_B = {
    "node_class": "COMPOSITE",
    "node_type": "SEQUENCE",
    "children": [
        {
            "node_class": "BEHAVIOR",
            "node_type": "NAVIGATION",
            "parameters": {
                "route": [
                    {
                        "x": 9.611,
                        "y": 14.6
                    }
                ]
            }
        },
        {
            "node_class": "BEHAVIOR",
            "node_type": "CHARGING",
            "parameters": {
                "robot_name": "robot_a"
            }
        }
    ]
}

OBJECTIVE_B_EXPECTED = {
    "node_class": "COMPOSITE",
    "node_type": "SEQUENCE",
    "state": "COMPLETED",
    "children": [
        {
            "node_class": "BEHAVIOR",
            "node_type": "NAVIGATION",
            "state": "COMPLETED"
        },
        {
            "node_class": "BEHAVIOR",
            "node_type": "CHARGING",
            "state": "COMPLETED"
        }
    ]
}

OBJECTIVE_C = {
    "node_class": "COMPOSITE",
    "node_type": "PARALLEL",
    "children": [
        {
            "node_class": "BEHAVIOR",
            "node_type": "NAVIGATION",
            "parameters": {
                "robot_name": "robot_a",
                "route": [
                    {
                        "x": 38.668574121407985,
                        "y": 13.058567670744942
                    }
                ]
            },
        },
        {
            "node_class": "BEHAVIOR",
            "node_type": "NAVIGATION",
            "parameters": {
                "robot_name": "robot_b",
                "route": [
                    {
                        "x": 43.13812263700239,
                        "y": 12.437736112372972
                    }
                ]
            }
        }
    ]
}

OBJECTIVE_C_EXPECTED = {
    "node_class": "COMPOSITE",
    "node_type": "PARALLEL",
    "state": "COMPLETED",
    "children": [
        {
            "node_class": "BEHAVIOR",
            "node_type": "NAVIGATION",
            "state": "COMPLETED"
        },
        {
            "node_class": "BEHAVIOR",
            "node_type": "NAVIGATION",
            "state": "COMPLETED"
        }
    ]
}

OBJECTIVE_SLEEP = {
    "node_class": "BEHAVIOR",
    "node_type": "SLEEP",
    "parameters": {
        "duration": 5.0
    }
}

OBJECTIVE_SLEEP_EXPECTED = {
    "node_class": "BEHAVIOR",
    "node_type": "SLEEP",
    "state": "COMPLETED"
}

# Context test: object detection + apriltag detection → context-driven pickplace
OBJECTIVE_DETECTION_CONTEXT_TEST = {
    "node_class": "COMPOSITE",
    "node_type": "SEQUENCE",
    "children":
    [
        {
            "node_class": "BEHAVIOR",
            "node_type": "OBJ_DETECTION",
            "parameters": {
                "robot_name": "robot_a"
            },
            "outputs": {
                "object_id_by_class": "object_ids",
            }
        },
        {
            "node_class": "BEHAVIOR",
            "node_type": "APRILTAG_DETECTION",
            "parameters": {
                "robot_name": "robot_a"
            },
            "outputs": {
                "tags_pose_by_id": "tag_poses"
            }
        },
        {
            "node_class": "BEHAVIOR",
            "node_type": "PICKPLACE",
            "parameters": {
                "robot_name": "robot_a",
                "object_id": "$object_ids[''][0]",
                "class_id": "",
                "pos_x": "$tag_poses['42'].pos_x",
                "pos_y": "$tag_poses['42'].pos_y",
                "pos_z": "$tag_poses['42'].pos_z",
                "pos_z_offset": 0.1,
                "quat_x": 0.996,
                "quat_y": 0.066,
                "quat_z": 0.042,
                "quat_w": 0.034
            }
        }
    ]
}

OBJECTIVE_DETECTION_CONTEXT_TEST_EXPECTED = {
    "node_class": "COMPOSITE",
    "node_type": "SEQUENCE",
    "state": "COMPLETED",
    "children": [
        {
            "node_class": "BEHAVIOR",
            "node_type": "OBJ_DETECTION",
            "state": "COMPLETED"
        },
        {
            "node_class": "BEHAVIOR",
            "node_type": "APRILTAG_DETECTION",
            "state": "COMPLETED"
        },
        {
            "node_class": "BEHAVIOR",
            "node_type": "PICKPLACE",
            "state": "COMPLETED"
        }
    ]
}


class TestObjectives(unittest.IsolatedAsyncioTestCase):
    """ Test suite for Objectives """

    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(timeout=60.0)

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_single_behavior_node(self):
        """ Test a simple mission example """
        with test_context.TestContext(config_overrides=None,  # Use base config
                                      async_client=self.client) as ctx:
            mission_control_client = MissionControlClient(
                config=ctx.mission_control_config, client=self.client)
            mission_database_client = MissionDatabaseClient(
                ctx.mission_database_config, client=self.client)

            # Verify Control is running
            mc_online = await mission_control_client.wait_for_mc_alive()
            assert mc_online

            # Wait for robots to be ready
            robots_online = await mission_database_client.wait_for_robots(robots=["robot_a"])
            assert robots_online

            # Submit objective
            objective_id = await mission_control_client.submit_objective(OBJECTIVE_A)
            objective_complete = await mission_database_client.wait_for_objective_to_complete(
                objective_id)
            assert objective_complete

            obj = await mission_database_client.get_objective(objective_id)
            assert verify_objective_node_states(obj.status.objective_tree, OBJECTIVE_A_EXPECTED)

    async def test_simple_tree(self):
        with test_context.TestContext(
                config_overrides=test_context.get_test_config(TestConfigKey.DOCKS),
                async_client=self.client) as ctx:
            mission_control_client = MissionControlClient(
                config=ctx.mission_control_config, client=self.client)
            mission_database_client = MissionDatabaseClient(
                ctx.mission_database_config, client=self.client)

            # Verify Control is running
            mc_online = await mission_control_client.wait_for_mc_alive()
            assert mc_online

            # Wait for robots to be ready
            robots_online = await mission_database_client.wait_for_robots(robots=["robot_a"])
            assert robots_online

            # Submit objective
            objective_id = await mission_control_client.submit_objective(OBJECTIVE_B)
            objective_complete = await mission_database_client.wait_for_objective_to_complete(
                objective_id)
            assert objective_complete

            # Check that robot_a is at the dock after charging mission
            config = MissionControlConfig("app/config/test_base.yaml",
                                          test_context.get_test_config(TestConfigKey.DOCKS))
            dock_configs = config.get_map_config().docks
            db_robot_a = await ctx.mission_database_client.get_robot("robot_a")

            # Get the expected dock position
            expected_x = dock_configs[0].dock_pose.x
            expected_y = dock_configs[0].dock_pose.y

            # Get the actual robot position using dot notation
            actual_x = db_robot_a.status.pose.x
            actual_y = db_robot_a.status.pose.y

            assert (actual_x == expected_x
                    ), f"Robot x is at {actual_x}, expected {expected_x}"
            assert (actual_y == expected_y
                    ), f"Robot y is at {actual_y}, expected {expected_y}"

            obj = await mission_database_client.get_objective(objective_id)
            assert verify_objective_node_states(obj.status.objective_tree, OBJECTIVE_B_EXPECTED)

    async def test_cancel_objective(self):
        """ Test a simple mission example """
        with test_context.TestContext(config_overrides=None,  # Use base config
                                      async_client=self.client) as ctx:
            mission_control_client = MissionControlClient(
                config=ctx.mission_control_config, client=self.client)
            mission_database_client = MissionDatabaseClient(
                ctx.mission_database_config, client=self.client)

            # Verify Control is running
            mc_online = await mission_control_client.wait_for_mc_alive()
            assert mc_online

            # Wait for robots to be ready
            robots_online = await mission_database_client.wait_for_robots(robots=["robot_a"])
            assert robots_online

            # Submit objective
            objective_id = await mission_control_client.submit_objective(OBJECTIVE_A)

            # Cancel objective
            await mission_control_client.cancel_objective(objective_id)

            # Wait for objective to be cancelled
            objective_complete = await mission_database_client.wait_for_objective_to_complete(
                objective_id)
            assert not objective_complete

    async def test_parallel_node(self):
        robot_a = test_context.RobotInit("robot_a", 40.234, 19.389)
        robot_b = test_context.RobotInit("robot_b", 43.308, 18.642)
        with test_context.TestContext(
                config_overrides=test_context.get_test_config(TestConfigKey.GALILEO_HUBBLE),
                robots=[robot_a, robot_b],
                async_client=self.client) as ctx:
            mission_control_client = MissionControlClient(
                config=ctx.mission_control_config, client=self.client)
            mission_database_client = MissionDatabaseClient(
                ctx.mission_database_config, client=self.client)

            # Verify Control is running & health endpoint has test coverage
            mc_online = await mission_control_client.wait_for_mc_alive()
            assert mc_online

            # Wait for robots to be ready
            robots_online = await mission_database_client.wait_for_robots(robots=[
                "robot_a", "robot_b"])
            assert robots_online

            # Submit objective
            objective_id = await mission_control_client.submit_objective(OBJECTIVE_C)
            objective_complete = await mission_database_client.wait_for_objective_to_complete(
                objective_id)
            assert objective_complete

            obj = await mission_database_client.get_objective(objective_id)
            assert verify_objective_node_states(obj.status.objective_tree, OBJECTIVE_C_EXPECTED)

    async def test_detection_with_context_resolution(self):
        """Test detection mission followed by context-driven pickplace"""
        robot_a = test_context.RobotInit("robot_a", 25, 25,
                                         robot_type=VDA5050AgvClass.MANIPULATOR)

        with test_context.TestContext(
                config_overrides=test_context.get_test_config(TestConfigKey.PICKPLACE),
                robots=[robot_a],
                async_client=self.client) as ctx:
            mission_control_client = MissionControlClient(
                config=ctx.mission_control_config, client=self.client)
            mission_database_client = MissionDatabaseClient(
                ctx.mission_database_config, client=self.client)

            # Verify Control is running
            mc_online = await mission_control_client.wait_for_mc_alive()
            assert mc_online

            # Wait for robot to be ready
            robots_online = await mission_database_client.wait_for_robots(
                robots=["robot_a"])
            assert robots_online

            # Submit objective with context resolution
            objective_id = await mission_control_client.submit_objective(
                OBJECTIVE_DETECTION_CONTEXT_TEST)

            # Wait for objective to complete
            objective_complete = await mission_database_client.wait_for_objective_to_complete(
                objective_id)
            assert objective_complete

            # Verify context resolution worked - parameters should be resolved
            obj = await mission_database_client.get_objective(objective_id)
            pickplace_node = obj.status.objective_tree.children[2]

            resolved_object_id = pickplace_node.parameters.get("object_id")
            resolved_pos_x = pickplace_node.parameters.get("pos_x")
            resolved_pos_y = pickplace_node.parameters.get("pos_y")
            resolved_pos_z = pickplace_node.parameters.get("pos_z")

            # Context variables should be resolved to actual values (new $ format)
            assert not str(resolved_object_id).startswith("$"), \
                "object_id should be resolved from context"
            assert not str(resolved_pos_x).startswith("$"), \
                "pos_x should be resolved from context"
            assert not str(resolved_pos_y).startswith("$"), \
                "pos_y should be resolved from context"
            assert not str(resolved_pos_z).startswith("$"), \
                "pos_z should be resolved from context"

            # Verify expected values from dummy detection data
            assert resolved_object_id == 0
            assert resolved_pos_x == 1.0
            assert resolved_pos_y == 0.5
            assert resolved_pos_z == 0.0  # Resolved value from AprilTag (offset in execution)

            # Verify objectives framework worked correctly
            assert pickplace_node.mission_id is not None, "Pickplace mission should be created"
            print("SUCCESS: Objectives framework working correctly!")
            print("  Context resolution: $variable -> actual values")
            print(f"  Mission creation: Pickplace mission {pickplace_node.mission_id}")
            print(f"  Values: object_id={resolved_object_id}, pos=({resolved_pos_x}, "
                  f"{resolved_pos_y}, {resolved_pos_z})")

    async def test_sleep_node(self):
        """Test sleep node"""
        with test_context.TestContext(config_overrides=None,  # Use base config
                                      async_client=self.client) as ctx:
            mission_control_client = MissionControlClient(
                config=ctx.mission_control_config, client=self.client)
            mission_database_client = MissionDatabaseClient(
                ctx.mission_database_config, client=self.client)

            # Verify Control is running
            mc_online = await mission_control_client.wait_for_mc_alive()
            assert mc_online

            # Submit objective
            objective_id = await mission_control_client.submit_objective(OBJECTIVE_SLEEP)
            time_to_complete = datetime.now() + timedelta(seconds=5.0)
            objective_complete = await mission_database_client.wait_for_objective_to_complete(
                objective_id)
            assert objective_complete

            obj = await mission_database_client.get_objective(objective_id)
            assert verify_objective_node_states(obj.status.objective_tree, OBJECTIVE_SLEEP_EXPECTED)
            assert datetime.now() >= time_to_complete


if __name__ == "__main__":
    unittest.main()

