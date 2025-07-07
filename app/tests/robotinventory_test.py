import unittest

from cloud_common.objects.common import ICSUsageError

from app.core.mission_control_config import MissionControlConfig
from app.core.robots import RobotInventory
from app.tests import test_context
from app.tests.test_context import TestConfigKey


class TestRobotInventory(unittest.TestCase):
    """Unit tests for RobotInventory"""

    def test_multiple_robots(self):
        """Test that config with multiple robots is loaded correctly"""
        config = MissionControlConfig("app/config/test_base.yaml",
                                      test_context.get_test_config(TestConfigKey.ROBOTS))
        robot_inventory = RobotInventory(config.get_robots_config())
        assert len(robot_inventory.get_robots()) == 3

    def test_missing_fields(self):
        """Raise Pydantic ValidationError on missing mandatory fields"""
        robots_config = [
            {
                "labels": ["test"],
            }
        ]
        with self.assertRaises(ICSUsageError):
            robot_inventory = RobotInventory(  # pylint: disable=unused-variable
                robots_config)

    def test_name_collision(self):
        """Raise KeyError on name collision"""
        robots_config = [
            {
                "name": "robot_a",
            },
            {
                "name": "robot_a",
            }
        ]
        with self.assertRaises(KeyError):
            robot_inventory = RobotInventory(  # pylint: disable=unused-variable
                robots_config)

    def test_get_robots(self):
        """Test getter functions"""
        robots_config = [
            {
                "name": "robot_a",
                "labels": ["test1"],
            },
            {
                "name": "robot_b",
                "labels": ["test2"],
            },
            {
                "name": "robot_c",
                "labels": ["test3"],
            }
        ]
        robot_inventory = RobotInventory(robots_config)

        robot_a = robot_inventory.get_robot("robot_a")
        assert robot_a.name == "robot_a"
        assert robot_a.labels == ["test1"]

        names = robot_inventory.get_robot_names()
        assert names == [robot["name"] for robot in robots_config]

        robots = robot_inventory.get_robots(names)
        assert len(robots) == 3
        assert robots[0].name == "robot_a"
        assert robots[1].name == "robot_b"
        assert robots[2].name == "robot_c"


if __name__ == "__main__":
    unittest.main()
