"""
SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.

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

import asyncio
import uuid
import logging
import threading
from typing import Optional
from datetime import datetime, timedelta

import pydantic.v1 as pydantic
import py_trees
import httpx
from scipy.spatial.transform import Rotation as R
from app.core.objectives.objective_behavior_tree import ObjectiveBehaviorTree
from app.core.objectives.objectives_common import ObjectiveLeafNode
from app.core.mission_control import MissionControl
from app.common.models import MissionData, PickPlaceData, MultiObjectPickPlaceData
from cloud_common.objects.common import ICSServerError, Pose3D
from cloud_common.objects.objective import ObjectiveV1, ObjectiveStateV1, ObjectiveNodeType, ObjectiveNode
from app.core.objectives.objectives_context import (
    ObjectivesContext, 
    ContextAccessError, 
    validate_output_extractors,
    extract_outputs_from_result
)
from cloud_common.objects.mission import MissionStateV1
from app.api.clients.mission_database_client import MissionDatabaseClient

class NavigationNodeSchema(MissionData):
    """Represents the parameters for a Navigation Node"""
    robot_name: str = ""


class PickPlaceNodeSchema(PickPlaceData):
    """Represents the parameters for a PickPlace Node"""
    robot_name: str
    
    # Offset parameters (optional, default 0) - applied before mission execution
    # Position offsets in meters
    pos_x_offset: float = 0.0
    pos_y_offset: float = 0.0
    pos_z_offset: float = 0.0
    
    # Angular offsets in radians (Euler angles: roll, pitch, yaw)
    roll_offset: float = 0.0   # Rotation around X-axis in radians
    pitch_offset: float = 0.0  # Rotation around Y-axis in radians
    yaw_offset: float = 0.0    # Rotation around Z-axis in radians
    
    def apply_offsets(self) -> PickPlaceData:
        """Apply offset parameters to base values before mission execution.
        
        Applies translational offsets (pos_x_offset, pos_y_offset, pos_z_offset) in meters
        to the base position coordinates. Converts user-friendly Euler angle offsets 
        (roll_offset, pitch_offset, yaw_offset) in radians to quaternion representation
        and composes them with the base quaternion orientation.
        
        Returns:
            PickPlaceData with offsets applied and offset parameters removed
        """
        # Apply position offsets
        final_pos_x = self.pos_x + self.pos_x_offset
        final_pos_y = self.pos_y + self.pos_y_offset
        final_pos_z = self.pos_z + self.pos_z_offset
        
        # Convert Euler angle offsets to rotation matrix then to quaternion
        if self.roll_offset != 0 or self.pitch_offset != 0 or self.yaw_offset != 0:
            # Create rotation from Euler angles (intrinsic XYZ order)
            offset_rotation = R.from_euler('xyz', [self.roll_offset, self.pitch_offset, self.yaw_offset])
            
            # Current orientation as rotation object
            current_rotation = R.from_quat([self.quat_x, self.quat_y, self.quat_z, self.quat_w])
            
            # Apply rotation offset by composing rotations
            final_rotation = current_rotation * offset_rotation
            
            # Convert back to quaternion (scipy returns x, y, z, w order)
            final_quat = final_rotation.as_quat()
            final_quat_x, final_quat_y, final_quat_z, final_quat_w = final_quat
        else:
            # No rotation offset, keep original quaternion
            final_quat_x = self.quat_x
            final_quat_y = self.quat_y
            final_quat_z = self.quat_z
            final_quat_w = self.quat_w
        
        # Create base PickPlaceData with offsets applied
        return PickPlaceData(
            object_id=self.object_id,
            class_id=self.class_id,
            pos_x=final_pos_x,
            pos_y=final_pos_y,
            pos_z=final_pos_z,
            quat_x=final_quat_x,
            quat_y=final_quat_y,
            quat_z=final_quat_z,
            quat_w=final_quat_w
        )

class MultiObjectPickPlaceNodeSchema(MultiObjectPickPlaceData):
    """Represents the parameters for a MultiObjectPickPlace Node"""
    robot_name: str

class ChargingNodeSchema(pydantic.BaseModel):
    """Represents the parameters for a Charging Node"""
    robot_name: str
    dock_id: Optional[str] = None

class UndockNodeSchema(pydantic.BaseModel):
    """Represents the parameters for a Undock Node"""
    robot_name: str

class ObjDetectionNodeSchema(pydantic.BaseModel):
    """Represents the parameters for a ObjDetection Node"""
    robot_name: str

class AprilTagDetectionNodeSchema(pydantic.BaseModel):
    """Represents the parameters for an AprilTag Detection Node"""
    robot_name: str

class SleepNodeSchema(pydantic.BaseModel):
    """Represents the parameters for a Sleep Node"""
    duration: float

class ObjectiveServer:
    """The Objective Server will run one Objective to completion"""

    def __init__(self, name: str, objective: ObjectiveV1):
        self.name = name
        self.objective = objective
        self.mc = MissionControl.get_instance()
        self.logger = logging.getLogger("Isaac Mission Control")
        self.running_nodes: list[ObjectiveLeafNode] = []
        
        # Initialize context (handles both storage and resolution)
        self.context = ObjectivesContext()
            
        self.behavior_tree = ObjectiveBehaviorTree(objective, self.running_nodes)
        self.loop = asyncio.get_event_loop()
        self.task = self.loop.create_task(self.run_tree_to_completion())

    async def extract_and_store_outputs(self, node, mission_id: str):
        """Extract outputs after mission completion and store in context"""
        
        if not hasattr(node, 'outputs') or not node.outputs:
            return
            
        self.logger.debug(f"Extracting outputs for node {node.node_type}: {node.outputs}")
        
        # Validate that all output keys are allowed output extractor keys
        validate_output_extractors(node.node_type, node.outputs)
        
        # Get mission results based on node type
        try:
            if node.node_type == ObjectiveNodeType.OBJ_DETECTION:
                robot_name = node.parameters["robot_name"]
                # Retrieve already-stored detection results from database
                detector = await self.mc.mission_database_client.get_detection_results(robot_name)
                result = detector.status.detected_objects
                
            elif node.node_type == ObjectiveNodeType.APRILTAG_DETECTION:
                robot_name = node.parameters["robot_name"]
                # Retrieve already-stored AprilTag results from database
                detector = await self.mc.mission_database_client.get_apriltag_results(robot_name)
                result = detector.status.detected_apriltags
                
            else:
                # For other node types, result is just empty for now
                result = {}
                
            # Extract outputs using output extractors
            extracted_values = extract_outputs_from_result(node.node_type, node.outputs, result)
            
            # Store all extracted values in context
            for context_var_name, value in extracted_values.items():
                self.context.set_variable(context_var_name, value)
                self.logger.info(f"Stored {context_var_name} = {value}")
                    
        except Exception as e:
            self.logger.error(f"Failed to get mission results for output extraction: {e}")
            # Don't fail the mission just because we couldn't get results

    async def check_mission_completion(self, mission_id: str) -> bool:
        """Non-blocking check whether a mission has reached a terminal state.

        Example:
            await self.check_mission_completion("123") -> True
        """
        try:
            mission = await self.mc.mission_database_client.get_mission(mission_id)
            return mission.status.state.done
        except Exception as e:
            self.logger.error(f"Error checking mission {mission_id} completion: {e}")
            return False

    async def is_mission_successful(self, mission_id: str) -> bool:
        """Return True if the mission finished successfully (COMPLETED).

        Example:
            await self.is_mission_successful("123") -> True
        """
        try:
            mission = await self.mc.mission_database_client.get_mission(mission_id)
            return mission.status.state == MissionStateV1.COMPLETED
        except Exception as e:
            self.logger.error(f"Error getting mission {mission_id} result: {e}")
            return False

    def get_new_running_nodes(self, active_missions: dict) -> list:
        """Get nodes that are running but don't have active missions yet"""
        active_nodes = set(active_missions.values())
        return [node for node in self.running_nodes if node not in active_nodes]

    async def create_missions_for_nodes(self, nodes: list) -> dict:
        """Create and start missions for a list of nodes, returns mission_id -> node mapping"""
        if not nodes:
            return {}
            
        mission_mapping = {}
        pending_mission_data = []
        
        # STEP 1: Resolve dynamic parameters for all nodes before mission creation
        for curr_bt_node in nodes:
            if isinstance(curr_bt_node, ObjectiveLeafNode):
                node_type = curr_bt_node.objective_node.node_type
                self.logger.info(f"Resolving parameters for {node_type} node")
                try:
                    # Resolve ${context.*} references in parameters
                    if hasattr(curr_bt_node.objective_node, 'parameters'):
                        original_params = curr_bt_node.objective_node.parameters.copy()
                        self.logger.debug(f"Original parameters for {node_type}: {original_params}")
                        
                        resolved_params = self.context.resolve_parameters(
                            curr_bt_node.objective_node.parameters
                        )
                        self.logger.debug(f"Resolved parameters for {node_type}: {resolved_params}")
                        
                        # Log parameter changes
                        for key, value in resolved_params.items():
                            if str(value) != str(original_params.get(key)):
                                self.logger.debug(f"Resolved parameter {key}: {original_params.get(key)} -> {value}")
                        
                        curr_bt_node.objective_node.parameters = resolved_params
                except ContextAccessError as e:
                    self.logger.error(f"Context resolution failed for {curr_bt_node.objective_node.node_type}: {e}")
                    await self.fail(failed_node=curr_bt_node.objective_node, error_msg=str(e))
                    return {}
        
        # STEP 2: Create missions with resolved parameters
        for curr_bt_node in nodes:
            if isinstance(curr_bt_node, ObjectiveLeafNode):
                objective_node = curr_bt_node.objective_node
                objective_node.state = ObjectiveStateV1.RUNNING
                
                node_type = objective_node.node_type
                robot_name = objective_node.parameters.get('robot_name', 'unknown')
                self.logger.info(f"Creating {node_type} mission for robot '{robot_name}'")
                
                try:
                    if objective_node.node_type == ObjectiveNodeType.NAVIGATION:
                        nav_mission_schema = NavigationNodeSchema(**objective_node.parameters)
                        nav_mission_data = MissionData(**objective_node.parameters)
                        if nav_mission_schema.robot_name:
                            robot_obj = self.mc.robots.get_robot(nav_mission_schema.robot_name)
                            self.logger.debug(f"Navigation robot object: {robot_obj}")
                            self.logger.debug(f"Navigation mission data: {nav_mission_data}")
                            pending_mission_data.append(self.mc.submit_navigation_mission(
                                mission_data=nav_mission_data,
                                mandatory_robot=robot_obj))
                        else:
                            pending_mission_data.append(self.mc.submit_navigation_mission(
                                mission_data=nav_mission_data))
                    elif objective_node.node_type == ObjectiveNodeType.CHARGING:
                        charging_parameters = ChargingNodeSchema(**objective_node.parameters)
                        robot_obj = self.mc.robots.get_robot(charging_parameters.robot_name)
                        pending_mission_data.append(self.mc.submit_charging_mission(
                            robot=robot_obj,
                            dock_id=charging_parameters.dock_id))
                    elif objective_node.node_type == ObjectiveNodeType.UNDOCK:
                        undock_parameters = UndockNodeSchema(**objective_node.parameters)
                        robot_obj = self.mc.robots.get_robot(undock_parameters.robot_name)
                        pending_mission_data.append(self.mc.submit_undock_mission(
                            robot=robot_obj))
                    elif objective_node.node_type == ObjectiveNodeType.PICKPLACE:
                        self.logger.debug(f"Starting PICKPLACE mission creation with parameters: {objective_node.parameters}")
                        try:
                            pickplace_parameters = PickPlaceNodeSchema(**objective_node.parameters)                            
                            robot_obj = self.mc.robots.get_robot(pickplace_parameters.robot_name)                            
                            # Apply offsets to get final PickPlaceData
                            final_pickplace_data = pickplace_parameters.apply_offsets()
                            
                            self.logger.debug(f"Pick and place: object {final_pickplace_data.object_id} (class {final_pickplace_data.class_id})")
                            self.logger.debug(f"Target position: ({final_pickplace_data.pos_x:.3f}, {final_pickplace_data.pos_y:.3f}, {final_pickplace_data.pos_z:.3f})")
                            pickplace_result = self.mc.submit_pickplace_mission(robot=robot_obj, pick_place_data=final_pickplace_data)
                            self.logger.debug(f"PICKPLACE mission submission returned: {pickplace_result}")
                            self.logger.debug(f"PICKPLACE result type: {type(pickplace_result)}")
                            pending_mission_data.append(pickplace_result)
                        except Exception as pickplace_exception:
                            self.logger.error(f"Exception during PICKPLACE mission creation: {str(pickplace_exception)}", exc_info=True)
                            raise
                    elif objective_node.node_type == ObjectiveNodeType.MULTI_OBJECT_PICKPLACE:
                        multi_object_pickplace_parameters = MultiObjectPickPlaceNodeSchema(**objective_node.parameters)
                        robot_obj = self.mc.robots.get_robot(multi_object_pickplace_parameters.robot_name)
                        pending_mission_data.append(self.mc.submit_multi_object_pickplace_mission(
                            robot=robot_obj, multi_object_pickplace_data=multi_object_pickplace_parameters))
                    elif objective_node.node_type == ObjectiveNodeType.OBJ_DETECTION:
                        obj_detection_parameters = ObjDetectionNodeSchema(**objective_node.parameters)
                        robot_obj = self.mc.robots.get_robot(obj_detection_parameters.robot_name)
                        
                        pending_mission_data.append(self.mc.submit_obj_detection_mission(robot_obj))
                        
                    elif objective_node.node_type == ObjectiveNodeType.APRILTAG_DETECTION:
                        apriltag_detection_parameters = AprilTagDetectionNodeSchema(**objective_node.parameters)
                        robot_obj = self.mc.robots.get_robot(apriltag_detection_parameters.robot_name)
                        
                        pending_mission_data.append(self.mc.submit_apriltag_detection_mission(robot_obj))
                    elif objective_node.node_type == ObjectiveNodeType.SLEEP:
                        sleep_parameters = SleepNodeSchema(**objective_node.parameters)
                        sleep_mission_id = str(uuid.uuid4())
                        objective_node.mission_id = sleep_mission_id
                        objective_node.robot = "N/A"
                        end_timestamp = datetime.now() + timedelta(seconds=sleep_parameters.duration)
                        objective_node.parameters["end_timestamp"] = end_timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')
                        objective_node.parameters["robot_name"] = "N/A"
                        mission_mapping[sleep_mission_id] = curr_bt_node
                        
                except Exception as e:  # pylint: disable=bare-except
                    self.logger.error("Error when creating mission for %s: %s", str(objective_node), str(e))
                    await self.fail(failed_node=objective_node, error_msg=str(e))
                    return {}
            else:
                self.logger.error("Internal error - Current node is not leaf node")
                await self.fail(error_msg="Internal error - Current node is not leaf node")
                return {}
        
        # Wait for all missions to be sent, fail objective if one fails
        try:
            results = await asyncio.gather(*pending_mission_data, return_exceptions=True)
        except Exception as e:
            self.logger.error(f"Error gathering mission creation results: {e}")
            return {}

        # Check if any mission failed. If so, fail the objective.
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                node_type = nodes[i].objective_node.node_type
                self.logger.error(f"Mission submission failed for {node_type}: {str(result)}")
                await self.fail(failed_node=nodes[i].objective_node, error_msg=str(result))
                return {}

        # Assign mission IDs and robots
        for i, result in enumerate(results):
            mission_id = result.sub_mission_uuids[0]
            nodes[i].objective_node.mission_id = mission_id
            nodes[i].objective_node.robot = result.robots[0]
            mission_mapping[mission_id] = nodes[i]
            
            node_type = nodes[i].objective_node.node_type
            robot = result.robots[0]
            self.logger.debug(f"{node_type} mission '{mission_id}' assigned to robot '{robot}'")
        
        return mission_mapping

    async def run_tree_to_completion(self):
        """
        Continuous execution algorithm that handles nested composite nodes properly.
        Updates the tree immediately when any mission completes, allowing sequences 
        within parallel nodes to progress through their children.
        """
        try:
            self.logger.info(f"Starting objective execution: {self.objective.name}")
            self.objective.status.state = ObjectiveStateV1.RUNNING
            
            # Initial tree setup
            self.behavior_tree.update()
            
            # Track active missions: mission_id -> ObjectiveLeafNode
            active_missions = {}
            
            while not self.behavior_tree.has_completed:
                # PHASE 1: Start missions for any newly running leaf nodes
                new_running_nodes = self.get_new_running_nodes(active_missions)
                
                if new_running_nodes:
                    # Log current running nodes
                    self.logger.info(f"Found {len(new_running_nodes)} new running nodes")
                    node_info = [f"{node.objective_node.node_type}({node.objective_node.parameters.get('robot_name', 'unknown')})" 
                                for node in new_running_nodes]
                    self.logger.info(f"Starting missions for: {', '.join(node_info)}")
                    
                    new_missions = await self.create_missions_for_nodes(new_running_nodes)
                    if self.objective.status.state == ObjectiveStateV1.FAILED:
                        return  # fail() already called, stop execution

                    active_missions.update(new_missions)
                    self.logger.info(f"Started {len(new_missions)} new missions")
                    
                    # Update objective in database after starting new missions
                    await self.mc.mission_database_client.update_objective(self.objective)

                # PHASE 2: Check for mission completions (non-blocking)
                completed_missions = {}
                for mission_id, node in active_missions.items():
                    self.logger.debug(f"Checking mission completion for {node.objective_node.node_type} mission {mission_id}")
                    if node.objective_node.node_type == ObjectiveNodeType.SLEEP:
                        end_timestamp = datetime.strptime(node.objective_node.parameters["end_timestamp"], '%Y-%m-%d %H:%M:%S.%f')
                        self.logger.debug(f"Sleep mission {mission_id} end timestamp: {end_timestamp}")
                        self.logger.debug(f"Sleep mission {mission_id} current time: {datetime.now()}")
                        if datetime.now() >= end_timestamp:
                            self.logger.debug(f"Sleep mission {mission_id} completed")
                            completed_missions[mission_id] = node
                    elif await self.check_mission_completion(mission_id):
                        completed_missions[mission_id] = node
                
                # PHASE 3: Handle completions and update tree
                if completed_missions:
                    self.logger.debug(f"Found {len(completed_missions)} completed missions")
                    
                    # Process each completed mission (equivalent to original asyncio.as_completed loop)
                    for mission_id, node in completed_missions.items():
                        if node.objective_node.node_type == ObjectiveNodeType.SLEEP:
                            mission_success = True
                        else:
                            mission_success = await self.is_mission_successful(mission_id)
                        node_type = node.objective_node.node_type
                        robot = node.objective_node.robot
                        
                        if mission_success:
                            node.objective_node.state = ObjectiveStateV1.COMPLETED
                            self.logger.info(f"{node_type} completed successfully on robot '{robot}'")
                            
                            # STEP 3: Extract and store outputs after successful mission completion
                            try:
                                await self.extract_and_store_outputs(
                                    node.objective_node,
                                    mission_id
                                )
                            except Exception as e:
                                self.logger.error(f"Failed to extract outputs for node {node_type}: {e}")
                                # Don't fail the mission just because output extraction failed
                        else:
                            node.objective_node.state = ObjectiveStateV1.FAILED
                            self.logger.error(f"{node_type} failed on robot '{robot}'")
                        
                        # Remove from active missions
                        del active_missions[mission_id]

                    # Need this for real world. When mission completes,
                    # robot state doesn't immediately update
                    # Sleeping before updating the tree gives time for the robot state to update
                    await asyncio.sleep(1.0)
                    
                    # After nodes are done, clear running nodes list and update tree to get next nodes
                    self.running_nodes.clear()
                    self.behavior_tree.update()
                    
                    # Update objective in database after tree update
                    await self.mc.mission_database_client.update_objective(self.objective)
                    
                    self.logger.debug(f"Processed {len(completed_missions)} completed missions, tree updated")
                
                # PHASE 5: Short sleep to prevent busy waiting 
                await asyncio.sleep(0.5)
            
            # Set objective final state
            if self.behavior_tree.root.status == py_trees.common.Status.SUCCESS:
                self.objective.status.state = ObjectiveStateV1.COMPLETED
                self.logger.info(f"Objective completed successfully: {self.objective.name}")
            else:
                self.logger.error(f"Objective failed: {self.objective.name}")
                await self.fail(error_msg="Objective failed")
                return
                
            await self.mc.mission_database_client.update_objective(self.objective)
            self.remove_objective_from_executor()
            return
            
        except asyncio.CancelledError:
            self.logger.info("Objective %s cancelled", self.name)
            await self.fail(error_msg="Objective cancelled")
            return

    async def fail(self, failed_node: Optional[ObjectiveNode] = None,
                   error_msg: Optional[str] = None):
        if failed_node:
            failed_node.state = ObjectiveStateV1.FAILED
        if error_msg:
            self.objective.status.errors.append(error_msg)
        self.objective.status.state = ObjectiveStateV1.FAILED
        _ = await self.mc.mission_database_client.update_objective(self.objective)
        self.remove_objective_from_executor()

    def cancel(self):
        if hasattr(self, 'task') and self.task:
            self.task.cancel()

    def remove_objective_from_executor(self):
        if self in ObjectiveExecutor.get_instance().active_objectives:
            ObjectiveExecutor.get_instance().active_objectives.remove(self)
            del ObjectiveExecutor.get_instance().objective_servers[self.name]

    @property
    def state(self):
        return self.objective.status.state
    
    def __del__(self):
        # If the ObjectiveServer instance is deleted, cancel the task
        # This is to ensure that the task is not running after the instance is deleted
        try:
            self.cancel()
        except Exception:
            pass  # Ignore any errors during cleanup


