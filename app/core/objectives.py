import asyncio
import uuid
import logging
from typing import Optional

import pydantic
import py_trees
from app.core.objective_behavior_tree import ObjectiveBehaviorTree, ObjectiveLeafNode
from app.core.mission_control import MissionControl
from app.common.models import MissionData, PickPlaceData
from cloud_common.objects.common import ICSServerError
from cloud_common.objects.objective import ObjectiveV1, ObjectiveStateV1, ObjectiveNodeType, ObjectiveNode


class NavigationNodeSchema(MissionData):
    """Represents the parameters for a Navigation Node"""
    robot_name: str = ""


class PickPlaceNodeSchema(PickPlaceData):
    """Represents the parameters for a PickPlace Node"""
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


class ObjectiveServer:
    """The Objective Server will run one Objective to completion"""

    def __init__(self, name: str, objective: ObjectiveV1):
        self.name = name
        self.objective = objective
        self.mc = MissionControl.get_instance()
        self.logger = logging.getLogger("Isaac Mission Control")
        self.running_nodes: list[ObjectiveLeafNode] = []
        self.behavior_tree = ObjectiveBehaviorTree(objective, self.running_nodes)
        self.loop = asyncio.get_event_loop()
        self.task = self.loop.create_task(self.run_tree_to_completion())

    async def run_tree_to_completion(self):
        try:
            self.logger.info("Running objective tree")
            self.objective.status.state = ObjectiveStateV1.RUNNING
            self.behavior_tree.update()
            while not self.behavior_tree.has_completed:
                pending_mission_data = []
                for curr_bt_node in self.running_nodes:
                    self.logger.debug("Processing node: %s", str(curr_bt_node.objective_node))
                    if isinstance(curr_bt_node, ObjectiveLeafNode):
                        # Mission Control currently does not send mission_id to Dispatch
                        mission_id = str(uuid.uuid4())
                        objective_node = curr_bt_node.objective_node
                        objective_node.state = ObjectiveStateV1.RUNNING
                        try:
                            if objective_node.node_type == ObjectiveNodeType.NAVIGATION:
                                nav_mission_schema = NavigationNodeSchema(**objective_node.parameters)
                                nav_mission_data = MissionData(**objective_node.parameters)
                                if nav_mission_schema.robot_name:
                                    robot_obj = self.mc.robots.get_robot(nav_mission_schema.robot_name)
                                    self.logger.info(robot_obj)
                                    self.logger.info(nav_mission_data)
                                    pending_mission_data.append(self.mc.submit_navigation_mission(
                                        mission_id=mission_id, mission_data=nav_mission_data,
                                        mandatory_robot=robot_obj))
                                else:
                                    pending_mission_data.append(self.mc.submit_navigation_mission(
                                        mission_id=mission_id, mission_data=nav_mission_data))
                            elif objective_node.node_type == ObjectiveNodeType.CHARGING:
                                charging_parameters = ChargingNodeSchema(**objective_node.parameters)
                                robot_obj = self.mc.robots.get_robot(charging_parameters.robot_name)
                                pending_mission_data.append(self.mc.submit_charging_mission(
                                    mission_id=mission_id, robot=robot_obj,
                                    dock_id=charging_parameters.dock_id))
                            elif objective_node.node_type == ObjectiveNodeType.UNDOCK:
                                undock_parameters = UndockNodeSchema(**objective_node.parameters)
                                robot_obj = self.mc.robots.get_robot(undock_parameters.robot_name)
                                pending_mission_data.append(self.mc.submit_undock_mission(
                                    robot=robot_obj))
                            elif objective_node.node_type == ObjectiveNodeType.PICKPLACE:
                                pickplace_parameters = PickPlaceNodeSchema(**objective_node.parameters)
                                robot_obj = self.mc.robots.get_robot(pickplace_parameters.robot_name)
                                pending_mission_data.append(
                                    self.mc.submit_pickplace_mission(mission_id=mission_id, robot=robot_obj,
                                                                    pick_place_data=pickplace_parameters))
                        except Exception as e:  # pylint: disable=bare-except
                            self.logger.error("Error when creating mission for %s: %s", str(objective_node), str(e))
                            await self.fail(failed_node=objective_node, error_msg=str(e))
                            return
                    else:
                        self.logger.error("Internal error - Current node is not leaf node")
                        await self.fail(error_msg="Internal error - Current node is not leaf node")
                        return
                # Wait for all missions to be sent, fail objective if one fails
                results = await asyncio.gather(*pending_mission_data, return_exceptions=True)

                # Check if any mission failed. If so, fail the objective.
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        await self.fail(failed_node=self.running_nodes[i].objective_node, error_msg=str(result))
                        return

                for i, result in enumerate(results):
                    self.running_nodes[i].objective_node.mission_id = result.sub_mission_uuids[0]
                    self.running_nodes[i].objective_node.robot = result.robots[0]
                # Update objective in database
                _ = await self.mc.mission_database_client.update_objective(self.objective)

                # await mission completed, then update bt
                missions_completed = []
                for i in range(len(self.running_nodes)):
                    if self.running_nodes[i].objective_node.mission_id:
                        mission_id = self.running_nodes[i].objective_node.mission_id
                        missions_completed.append(self.mc.wait_for_mission_wrapper(mission_id, i))

                for coro in asyncio.as_completed(missions_completed):
                    try:
                        mission_completed, i = await coro
                        if mission_completed:
                            self.running_nodes[i].objective_node.state = ObjectiveStateV1.COMPLETED
                        else:
                            self.running_nodes[i].objective_node.state = ObjectiveStateV1.FAILED
                    except:  # pylint: disable=bare-except
                        # Add error handling here
                        self.running_nodes[i].objective_node.state = ObjectiveStateV1.FAILED
                    _ = await self.mc.mission_database_client.update_objective(self.objective)

                # After nodes are done, clear running nodes list and update tree to get next nodes
                self.running_nodes.clear()
                self.behavior_tree.update()
                _ = await self.mc.mission_database_client.update_objective(self.objective)

                # Need this for real world. When mission complete,
                # robot state doesn't immediately switch to IDLE.
                await asyncio.sleep(5)
            # Set objective final state
            if self.behavior_tree.root.status == py_trees.common.Status.SUCCESS:
                self.objective.status.state = ObjectiveStateV1.COMPLETED
            else:
                await self.fail(error_msg="Objective failed")
                return
            _ = await self.mc.mission_database_client.update_objective(self.objective)
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
        self.cancel()


class ObjectiveExecutor:
    """ Class to orchestrate running objectives """
    _instance = None

    @staticmethod
    def get_instance():
        """ Static access method. """
        if not ObjectiveExecutor._instance:
            raise ICSServerError("Objective Executor")
        return ObjectiveExecutor._instance

    def __init__(self):
        self.active_objectives = set()
        self.objective_servers: dict[str, ObjectiveServer] = {}
        self.logger = logging.getLogger("Isaac Mission Control")
        ObjectiveExecutor._instance = self

    def run_objective(self, objective: ObjectiveV1):
        self.logger.info("Running objective")
        self.objective_servers[objective.name] = ObjectiveServer(name=objective.name, objective=objective)
        self.active_objectives.add(self.objective_servers[objective.name])
        self.logger.info("Active objectives: %s", str(self.active_objectives))

    def cancel_objective(self, objective: ObjectiveV1):
        self.logger.info("Cancelling objective")
        self.objective_servers[objective.name].cancel()
        self.logger.info("Active objectives: %s", str(self.active_objectives))
