# Copyright (c) 2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.


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
