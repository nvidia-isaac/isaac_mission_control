# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import logging
from json.decoder import JSONDecodeError

import httpx
from httpx import HTTPError


class BaseAPIClient:
    """Base class for Isaac API clients with logging support"""

    def __init__(self, config: dict, client: httpx.AsyncClient):
        self._config = config
        self._base_url = config["base_url"]
        self._client = client
        self._timeout = 60
        self._logger = logging.getLogger("Isaac Mission Control")

    @property
    def base_url(self):
        return self._base_url

    async def make_request_with_logs(self, method_name, endpoint, error_msg, success_msg,
                                     suppress_msg=False, **kwargs):
        try:
            response = await self._client.request(method=method_name, url=endpoint,
                                                  timeout=self._timeout, **kwargs)
            response.raise_for_status()
        except (HTTPError) as exc:
            if not suppress_msg:
                self._logger.error("endpoint %s HTTPError failure", endpoint)
                self._logger.error("%s, %s", error_msg, exc)
            raise

        self._logger.debug(success_msg)
        try:
            if not suppress_msg:
                self._logger.debug("Response JSON:\n%s", str(response.json()))
            return response.json()
        except JSONDecodeError:
            self._logger.error("Invalid response JSON received")
            return None
