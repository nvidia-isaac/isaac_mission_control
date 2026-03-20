"""
SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
Copyright (c) 2023-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.

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
"""
import unittest
import httpx
import app.core.objectives.objectives_conditional as conditional
from app.tests import test_context
from app.api.clients.mission_control_client import MissionControlClient
from app.api.clients.mission_database_client import MissionDatabaseClient
from app.tests.test_context import verify_objective_node_states, TestConfigKey

OBJECTIVE_A = {
    "node_class": "DECORATOR",
    "node_type": "CONDITIONAL",
    "parameters": {
        "condition": {
            "type": "LOGICAL_EXPRESSION",
            "operator": "AND",
            "operands": [
                {
                    "type": "COMPARISON",
                    "operator": "EQ",
                    "operands": ["robot_battery_level(robot_a)", "100"]
                },
                {
                    "type": "COMPARISON",
                    "operator": "EQ",
                    "operands": ["robot_state(robot_a)", "IDLE"]
                }
            ]
        }
    },
    "child": {
        "node_class": "COMPOSITE",
        "node_type": "SEQUENCE",
        "children": [
            {
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
            },
            {
                "node_class": "BEHAVIOR",
                "node_type": "NAVIGATION",
                "parameters": {
                    "route": [
                        {
                            "x": 9,
                            "y": 8
                        }
                    ]
                }
            },
            {
                "node_class": "BEHAVIOR",
                "node_type": "NAVIGATION",
                "parameters": {
                    "route": [
                        {
                            "x": 10,
                            "y": 8
                        }
                    ]
                }
            }
        ]

    }
}

