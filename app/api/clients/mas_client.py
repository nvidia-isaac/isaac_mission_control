# Copyright (c) 2024-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

from app.api.clients.base_api_client import BaseAPIClient
from app.common.utils import Blockage


class MASServiceClient(BaseAPIClient):
    """ Client for MAS API """
    _endpoints = {
        "blockages": {
            "path": "/blockages",
        },
        "health": {
            "path": "/health",
        }
    }

    def send_blockages(self, blockages: list[Blockage]):
        """Send blockages"""
        blockages_endpoint = self._base_url + \
            str(self._endpoints["blockages"]["path"])
        return self.make_request_with_logs(
            "post", blockages_endpoint,
            "Failed to send blockages to MAS", "Sent blockages to MAS",
            json={"circles": blockages})
