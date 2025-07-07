# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import json
import logging
from typing import Optional

from pydantic import BaseModel

from app.api.clients.base_api_client import BaseAPIClient


class OTAFile(BaseModel):
    """File attributes"""
    s3_bucket: str = "files"
    s3_object_name: Optional[str] = ""
    robot_id: Optional[str] = ""
    deploy_path: Optional[str] = ""
    robot_type: Optional[str] = ""
    robot_version: Optional[str] = ""
    file_metadata: Optional[dict[str, str]] = {}


class OTAFileServiceClient(BaseAPIClient):
    """ Client for OTA file service API """
    _endpoints = {
        "upload": {
            "path": "/api/v1/file/upload",
        },
        "update": {
            "path": "/api/v1/file/update",
        },
        "list": {
            "path": "/api/v1/file/list",
        },
        "health": {
            "path": "/api/v1/health",
        }
    }

    def ota_file_upload(self, map_metadata: dict, map_path: str = "", map_content=None):
        """Upload file with OTA"""
        logging.info("Upload file with OTA")
        upload_endpoint = self._base_url + \
            str(self._endpoints["upload"]["path"])
        update_endpoint = self._base_url + \
            str(self._endpoints["update"]["path"])
        list_endpoint = self._base_url + \
            str(self._endpoints["list"]["path"])

        # Check if the file exists
        list_result = self.make_request_with_logs("get", list_endpoint, "OTA file list error",
                                                  "OTA file listed",
                                                  params={"s3_bucket": "files"})
        map_content_upload = map_content if map_content else open(
            map_path, "rb")
        if map_metadata["map_id"] in [file["s3_object_name"] for file in list_result]:
            file_info = OTAFile(
                s3_object_name=map_metadata["map_id"], file_metadata=map_metadata).dict()
            files = {
                "file_info": (None, json.dumps(file_info)),
                "file": (map_path.split("/")[-1], map_content_upload)
            }
            result = self.make_request_with_logs("patch", update_endpoint, "OTA file update error",
                                                 "OTA file updated",
                                                 files=files)

        else:
            file_info = OTAFile(
                s3_object_name=map_metadata["map_id"], file_metadata=map_metadata).dict()
            files = {
                "file_info_list": (None, json.dumps({"file_list": [file_info]})),
                "files": (map_path.split("/")[-1], map_content_upload)
            }
            result = self.make_request_with_logs("post", upload_endpoint, "OTA file upload error",
                                                 "OTA file uploaded",
                                                 files=files)

        return result