class ObjectiveExecutor:
    """ Class to orchestrate running objectives """
    _instance = None

    @staticmethod
    def get_instance():
        """ Static access method. """
        if not ObjectiveExecutor._instance:
            raise ICSServerError("Objective Executor not ready.")
        return ObjectiveExecutor._instance

    def __init__(self):
        self.active_objectives = set()
        self.objective_servers: dict[str, ObjectiveServer] = {}

        # Initialize database thread and event loop
        self.mc_config = MissionControl.get_instance().config
        self.database_event_loop = asyncio.new_event_loop()
        self.async_client = None
        self.database_client = None
        self.database_thread = threading.Thread(target=self.run_database_thread, daemon=True)
        self.database_thread.start()

        self.logger = logging.getLogger("Isaac Mission Control")
        ObjectiveExecutor._instance = self

    def run_database_thread(self):
        # This thread is specific to the ObjectiveExecutor and is responsible for
        # running its own event loop for the database client.
        # Currently it is being used when ticking the Conditional Decorator node
        asyncio.set_event_loop(self.database_event_loop)
        self.async_client = httpx.AsyncClient()
        self.database_client = MissionDatabaseClient(
            self.mc_config.get_mission_database_config(), self.async_client)
        try:
            self.database_event_loop.run_forever()
        finally:
            self.database_event_loop.close()

    def run_objective(self, objective: ObjectiveV1):
        self.logger.info("Running objective")
        self.objective_servers[objective.name] = ObjectiveServer(name=objective.name, objective=objective)
        self.active_objectives.add(self.objective_servers[objective.name])
        self.logger.info("Active objectives: %s", str(self.active_objectives))

    def cancel_objective(self, objective: ObjectiveV1):
        self.logger.info("Cancelling objective")
        self.objective_servers[objective.name].cancel()
        self.logger.info("Active objectives: %s", str(self.active_objectives))

    async def close(self):
        future = asyncio.run_coroutine_threadsafe(
            self.async_client.aclose(), self.database_event_loop)
        await asyncio.wrap_future(future)

        self.database_event_loop.call_soon_threadsafe(self.database_event_loop.stop)
        self.database_thread.join()
