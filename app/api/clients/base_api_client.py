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
import asyncio
import random


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
                                     suppress_msg=False, retry_safe=True, max_attempts=5, **kwargs):
        """Make an HTTP request with logging and built-in retry logic.

        Args:
            method_name (str): HTTP verb ("get", "post" …).
            endpoint (str): Complete URL to call.
            error_msg (str): Message to log on failures.
            success_msg (str): Message to log on success.
            suppress_msg (bool): If True, minimise log noise.
            retry_safe (bool): Only retry when the operation is idempotent / safe.
            max_attempts (int): Total attempts (first try + retries).

        The policy retries network errors and 429/502/503/504 responses
        with exponential back-off capped at 30 s and ±20 % jitter.
        """
        retryable_status_codes = {429, 502, 503, 504}
        initial_delay = 0.5  # seconds
        max_delay = 30.0     # seconds

        for attempt in range(1, max_attempts + 1):
            try:
                response = await self._client.request(method=method_name, url=endpoint,
                                                      timeout=self._timeout, **kwargs)
                response.raise_for_status()
                # Success — leave retry loop
                break
            except HTTPError as exc:
                # Some httpx exceptions (e.g. ConnectError) do not carry a `response` attribute.
                status = getattr(getattr(exc, "response", None), "status_code", None)
                is_retryable = retry_safe and (status is None or status in retryable_status_codes)

                # Decide whether we should retry
                should_retry = is_retryable and attempt < max_attempts

                if not should_retry:
                    if not suppress_msg:
                        self._logger.error("endpoint %s HTTPError failure", endpoint)
                        self._logger.error("%s, %s", error_msg, exc)
                    raise

                # Back-off before the next attempt
                delay = min(max_delay, initial_delay * (2 ** (attempt - 1)))
                delay *= random.uniform(0.8, 1.2)  # jitter ±20 %
                if not suppress_msg:
                    self._logger.warning(
                        "Attempt %d/%d failed (%s). Retrying in %.2fs…",
                        attempt, max_attempts, exc, delay,
                    )
                await asyncio.sleep(delay)

        self._logger.debug(success_msg)
        try:
            if not suppress_msg:
                self._logger.debug("Response JSON:\n%s", str(response.json()))
            return response.json()
        except JSONDecodeError:
            self._logger.error("Invalid response JSON received")
            return None
