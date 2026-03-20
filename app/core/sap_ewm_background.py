# Copyright (c) 2025-2026, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import asyncio
import logging
import uuid
import httpx
import ssl
from typing import Optional, Dict, Any, List
from app.api.clients.sap_ewm_client import SapEwmService
from cloud_common.objects.common import ICSError, Point2D
from cloud_common.objects.robot import RobotObjectV1
from app.common.models import MissionData

logger = logging.getLogger("Isaac Mission Control")


class SapEwmBackgroundTask:
    """Background task system for SAP EWM integration that automates order processing"""

    def __init__(self, mission_control):
        self.mc = mission_control
        self.running = False
        self.current_order: Optional[Dict[str, Any]] = None
        # task_id -> task_info
        self.active_tasks: Dict[str, Dict[str, Any]] = {}
        self.sap_service: Optional[SapEwmService] = None
        self.available_robots: List[RobotObjectV1] = []
        # Track which robot is assigned to which order
        self.order_robot_assignments: Dict[str, str] = {}
        # Track total number of orders processed
        self.orders_processed_count: int = 0
        # Maximum number of orders to process (0 = unlimited)
        self.max_orders_to_process: int = 1
        logger.debug("SapEwmBackgroundTask initialized")

    async def start(self):
        """Start the background task system"""
        if self.running:
            logger.warning("SAP EWM background task is already running")
            return

        self.running = True
        logger.info("Starting SAP EWM background task system")
        logger.debug("Initializing SAP service with custom SSL context")

        # Create SAP service
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        client = httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(
                retries=3,
                verify=False
            ),
            timeout=60.0
        )

        # Get SAP configuration
        sap_config = self.mc.config.get_sap_config()
        self.sap_service = SapEwmService(client, sap_config)

        config_max_orders = sap_config.max_orders_to_process

        # Only update if config has a non-zero value (0 means unlimited in config
        if config_max_orders > 0:
            self.max_orders_to_process = config_max_orders

        logger.info(f"Maximum orders to process set to: \
            {self.max_orders_to_process if self.max_orders_to_process > 0 else 'unlimited'}")

        logger.debug("SAP service initialized successfully")

        # Start the main processing loop
        logger.debug("Creating main processing loop task")
        asyncio.create_task(self._process_loop())

    async def stop(self):
        """Stop the background task system"""
        if not self.running:
            logger.warning("SAP EWM background task is not running")
            return

        self.running = False
        logger.info("Stopping SAP EWM background task system")

        if self.sap_service:
            logger.debug("Closing SAP service client")
            await self.sap_service.client.aclose()
            self.sap_service = None
            logger.debug("SAP service client closed")

    async def _update_available_robots(self):
        """Update the list of available robots"""
        try:
            logger.debug("Updating available robots list")
            # Get all robots from the database
            params = {
                "state": "IDLE",
                "online": True,
                "min_battery": self.mc.constants.MIN_BATTERY,
                "position_initialized": True,
            }
            logger.debug(f"Querying robots with params: {params}")
            self.available_robots = await self.mc.mission_database_client.get_robots(params)
            logger.info(f"Found {len(self.available_robots)} available robots")
            logger.debug(
                f"Available robots: {[robot.name for robot in self.available_robots]}")
        except Exception as e:
            logger.error(f"Error updating available robots: {e}")
            self.available_robots = []

    async def _process_task(self, task: Dict[str, Any], robot: RobotObjectV1, is_first_task: bool = False):
        """Process a single task with a specific robot"""
        task_id = f"{task['WarehouseTask']}_{task['WarehouseTaskItem']}"
        robot_name = robot.name if robot else 'None'
        logger.debug(
            f"Starting to process task {task_id} with robot {robot_name}")

        self.active_tasks[task_id] = {
            "task": task,
            "robot": robot_name,
            "status": "processing"
        }
        logger.debug(f"Task {task_id} added to active tasks")

        try:
            # Create and submit mission
            logger.debug(f"Creating navigation mission for task {task_id}")
            sap_mission = await self.sap_service.create_navigation_mission_from_task(task)
            logger.debug(f"Created SAP mission: {sap_mission.get('id')}")
            logger.debug(f"SAP mission details: {sap_mission}")

            # Convert sap_mission directly to MissionData
            mission_data = MissionData(
                route=[Point2D(x=point["x"], y=point["y"])
                       for point in sap_mission.get("route", [])]
            )
            logger.debug(f"Converted to Mission Control Data: {mission_data}")

            # Submit navigation mission - this will handle robot selection through CUOPT internally
            result = await self.mc.submit_navigation_mission(mission_data, robot)
            logger.debug(f"Navigation mission submitted with result: {result}")

            # For the first task in an order, store the assigned robot for subsequent tasks
            if is_first_task:
                if result and result.robots:
                    # Update the robot assignment for this order
                    order_number = task['WarehouseOrder']
                    robot_name = result.robots[0]
                    self.order_robot_assignments[order_number] = robot_name
                    logger.info(f"Using robot {robot_name} for all tasks in order {order_number}")

                    # Send assignment to SAP EWM
                    try:
                        await self._assign_robot_to_order(robot_name, order_number)
                    except Exception as e:
                        logger.error(
                            f"Failed to assign robot {robot_name} to order {order_number}: {e}")
                        # Continue with the assignment anyway

            # Check if we have sub_mission_uuids in the result
            if not result or not result.sub_mission_uuids:
                logger.error(
                    f"No sub_mission_uuids returned for task {task_id}")
                self.active_tasks[task_id]["status"] = "failed"
                return

            # Wait for mission completion
            # Use the first sub-mission UUID
            mission_id = result.sub_mission_uuids[0]
            if mission_id:
                logger.debug(f"Waiting for mission {mission_id} to complete")
                # Use index 0 since we're only waiting for one mission
                mission_done = await self.mc.wait_for_mission_wrapper(mission_id, 0)
                logger.debug(f"Mission {mission_id} completed: {mission_done}")

                # Confirm task if mission is done
                if mission_done:
                    # Confirm task completion
                    logger.debug(f"Confirming warehouse task {task_id}")
                    await self.sap_service.confirm_warehouse_task(
                        task["WarehouseTask"],
                        task["WarehouseTaskItem"]
                    )
                    logger.debug(f"Warehouse task {task_id} confirmed")
                    self.active_tasks[task_id]["status"] = "completed"
                    logger.debug(f"Task {task_id} marked as completed")
                else:
                    logger.warning(f"Mission {mission_id} did not complete, not confirming task")
                    self.active_tasks[task_id]["status"] = "failed"
            else:
                logger.error(f"No mission_id returned for task {task_id}")
                self.active_tasks[task_id]["status"] = "failed"

        except Exception as e:
            logger.error(
                f"Error processing task {task_id} with robot {robot_name}: {e}")
            self.active_tasks[task_id]["status"] = "failed"

        finally:
            # Remove task from active tasks after a delay
            logger.debug(
                f"Removing task {task_id} from active tasks after delay")
            await asyncio.sleep(5)  # Wait to ensure status is updated
            if task_id in self.active_tasks:
                # Check if the task was successful before removing
                task_status = self.active_tasks[task_id]["status"]
                if task_status == "completed":
                    logger.info(
                        f"Task {task_id} completed successfully, removing from active tasks")
                    del self.active_tasks[task_id]
                else:
                    logger.warning(
                        f"Task {task_id} ended with status '{task_status}', keeping in active tasks for monitoring")
                logger.debug(f"Task {task_id} status check completed")

    async def _process_loop(self):
        """Main processing loop that handles order processing"""
        logger.debug("Starting main processing loop")
        while self.running:
            try:
                # Check if we've reached the maximum number of orders to process
                if self.max_orders_to_process > 0 and self.orders_processed_count >= self.max_orders_to_process:
                    logger.info(
                        f"Maximum number of orders ({self.max_orders_to_process}) has been processed. Stopping order processing.")
                    # Stop the processing loop
                    self.running = False
                    break

                # Update available robots
                await self._update_available_robots()

                if not self.available_robots:
                    logger.info("No available robots, waiting...")
                    await asyncio.sleep(10)
                    continue

                # Get open orders
                logger.debug("Fetching open warehouse orders")
                orders = await self.sap_service.get_open_warehouse_orders()

                if not orders:
                    logger.info("No open orders found, waiting...")
                    await asyncio.sleep(10)
                    continue

                # Process first order
                self.current_order = orders[0]
                order_number = self.current_order['WarehouseOrder']
                logger.info(f"Processing order: {order_number}")
                logger.debug(f"Order details: {self.current_order}")

                # Get tasks for the order
                logger.debug(f"Fetching tasks for order {order_number}")
                tasks = await self.sap_service.get_warehouse_tasks_for_order(order_number)

                if not tasks:
                    logger.warning(f"No tasks found for order {order_number}")
                    # Skip this order without counting it as processed
                    logger.info(f"Order {order_number} skipped (no tasks)")

                    # Clean up resources associated with this order
                    self.current_order = None
                    if order_number in self.order_robot_assignments:
                        del self.order_robot_assignments[order_number]

                    continue

                logger.debug(f"Found {len(tasks)} tasks to process")

                # Determine which robot to use for this order using CUOPT
                robot = None

                # Check if this order is already assigned to a robot
                if order_number in self.order_robot_assignments:
                    # Try to find the previously assigned robot among available robots
                    assigned_robot_name = self.order_robot_assignments[order_number]
                    for available_robot in self.available_robots:
                        if available_robot.name == assigned_robot_name:
                            robot = available_robot
                            logger.info(
                                f"Using previously assigned robot {robot.name} for order {order_number}")
                            break

                    if robot is None:
                        logger.warning(
                            f"Previously assigned robot {assigned_robot_name} for order {order_number} is not available")
                        await asyncio.sleep(10)
                        continue

                # Process all tasks sequentially with the selected robot
                logger.info(
                    f"Processing all {len(tasks)} tasks for order {order_number}")
                for i, task in enumerate(tasks):
                    logger.debug(f"Processing task {task['WarehouseTask']}")
                    # For first task, we can pass None as robot will be assigned by CUOPT
                    # For subsequent tasks, we must have a valid robot object
                    await self._process_task(task, robot, i == 0)  # First task in the list
                    # Check if system is still running after each task
                    if not self.running:
                        break

                    # Refresh robot status to ensure it's still available
                    await self._update_available_robots()
                    if robot and not any(r.name == robot.name for r in self.available_robots):
                        logger.warning(
                            f"Robot {robot.name} is no longer available, stopping order processing")
                        break

                # Clear current order if all tasks are done
                if not self.active_tasks:
                    logger.debug("All tasks completed, clearing current order")
                    self.current_order = None
                    # Increment the processed orders counter for successful order completion
                    self.orders_processed_count += 1
                    logger.info(
                        f"Order {order_number} completed. Total orders processed: {self.orders_processed_count}")
                    # Remove the order-robot assignment
                    if order_number in self.order_robot_assignments:
                        del self.order_robot_assignments[order_number]

                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Error in SAP EWM background task: {e}")
                await asyncio.sleep(10)

    async def _assign_robot_to_order(self, robot_name: str, order_number: str):
        """Assign a robot to a warehouse order in SAP EWM"""
        logger.debug(f"Assigning robot {robot_name} to order {order_number}")
        try:
            # First, try to log on to the resource
            try:
                logger.debug(f"Logging on to resource {robot_name}")
                await self.sap_service.logon_to_resource(robot_name)
                logger.debug(f"Successfully logged on to resource {robot_name}")
            except Exception as e:
                logger.warning(f"Error logging on to resource {robot_name}: {e}")
                # Continue despite logon error as the resource might already be logged on

            # Unassign any previous resource from the order
            try:
                logger.debug(f"Unassigning any previous resources from order {order_number}")
                await self.sap_service.unassign_warehouse_order(order_number)
                logger.debug(
                    f"Successfully unassigned previous resources from order {order_number}")
            except Exception as e:
                logger.warning(f"Error unassigning resources from order {order_number}: {e}")
                # Continue despite unassign error

            # Now assign the robot to the order
            logger.debug(f"Assigning robot {robot_name} to order {order_number}")
            result = await self.sap_service.assign_robot_to_warehouse_order(order_number, robot_name)

            logger.info(
                f"Successfully assigned robot {robot_name} to order {order_number} in SAP EWM")

            # Update our local tracking
            self.order_robot_assignments[order_number] = robot_name
            return True
        except Exception as e:
            logger.error(f"Error assigning robot to order: {e}")
            # Still maintain the local assignment for retry
            self.order_robot_assignments[order_number] = robot_name
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get the current status of the background task system"""
        logger.debug("Retrieving system status")
        status = {
            "running": self.running,
            "current_order": self.current_order,
            "active_tasks": self.active_tasks,
            "available_robots": [robot.name for robot in self.available_robots],
            "order_robot_assignments": self.order_robot_assignments,
            "orders_processed_count": self.orders_processed_count,
            "max_orders_to_process": self.max_orders_to_process
        }
        logger.debug(f"System status: {status}")
        return status
