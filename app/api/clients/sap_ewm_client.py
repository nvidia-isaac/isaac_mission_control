# Copyright (c) 2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import os
import base64
from typing import Dict, List, Any, Optional
import httpx
import logging
import urllib.parse
from cloud_common.objects.common import ICSUsageError, ICSServerError

logger = logging.getLogger("Isaac Mission Control")


class SapEwmService:
    def __init__(self, client: httpx.AsyncClient, sap_config):
        """Initialize the SAP EWM service with the existing httpx client and configuration."""
        self.client = client
        # Get credentials from config first
        self.username = sap_config.username
        self.password = sap_config.password
        # Override with environment variables if they exist
        if os.getenv('SAP_USERNAME'):
            self.username = os.getenv('SAP_USERNAME')
        if os.getenv('SAP_PASSWORD'):
            self.password = os.getenv('SAP_PASSWORD')
        self.base_url = sap_config.base_url
        self.warehouse = sap_config.warehouse

    async def _make_request(self, method: str, url: str, json_data=None):
        """Make an authenticated request to the SAP API."""
        # Check if credentials are available
        if not self.username or not self.password:
            raise ICSUsageError(
                "SAP credentials not set. Please set SAP_USERNAME and SAP_PASSWORD environment variables.")

        # Create base64 encoded basic auth header
        auth_string = f"{self.username}:{self.password}"
        auth_bytes = auth_string.encode('utf-8')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth_b64}"
        }

        # Make sure URL is properly formatted with no spaces
        url = url.replace(' ', '%20')

        try:
            logger.debug(
                f"Making SAP API request: {method} {self.base_url}{url}")

            # For POST requests, first fetch a CSRF token and ETag
            if method.lower() == 'post':
                # Make a HEAD/GET request to get the CSRF token
                csrf_headers = headers.copy()
                csrf_headers["X-CSRF-Token"] = "Fetch"

                csrf_response = await self.client.get(
                    f"{self.base_url}{url}",
                    headers=csrf_headers
                )

                # Extract token from response headers
                csrf_token = csrf_response.headers.get("x-csrf-token")
                if not csrf_token:
                    logger.warning("No CSRF token received from SAP API")
                else:
                    logger.debug("Received CSRF token from SAP API")
                    headers["X-CSRF-Token"] = csrf_token

                # Add If-Match header for conditional request
                # Use wildcard ETag (*) which will match any resource state
                headers["If-Match"] = "*"

            if method.lower() == 'get':
                response = await self.client.get(
                    f"{self.base_url}{url}",
                    headers=headers
                )
            elif method.lower() == 'post':
                response = await self.client.post(
                    f"{self.base_url}{url}",
                    headers=headers,
                    json=json_data
                )
            else:
                raise ICSUsageError(f"Unsupported HTTP method: {method}")

            logger.debug(f"SAP API response status: {response.status_code}")
            response.raise_for_status()

            # Check if response is empty
            if not response.content:
                logger.warning("Received empty response from SAP API")
                return {"value": []}  # Return empty value array as default

            # Try to parse JSON response
            try:
                return response.json()
            except ValueError as e:
                logger.error(f"Invalid JSON response from SAP API: {response.text}")
                raise ICSServerError(f"SAP API returned invalid JSON: {response.text}") from e

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error occurred: {e} - Response: {e.response.text if hasattr(e, 'response') else 'No response'}")
            raise ICSServerError(f"SAP API request failed: {str(e)}") from e
        except Exception as e:
            logger.error(f"An error occurred during SAP API request: {e}")
            raise ICSServerError(f"Unexpected error during SAP API request: {str(e)}") from e

    async def get_storage_bins(self, bin_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get list of storage bins with coordinates.

        Args:
            bin_name: Optional storage bin name to filter by. If provided, returns only that specific bin.
        """
        if bin_name:
            # Use direct endpoint for specific bin
            url = f"/api_whse_storage_bin_2/srvd_a2x/sap/warehousestoragebin/0001/WarehouseStorageBin/{self.warehouse}/{bin_name}"
            response = await self._make_request('get', url)
            return [response] if response else []
        else:
            # Getting all bins
            warehouse_filter = urllib.parse.quote(
                f"EWMWarehouse eq '{self.warehouse}'")
            url = f"/api_whse_storage_bin_2/srvd_a2x/sap/warehousestoragebin/0001/WarehouseStorageBin?$filter={warehouse_filter}"
            response = await self._make_request('get', url)
            return response["value"]

    async def get_warehouse_resources(self) -> List[Dict[str, Any]]:
        """Get list of warehouse resources (robots)."""
        warehouse_filter = urllib.parse.quote(
            f"EWMWarehouse eq '{self.warehouse}'")
        url = f"/api_warehouse_resource_2/srvd_a2x/sap/warehouseresource/0001/WarehouseResource?$filter={warehouse_filter}"
        response = await self._make_request('get', url)
        return response["value"]

    async def get_warehouse_orders(self, status: str = '') -> List[Dict[str, Any]]:
        """Get warehouse orders with specified status.

        Args:
            status: Warehouse order status
                '' - open
                'C' - confirmed
                'A' - cancelled
                'D' - in progress
        """
        filter_str = urllib.parse.quote(
            f"EWMWarehouse eq '{self.warehouse}' and WarehouseOrderStatus eq '{status}'")
        url = f"/api_warehouse_order_task_2/srvd_a2x/sap/warehouseorder/0001/WarehouseOrder?$filter={filter_str}"
        response = await self._make_request('get', url)
        return response["value"]

    async def get_open_warehouse_orders(self) -> List[Dict[str, Any]]:
        """Get open warehouse orders."""
        return await self.get_warehouse_orders('')

    async def get_warehouse_tasks_for_order(self, order_number: str) -> List[Dict[str, Any]]:
        """Get tasks for a specific warehouse order."""
        url = f"/api_warehouse_order_task_2/srvd_a2x/sap/warehouseorder/0001/WarehouseOrder/{self.warehouse}/{order_number}/_WarehouseTask"
        response = await self._make_request('get', url)
        return response["value"]

    async def confirm_warehouse_task(self, task_number: str, task_item: str) -> Dict[str, Any]:
        """
        Confirm warehouse task completion.

        Args:
            task_number: The warehouse task number to confirm
            task_item: The warehouse task item number

        Returns:
            API response from SAP

        Note:
            - Task destination bin is automatically retrieved from the task data
            - For handling unit tasks, a different endpoint and payload structure is used
        """
        try:
            # Get the task details to ensure we have the latest data
            task_url = f"/api_warehouse_order_task_2/srvd_a2x/sap/warehouseorder/0001/WarehouseTask/{self.warehouse}/{task_number}/{task_item}"
            try:
                task_data = await self._make_request('get', task_url)
            except Exception as e:
                logger.error(f"Failed to retrieve task data: {e}")
                raise ICSServerError(
                    f"Could not retrieve task data for {task_number}/{task_item}: {str(e)}")

            if not task_data:
                error_msg = f"Task {task_number}/{task_item} not found or returned empty data"
                logger.error(error_msg)
                raise ICSUsageError(error_msg)

            # Check if this is a handling unit task
            is_handling_unit_task = task_data.get("IsHandlingUnitWarehouseTask", False)

            # Choose the appropriate endpoint based on task type
            endpoint = "SAP__self.ConfirmWarehouseTaskHndlgUnit" if is_handling_unit_task else "SAP__self.ConfirmWarehouseTaskProduct"

            # Confirmation endpoint URL
            url = f"/api_warehouse_order_task_2/srvd_a2x/sap/warehouseorder/0001/WarehouseTask/{self.warehouse}/{task_number}/{task_item}/{endpoint}"

            # Build the appropriate payload based on task type
            data = {}
            if is_handling_unit_task:
                # For handling unit tasks, we need to specify destination
                data["DestinationStorageBin"] = task_data.get("DestinationStorageBin", "")
                data["WhseTaskExCodeDestStorageBin"] = ""
                logger.debug(f"Using destination bin from task: {data['DestinationStorageBin']}")
            else:
                # For product tasks, use the more detailed payload
                data = {
                    "DestinationHandlingUnit": "",
                    "AlternativeUnit": task_data.get("AlternativeUnit", "EA"),
                    "ActualQuantityInAltvUnit": 1,
                    "DifferenceQuantityInAltvUnit": task_data.get("DifferenceQuantityInAltvUnit", 0),
                    "WhseTaskExceptionCodeQtyDiff": "",
                    "DestinationStorageBin": task_data.get("DestinationStorageBin", ""),
                    "WhseTaskExCodeDestStorageBin": "",
                    "SourceHandlingUnit": task_data.get("SourceHandlingUnit", "")
                }

            logger.debug(
                f"Confirmation data for {'handling unit' if is_handling_unit_task else 'product'} task: {data}")

            try:
                response = await self._make_request('post', url, data)
                logger.info(f"Successfully confirmed task {task_number}/{task_item}")
                return response
            except Exception as e:
                logger.error(f"Failed to confirm task: {e}")
                raise ICSServerError(f"Task confirmation failed: {str(e)}")

        except Exception as e:
            logger.error(f"Error confirming warehouse task: {e}")
            raise ICSServerError(f"Error confirming warehouse task: {str(e)}")

    async def build_storage_bin_coordinate_map(self) -> Dict[str, Dict[str, float]]:
        """Build a coordinate mapping from storage bins."""
        storage_bins = await self.get_storage_bins()

        # Create a map of bin name to coordinates
        bin_coordinates = {}

        for bin in storage_bins:
            bin_coordinates[bin["EWMStorageBin"]] = {
                "x": bin["EWMStorBinWidthCoordinateValue"],
                "y": bin["EWMStorBinLengthCoordinateVal"],
                "z": bin["EWMStorBinHeightCoordinateVal"]
            }

        return bin_coordinates

    async def create_navigation_mission_from_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Create a navigation mission from a warehouse task in a format compatible with MissionData."""
        # Extract source and destination bin names from the task
        source_bin = task.get("SourceStorageBin", "")
        dest_bin = task.get("DestinationStorageBin", "")

        # Store bin coordinates
        bin_coordinates = {}

        # Get source bin coordinates if available
        if source_bin:
            source_bins = await self.get_storage_bins(source_bin)
            if source_bins:
                bin_coordinates[source_bin] = {
                    "x": source_bins[0].get("EWMStorBinWidthCoordinateValue", 0),
                    "y": source_bins[0].get("EWMStorBinLengthCoordinateVal", 0),
                    "z": source_bins[0].get("EWMStorBinHeightCoordinateVal", 0)
                }

        # Get destination bin coordinates if available
        if dest_bin:
            dest_bins = await self.get_storage_bins(dest_bin)
            if dest_bins:
                bin_coordinates[dest_bin] = {
                    "x": dest_bins[0].get("EWMStorBinWidthCoordinateValue", 0),
                    "y": dest_bins[0].get("EWMStorBinLengthCoordinateVal", 0),
                    "z": dest_bins[0].get("EWMStorBinHeightCoordinateVal", 0)
                }

        # If we couldn't get specific bin coordinates, fall back to the complete map
        if (source_bin and source_bin not in bin_coordinates) or (dest_bin and dest_bin not in bin_coordinates):
            logger.warning("Couldn't get specific bin coordinates, falling back to complete map")
            bin_coordinates = await self.build_storage_bin_coordinate_map()

        # Extract source and destination locations
        source_location = bin_coordinates.get(source_bin, {"x": 0, "y": 0, "z": 0})
        dest_location = bin_coordinates.get(dest_bin, {"x": 0, "y": 0, "z": 0})

        # Build mission details using the route field instead of waypoints
        mission = {
            "id": f"sap-task-{task['WarehouseTask']}-{task['WarehouseTaskItem']}",
            "type": "navigation",
            "priority": task.get("EWMWarehouseTaskPriority", 0),
            "route": [  # Use route instead of waypoints
                {
                    # Source location
                    "name": source_bin,
                    "x": source_location["x"] / 1000.0,
                    "y": source_location["y"] / 1000.0,
                    "z": source_location.get("z", 0),
                    "action": "PICKUP",
                    "parameters": {
                        "product": task["Product"],
                        "quantity": task["TargetQuantityInBaseUnit"],
                        "unit": task["BaseUnit"]
                    }
                },
                {
                    # Destination location
                    "name": dest_bin,
                    "x": dest_location["x"] / 1000.0,
                    "y": dest_location["y"] / 1000.0,
                    "z": dest_location.get("z", 0),
                    "action": "DELIVER",
                    "parameters": {
                        "product": task["Product"],
                        "quantity": task["TargetQuantityInBaseUnit"],
                        "unit": task["BaseUnit"]
                    }
                }
            ],
            "metadata": {
                "sapWarehouseTask": task["WarehouseTask"],
                "sapWarehouseTaskItem": task["WarehouseTaskItem"],
                "sapWarehouseOrder": task["WarehouseOrder"],
                "sapProduct": task["Product"],
                "sapQuantity": task["TargetQuantityInBaseUnit"]
            }
        }

        return mission

    async def assign_robot_to_warehouse_order(self, order_number: str, resource_name: str) -> Dict[str, Any]:
        """
        Assign a robot (resource) to a warehouse order in SAP EWM

        Args:
            order_number: The warehouse order number
            resource_name: The name of the robot resource in SAP EWM

        Returns:
            Dict[str, Any]: API response from SAP
        """
        try:
            # Build the assignment endpoint URL
            url = f"/api_warehouse_order_task_2/srvd_a2x/sap/warehouseorder/0001/WarehouseOrder(EWMWarehouse='{self.warehouse}',WarehouseOrder='{order_number}')/SAP__self.AssignWarehouseOrder"

            # Prepare request payload
            payload = {
                "EWMResource": resource_name
            }

            # Make the assignment request
            response = await self._make_request('post', url, payload)
            logger.info(f"Successfully assigned resource {resource_name} to order {order_number}")
            return response

        except Exception as e:
            logger.error(f"Error assigning robot to warehouse order: {e}")
            raise ICSServerError(
                f"Failed to assign robot {resource_name} to order {order_number}: {str(e)}")

    async def logon_to_resource(self, resource_name: str) -> Dict[str, Any]:
        """
        Log on to a warehouse resource in SAP EWM.

        In SAP EWM, you must be logged on to a resource before you can assign tasks to it.

        Args:
            resource_name: The name of the robot resource in SAP EWM

        Returns:
            Dict[str, Any]: API response from SAP
        """
        try:
            # Build the logon endpoint URL
            url = f"/api_warehouse_resource_2/srvd_a2x/sap/warehouseresource/0001/WarehouseResource(EWMWarehouse='{self.warehouse}',EWMResource='{resource_name}')/SAP__self.LogonToWarehouseResource"

            # Empty payload for logon action
            payload = {}

            # Make the logon request
            response = await self._make_request('post', url, payload)
            logger.info(f"Successfully logged on to resource {resource_name}")
            return response

        except Exception as e:
            logger.error(f"Error logging on to resource: {e}")
            raise ICSServerError(f"Failed to log on to resource {resource_name}: {str(e)}")

    async def unassign_warehouse_order(self, order_number: str) -> Dict[str, Any]:
        """
        Unassign any resource from a warehouse order in SAP EWM.

        This should be called before assigning a new resource to ensure clean assignment.

        Args:
            order_number: The warehouse order number

        Returns:
            Dict[str, Any]: API response from SAP
        """
        try:
            # Build the unassignment endpoint URL
            url = f"/api_warehouse_order_task_2/srvd_a2x/sap/warehouseorder/0001/WarehouseOrder(EWMWarehouse='{self.warehouse}',WarehouseOrder='{order_number}')/SAP__self.UnassignWarehouseOrder"

            # Empty payload for unassignment
            payload = {}

            # Make the unassignment request
            response = await self._make_request('post', url, payload)
            logger.info(f"Successfully unassigned any resource from order {order_number}")
            return response

        except Exception as e:
            logger.error(f"Error unassigning warehouse order: {e}")
            # Don't raise an exception here, as this is a preparatory step
            # and the order might not have been assigned in the first place
            logger.warning(f"Continuing with assignment despite unassign error: {str(e)}")
            return {"status": "warning", "message": f"Unassign operation failed: {str(e)}"}