OBJECTIVE_A_EXPECTED = {
    "node_class": "DECORATOR",
    "node_type": "CONDITIONAL",
    "state": "COMPLETED",
    "child": {
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
}

OBJECTIVE_B = {
    "node_class": "DECORATOR",
    "node_type": "CONDITIONAL",
    "parameters": {
        "condition": {
            "type": "LOGICAL_EXPRESSION",
            "operator": "AND",
            "operands": [
                {
                    "type": "COMPARISON",
                    "operator": "EQ",
                    "operands": ["robot_battery_level(robot_a)", "0"]
                },
                {
                    "type": "COMPARISON",
                    "operator": "EQ",
                    "operands": ["robot_state(robot_a)", "IDLE"]
                }
            ]
        }
    },
    "child": {
        "node_class": "COMPOSITE",
        "node_type": "SEQUENCE",
        "children": [
            {
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
        ]
    }
}

OBJECTIVE_B_EXPECTED = {
    "node_class": "DECORATOR",
    "node_type": "CONDITIONAL",
    "state": "FAILED",
    "child": {
        "node_class": "COMPOSITE",
        "node_type": "SEQUENCE",
        "state": "PENDING",
        "children": [
            {
                "node_class": "BEHAVIOR",
                "node_type": "NAVIGATION",
                "state": "PENDING"
            }
        ]
    }
}


OBJECTIVE_C = {
    "node_class": "DECORATOR",
    "node_type": "CONDITIONAL",
    "parameters": {
        "condition": {
            "type": "COMPARISON",
            "operator": "NEQ",
            "operands": ["test1", "test2"]
        }
    },
    "child": {
        "node_class": "DECORATOR",
        "node_type": "CONDITIONAL",
        "parameters": {
            "condition": {
                "type": "COMPARISON",
                "operator": "EQ",
                "operands": ["test1", "test1"]
            }
        },
        "child": {
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
    }
}

OBJECTIVE_C_EXPECTED = {
    "node_class": "DECORATOR",
    "node_type": "CONDITIONAL",
    "state": "COMPLETED",
    "child": {
        "node_class": "DECORATOR",
        "node_type": "CONDITIONAL",
        "state": "COMPLETED",
        "child": {
            "node_class": "BEHAVIOR",
            "node_type": "NAVIGATION",
            "state": "COMPLETED"
        }
    }
}

OBJECTIVE_D = {
    "node_class": "DECORATOR",
    "node_type": "RETRY",
    "parameters": {
        "num_failures": 3
    },
    "child": {
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
}

OBJECTIVE_D_EXPECTED = {
    "node_class": "DECORATOR",
    "node_type": "RETRY",
    "state": "COMPLETED",
    "child": {
        "node_class": "BEHAVIOR",
        "node_type": "NAVIGATION",
        "state": "COMPLETED"
    }
}

OBJECTIVE_E = {
    "node_class": "DECORATOR",
    "node_type": "INVERTER",
    "parameters": {},
    "child": {
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
}

OBJECTIVE_E_EXPECTED = {
    "node_class": "DECORATOR",
    "node_type": "INVERTER",
    "state": "FAILED",
    "child": {
        "node_class": "BEHAVIOR",
        "node_type": "NAVIGATION",
        "state": "COMPLETED"
    }
}

OBJECTIVE_F = {
    "node_class": "DECORATOR",
    "node_type": "REPEAT",
    "parameters": {
        "num_success": 3
    },
    "child": {
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
}

OBJECTIVE_F_EXPECTED = {
    "node_class": "DECORATOR",
    "node_type": "REPEAT",
    "state": "COMPLETED",
    "child": {
        "node_class": "BEHAVIOR",
        "node_type": "NAVIGATION",
        "state": "COMPLETED"
    }
}

OBJECTIVE_G = {
    "node_class": "DECORATOR",
    "node_type": "RETRY",
    "parameters": {
        "num_failures": 3
    },
    "child": {
        "node_class": "DECORATOR",
        "node_type": "INVERTER",
        "parameters": {},
        "child": {
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
    }
}

OBJECTIVE_G_EXPECTED = {
    "node_class": "DECORATOR",
    "node_type": "RETRY",
    "state": "FAILED",
    "child": {
        "node_class": "DECORATOR",
        "node_type": "INVERTER",
        "state": "FAILED",
        "child": {
            "node_class": "BEHAVIOR",
            "node_type": "NAVIGATION",
            "state": "COMPLETED"
        }
    }
}

OBJECTIVE_H = {
    "node_class": "DECORATOR",
    "node_type": "REPEAT",
    "parameters": {
        "num_success": 2
    },
    "child": {
        "node_class": "COMPOSITE",
        "node_type": "SEQUENCE",
        "children": [
            {
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
            },
            {
                "node_class": "BEHAVIOR",
                "node_type": "NAVIGATION",
                "parameters": {
                    "route": [
                        {
                            "x": 25,
                            "y": 25
                        }
                    ]
                }
            }
        ]
    }
}

OBJECTIVE_H_EXPECTED = {
    "node_class": "DECORATOR",
    "node_type": "REPEAT",
    "state": "COMPLETED",
    "child": {
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
                "node_type": "NAVIGATION",
                "state": "COMPLETED"
            }
        ]
    }
}

OBJECTIVE_I = {
    "node_class": "DECORATOR",
    "node_type": "REPEAT",
    "parameters": {
        "num_success": 2
    },
    "child": {
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
                }
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
}

OBJECTIVE_I_EXPECTED = {
    "node_class": "DECORATOR",
    "node_type": "REPEAT",
    "state": "COMPLETED",
    "child": {
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
}

class TestConditionalNode(unittest.IsolatedAsyncioTestCase):
    """Test the conditional node"""

    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(timeout=60.0)

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_evaluate_conditional(self):
        # Test conditional evaluation logic
        with test_context.TestContext(
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

            robot_a = await mission_database_client.get_robot("robot_a")
            print(robot_a)


            # ------------------------------------------------------------
            # Normal logical expression
            # robot_battery_level(robot_a) == 100 AND robot_state(robot_a) == IDLE
            # Expected: True
            condition = conditional.ConditionalExpression(
                type=conditional.ConditionalType.LOGICAL_EXPRESSION,
                operator=conditional.ConditionalOperator.AND,
                operands=[
                    conditional.ConditionalExpression(
                        type=conditional.ConditionalType.COMPARISON,
                        operator=conditional.ConditionalOperator.EQUAL,
                        operands=["robot_battery_level(robot_a)", "100"]
                    ),
                    conditional.ConditionalExpression(
                        type=conditional.ConditionalType.COMPARISON,
                        operator=conditional.ConditionalOperator.EQUAL,
                        operands=["robot_state(robot_a)", "IDLE"]
                    )
                ]
            )
            result = await conditional.evaluate_conditional(condition, mission_database_client)
            self.assertTrue(result)

            # ------------------------------------------------------------
            # Normal logical expression but with a guaranteed false operand
            # robot_battery_level(robot_a) == 100 AND robot_state(robot_a) == IDLE AND 10 == 6
            # Expected: False
            condition = conditional.ConditionalExpression(
                type=conditional.ConditionalType.LOGICAL_EXPRESSION,
                operator=conditional.ConditionalOperator.AND,
                operands=[
                    conditional.ConditionalExpression(
                        type=conditional.ConditionalType.COMPARISON,
                        operator=conditional.ConditionalOperator.EQUAL,
                        operands=["robot_battery_level(robot_a)", "100"]
                    ),
                    conditional.ConditionalExpression(
                        type=conditional.ConditionalType.COMPARISON,
                        operator=conditional.ConditionalOperator.EQUAL,
                        operands=["robot_state(robot_a)", "IDLE"]
                    ),
                    conditional.ConditionalExpression(
                        type=conditional.ConditionalType.COMPARISON,
                        operator=conditional.ConditionalOperator.EQUAL,
                        operands=["10", "6"]
                    )
                ]
            )
            result = await conditional.evaluate_conditional(condition, mission_database_client)
            self.assertFalse(result)

            # ------------------------------------------------------------
            # Test that you can use a reference on the left operand
            # 100 == robot_battery_level(robot_a)
            # Expected: True
            condition = conditional.ConditionalExpression(
                type=conditional.ConditionalType.COMPARISON,
                operator=conditional.ConditionalOperator.EQUAL,
                operands=["100", "robot_battery_level(robot_a)"]
            )
            result = await conditional.evaluate_conditional(condition, mission_database_client)
            self.assertTrue(result)

            # ------------------------------------------------------------
            # Test that you can use a references on both operands
            # robot_battery_level(robot_a) == robot_battery_level(robot_a)
            # Expected: True
            condition = conditional.ConditionalExpression(
                type=conditional.ConditionalType.COMPARISON,
                operator=conditional.ConditionalOperator.EQUAL,
                operands=["robot_battery_level(robot_a)", "robot_battery_level(robot_a)"]
            )
            result = await conditional.evaluate_conditional(condition, mission_database_client)
            self.assertTrue(result)

            # ------------------------------------------------------------
            # Test that strings that can be converted to numbers are converted when applicable
            # '100' == 100
            # Expected: True
            condition = conditional.ConditionalExpression(
                type=conditional.ConditionalType.COMPARISON,
                operator=conditional.ConditionalOperator.EQUAL,
                operands=["100", 100]  # type: ignore
            )
            result = await conditional.evaluate_conditional(condition, mission_database_client)
            self.assertTrue(result)

            # ------------------------------------------------------------
            # Test that if a string cannot be converted to a number, we simply compare as strings
            # '100test' == 100
            # Expected: False
            condition = conditional.ConditionalExpression(
                type=conditional.ConditionalType.COMPARISON,
                operator=conditional.ConditionalOperator.EQUAL,
                operands=["100test", 100]  # type: ignore
            )
            result = await conditional.evaluate_conditional(condition, mission_database_client)
            self.assertFalse(result)

    async def test_conditional_node(self):
        """Test the conditional node with a normal logical expression"""
        with test_context.TestContext(
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

    async def test_conditional_node_failure(self):
        """Test the conditional node with a guaranteed false logical expression"""
        with test_context.TestContext(
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
            assert not objective_complete

            obj = await mission_database_client.get_objective(objective_id)
            assert verify_objective_node_states(obj.status.objective_tree, OBJECTIVE_B_EXPECTED)

    async def test_conditional_node_nested(self):
        """Test the conditional node with a nested conditional node"""
        with test_context.TestContext(
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
            objective_id = await mission_control_client.submit_objective(OBJECTIVE_C)
            objective_complete = await mission_database_client.wait_for_objective_to_complete(
                objective_id)
            assert objective_complete

            obj = await mission_database_client.get_objective(objective_id)
            assert verify_objective_node_states(obj.status.objective_tree, OBJECTIVE_C_EXPECTED)

    async def test_retry_node(self):
        """Test the retry node and that it will not retry on success"""
        with test_context.TestContext(
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
            objective_id = await mission_control_client.submit_objective(OBJECTIVE_D)
            objective_complete = await mission_database_client.wait_for_objective_to_complete(
                objective_id)
            assert objective_complete

            obj = await mission_database_client.get_objective(objective_id)
            assert verify_objective_node_states(obj.status.objective_tree, OBJECTIVE_D_EXPECTED)

            missions = await mission_database_client.get_missions()
            assert missions is not None
            assert len(missions) == 1

    async def test_inverter_node(self):
        """Test the inverter node and that it will invert the result of its child"""
        with test_context.TestContext(
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
            objective_id = await mission_control_client.submit_objective(OBJECTIVE_E)
            objective_complete = await mission_database_client.wait_for_objective_to_complete(
                objective_id)
            assert not objective_complete

            obj = await mission_database_client.get_objective(objective_id)
            assert verify_objective_node_states(obj.status.objective_tree, OBJECTIVE_E_EXPECTED)

    async def test_repeat_node(self):
        """Test the repeat node and that it will repeat its child num_success times"""
        with test_context.TestContext(
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
            objective_id = await mission_control_client.submit_objective(OBJECTIVE_F)
            objective_complete = await mission_database_client.wait_for_objective_to_complete(
                objective_id)
            assert objective_complete

            obj = await mission_database_client.get_objective(objective_id)
            assert verify_objective_node_states(obj.status.objective_tree, OBJECTIVE_F_EXPECTED)

            missions = await mission_database_client.get_missions()
            assert missions is not None
            assert len(missions) == 3, f"Expected 3 missions, got {len(missions)}"

    async def test_retry_inverter_node(self):
        """
        Test the retry node with an inverter node as its child.
        Verify that the retry node will retry num_failures times, and then fail.
        """
        with test_context.TestContext(
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
            objective_id = await mission_control_client.submit_objective(OBJECTIVE_G)
            objective_complete = await mission_database_client.wait_for_objective_to_complete(
                objective_id)
            assert not objective_complete

            obj = await mission_database_client.get_objective(objective_id)
            assert verify_objective_node_states(obj.status.objective_tree, OBJECTIVE_G_EXPECTED)

            missions = await mission_database_client.get_missions()
            assert missions is not None
            assert len(missions) == 3, f"Expected 3 missions, got {len(missions)}"

    async def test_repeat_node_with_sequence_child(self):
        """Test the repeat node with a composite child"""
        with test_context.TestContext(
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
            objective_id = await mission_control_client.submit_objective(OBJECTIVE_H)
            objective_complete = await mission_database_client.wait_for_objective_to_complete(
                objective_id)
            assert objective_complete

            obj = await mission_database_client.get_objective(objective_id)
            assert verify_objective_node_states(obj.status.objective_tree, OBJECTIVE_H_EXPECTED)

            missions = await mission_database_client.get_missions()
            assert missions is not None
            assert len(missions) == 4, f"Expected 4 missions, got {len(missions)}"

    async def test_repeat_node_with_parallel_child(self):
        """Test the repeat node with a parallel child"""
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

            # Verify Control is running
            mc_online = await mission_control_client.wait_for_mc_alive()
            assert mc_online

            # Wait for robots to be ready
            robots_online = await mission_database_client.wait_for_robots(robots=["robot_a",
                                                                                  "robot_b"])
            assert robots_online

            # Submit objective
            objective_id = await mission_control_client.submit_objective(OBJECTIVE_I)
            objective_complete = await mission_database_client.wait_for_objective_to_complete(
                objective_id)
            assert objective_complete

            obj = await mission_database_client.get_objective(objective_id)
            assert verify_objective_node_states(obj.status.objective_tree, OBJECTIVE_I_EXPECTED)

            missions = await mission_database_client.get_missions()
            assert missions is not None
            assert len(missions) == 4, f"Expected 4 missions, got {len(missions)}"

if __name__ == "__main__":
    unittest.main()
