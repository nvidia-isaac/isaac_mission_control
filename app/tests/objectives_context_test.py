"""
SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
Copyright (c) 2023-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.

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
import math

from scipy.spatial.transform import Rotation as R
from cloud_common.objects.common import Point3D as Position3D, Pose3D, Quaternion
from cloud_common.objects.objective import ObjectiveNodeType
from cloud_common.objects.detection_results import (
    DetectedObject, DetectedObjectBoundingBox2D, DetectedObjectBoundingBox3D,
    DetectedObjectCenter2D
)
from cloud_common.objects.apriltag_results import DetectedAprilTag, AprilTagCenter2D

from app.core.objectives.objectives import PickPlaceNodeSchema
from app.core.objectives.objectives_context import ObjectivesContext, ContextAccessError, extract_outputs_from_result


class TestObjectivesContext(unittest.TestCase):
    """Concise tests for simplified objectives context system"""

    def setUp(self):
        self.context = ObjectivesContext()

    def test_basic_variable_resolution(self):
        """Test basic $variable resolution"""
        self.context.set_variable("simple_var", "test_value")
        self.context.set_variable("number_var", 42)

        params = {"param1": "$simple_var", "param2": "$number_var", "param3": "constant"}
        resolved = self.context.resolve_parameters(params)

        self.assertEqual(resolved["param1"], "test_value")
        self.assertEqual(resolved["param2"], 42)
        self.assertEqual(resolved["param3"], "constant")

    def test_dictionary_and_array_access(self):
        """Test dictionary keys and array indexing"""
        test_dict = {"3": [123, 456], "5": [789]}
        test_array = [{"pos_x": 1.0}, {"pos_x": 2.0}]

        self.context.set_variable("objects", test_dict)
        self.context.set_variable("poses", test_array)

        # Dictionary access with quoted keys
        params = {"obj1": "$objects['3'][0]", "obj2": "$objects['5'][0]"}
        resolved = self.context.resolve_parameters(params)
        self.assertEqual(resolved["obj1"], 123)
        self.assertEqual(resolved["obj2"], 789)

        # Array indexing
        params = {"pos": "$poses[1]"}
        resolved = self.context.resolve_parameters(params)
        self.assertEqual(resolved["pos"], {"pos_x": 2.0})

    def test_pydantic_access_blocked(self):
        """Test that direct Pydantic model attribute access is blocked"""
        # Create a Pydantic model instance
        point = Position3D(x=1.5, y=2.5, z=3.5)
        self.context.set_variable("point", point)

        # Direct Pydantic attribute access should be blocked
        with self.assertRaises(ContextAccessError) as cm:
            self.context.resolve_parameters({"x_coord": "$point.x"})

        error_msg = str(cm.exception)
        self.assertIn("output extractors", error_msg)
        self.assertIn("outputs", error_msg)

    def test_security_restrictions(self):
        """Test security measures against dangerous access"""
        self.context.set_variable("test_obj", {"safe_key": "value"})

        # Test double underscore blocking
        with self.assertRaises(ContextAccessError):
            self.context.resolve_parameters({"bad": "$test_obj.__class__"})

        # Test that all Pydantic attribute access is blocked
        point = Position3D(x=1.0, y=2.0, z=3.0)
        self.context.set_variable("point", point)
        with self.assertRaises(ContextAccessError):
            self.context.resolve_parameters({"bad": "$point.x"})  # Even valid fields blocked

    def test_obscure_edge_cases(self):
        """Test obscure edge cases and malformed syntax handling"""
        # Set up test data with unusual but valid keys
        self.context.set_variable("data", {
            "": "empty_key_value",  # Empty string key
            "key with spaces": "spaces_value",
            "key-with-dashes": "dashes_value",
            "normal": {"nested": "deep_value"}
        })

        # Test 1: Empty string keys (valid)
        resolved = self.context.resolve_parameters({"test": "$data['']"})
        self.assertEqual(resolved["test"], "empty_key_value")

        # Test 2: Keys with spaces and special characters (valid)
        resolved = self.context.resolve_parameters({
            "spaces": "$data['key with spaces']",
            "dashes": "$data['key-with-dashes']"
        })
        self.assertEqual(resolved["spaces"], "spaces_value")
        self.assertEqual(resolved["dashes"], "dashes_value")

        # Test 3: Nested brackets should fail (security critical)
        with self.assertRaises(ContextAccessError):
            self.context.resolve_parameters({"bad": "$data[normal[nested]]"})

        # Test 4: Unclosed brackets should fail
        with self.assertRaises(ContextAccessError):
            self.context.resolve_parameters({"bad": "$data[unclosed"})

    def test_output_extractors(self):
        """Test key output extractors with flattened pose data using actual objects"""
        # Create actual DetectedObject instance instead of mock
        position = Position3D(x=1.0, y=2.0, z=3.0)
        orientation = Quaternion(x=0.1, y=0.2, z=0.3, w=0.9)
        pose3d = Pose3D(position=position, orientation=orientation)

        bbox3d = DetectedObjectBoundingBox3D(
            center=pose3d,
            size_x=0.5,
            size_y=0.3,
            size_z=0.2
        )

        actual_obj = DetectedObject(
            bbox3d=bbox3d,
            class_id="3",
            object_id=123
        )

        outputs = {"object_id_by_class": "obj_ids", "object_pose3D_by_class": "obj_poses"}
        extracted = extract_outputs_from_result(
            ObjectiveNodeType.OBJ_DETECTION, outputs, [actual_obj]
        )

        self.assertEqual(extracted["obj_ids"]["3"], [123])
        expected_pose = {
            "pos_x": 1.0, "pos_y": 2.0, "pos_z": 3.0,
            "quat_x": 0.1, "quat_y": 0.2, "quat_z": 0.3, "quat_w": 0.9
        }
        self.assertEqual(extracted["obj_poses"]["3"][0], expected_pose)

        # Create actual DetectedAprilTag instance instead of mock
        tag_position = Position3D(x=4.0, y=5.0, z=6.0)
        tag_orientation = Quaternion(x=0.4, y=0.5, z=0.6, w=0.8)
        tag_pose = Pose3D(position=tag_position, orientation=tag_orientation)
        tag_center = AprilTagCenter2D(x=320.0, y=240.0)

        actual_tag = DetectedAprilTag(
            tag_id=5,
            family="tag36h11",
            center=tag_center,
            pose=tag_pose,
            frame_id="camera_optical_frame",
            timestamp=1234567890.0
        )

        outputs = {"tags_pose_by_id": "tag_poses"}
        extracted = extract_outputs_from_result(
            ObjectiveNodeType.APRILTAG_DETECTION, outputs, [actual_tag]
        )

        expected_tag_pose = {
            "pos_x": 4.0, "pos_y": 5.0, "pos_z": 6.0,
            "quat_x": 0.4, "quat_y": 0.5, "quat_z": 0.6, "quat_w": 0.8
        }
        self.assertEqual(extracted["tag_poses"]["5"], expected_tag_pose)

    def test_offset_functionality(self):
        """Test offset application in PickPlace parameters"""
        # Test with positive offsets
        params = PickPlaceNodeSchema(
            robot_name="arm01",
            object_id=123,
            class_id="3",
            pos_x=1.0, pos_y=2.0, pos_z=3.0,
            pos_x_offset=0.1, pos_y_offset=0.2, pos_z_offset=0.3,
            quat_x=0.0, quat_y=0.0, quat_z=0.0, quat_w=1.0,
            yaw_offset=math.pi/4  # 45 degree rotation around Z-axis
        )

        result = params.apply_offsets()

        # Test position offsets
        self.assertEqual(result.pos_x, 1.1)
        self.assertEqual(result.pos_y, 2.2)
        self.assertEqual(result.pos_z, 3.3)
        # Test rotation offset - a 45 degree yaw rotation should result in specific values
        # Use scipy to calculate expected values for accuracy
        expected_rotation = R.from_euler("xyz", [0, 0, math.pi/4])
        expected_quat = expected_rotation.as_quat(canonical=True)  # returns [x, y, z, w]
        self.assertAlmostEqual(result.quat_x, expected_quat[0], places=6)
        self.assertAlmostEqual(result.quat_y, expected_quat[1], places=6)
        self.assertAlmostEqual(result.quat_z, expected_quat[2], places=6)
        self.assertAlmostEqual(result.quat_w, expected_quat[3], places=6)

        # Test with negative offsets
        params.pos_z_offset = -0.5
        result = params.apply_offsets()
        self.assertEqual(result.pos_z, 2.5)

        # Test with no rotation offset (identity)
        params_no_rotation = PickPlaceNodeSchema(
            robot_name="arm01",
            object_id=123,
            class_id="3",
            pos_x=1.0, pos_y=2.0, pos_z=3.0,
            quat_x=0.0, quat_y=0.0, quat_z=0.0, quat_w=1.0
        )
        result_no_rotation = params_no_rotation.apply_offsets()
        self.assertAlmostEqual(result_no_rotation.quat_x, 0.0, places=6)
        self.assertAlmostEqual(result_no_rotation.quat_y, 0.0, places=6)
        self.assertAlmostEqual(result_no_rotation.quat_z, 0.0, places=6)
        self.assertAlmostEqual(result_no_rotation.quat_w, 1.0, places=6)

    def test_integrated_workflow(self):
        """Test complete workflow: context resolution + offset application"""
        # Setup context with flattened pose data
        tag_pose = {
            "pos_x": 5.0, "pos_y": 6.0, "pos_z": 7.0,
            "quat_x": 0.1, "quat_y": 0.2, "quat_z": 0.3, "quat_w": 0.9
        }
        object_ids = {"3": [456]}

        self.context.set_variable("tag_poses", [tag_pose])
        self.context.set_variable("object_ids", object_ids)

        # Parameters with context references and offsets
        raw_params = {
            "robot_name": "arm01",
            "object_id": "$object_ids['3'][0]",
            "class_id": "3",
            "pos_x": "$tag_poses[0].pos_x",
            "pos_y": "$tag_poses[0].pos_y",
            "pos_z": "$tag_poses[0].pos_z",
            "pos_z_offset": 0.35,
            "quat_x": 0.996, "quat_y": 0.066, "quat_z": 0.042, "quat_w": 0.034
        }

        # Resolve context
        resolved_params = self.context.resolve_parameters(raw_params)

        # Create schema and apply offsets
        schema = PickPlaceNodeSchema(**resolved_params)
        final_params = schema.apply_offsets()

        # Verify final values
        self.assertEqual(final_params.object_id, 456)
        self.assertEqual(final_params.pos_x, 5.0)
        self.assertEqual(final_params.pos_y, 6.0)
        self.assertEqual(final_params.pos_z, 7.35)  # 7.0 + 0.35 offset

    def test_2d_and_3d_pose_extractors(self):
        """Test 2D and 3D pose extractors using actual objects instead of mocks"""
        # Create actual DetectedObject with 2D bounding box
        center_2d = DetectedObjectCenter2D(x=460.071, y=332.274, theta=0.0)
        bbox2d = DetectedObjectBoundingBox2D(
            center=center_2d,
            size_x=100.0,
            size_y=150.0
        )

        actual_obj_2d = DetectedObject(
            bbox2d=bbox2d,
            bbox3d=None,  # No 3D bbox for this test
            class_id="3",
            object_id=123
        )

        # Test 2D pose extractor
        outputs = {"object_pose2D_by_class": "obj_poses_2d"}
        extracted = extract_outputs_from_result(
            ObjectiveNodeType.OBJ_DETECTION, outputs, [actual_obj_2d]
        )

        self.assertEqual(len(extracted["obj_poses_2d"]["3"]), 1)
        pose_2d = extracted["obj_poses_2d"]["3"][0]
        self.assertEqual(pose_2d["x"], 460.071)
        self.assertEqual(pose_2d["y"], 332.274)
        self.assertEqual(pose_2d["theta"], 0.0)


if __name__ == "__main__":
    unittest.main()
