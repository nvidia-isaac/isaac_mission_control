# SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
# Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0


import boto3
import logging
import os
from typing import Optional
from cloud_common.objects.common import ICSServerError, ICSUsageError


class S3Client:
    """A boto3 S3 client"""
    _instance = None

    @staticmethod
    def get_instance():
        """ Static access method. """
        if not S3Client._instance:
            raise ICSServerError("S3 Client not started.")
        return S3Client._instance

    def __init__(self, aws_access_key_id: str = "", aws_secret_access_key: str = "",
                 region_name: Optional[str] = None, endpoint_url: Optional[str] = None):
        self.logger = logging.getLogger("Isaac Mission Control")
        config = {
            "aws_access_key_id": aws_access_key_id,
            "aws_secret_access_key": aws_secret_access_key,
            "region_name": region_name if region_name else None,
            "endpoint_url": endpoint_url if endpoint_url else None
        }
        self.s3 = boto3.client('s3', **config)
        self.logger.info("S3 Client initialized")
        S3Client._instance = self

    def get_object(self, bucket_name, object_key):
        """Get an object from S3"""
        try:
            response = self.s3.get_object(Bucket=bucket_name, Key=object_key)
            content = response['Body'].read()
            content_type = response['ContentType']
            return content, content_type
        except Exception as e:
            raise ICSServerError(
                f"Error getting object {object_key} from bucket {bucket_name}: {e}") from e
