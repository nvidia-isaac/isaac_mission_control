# SPDX-FileCopyrightText: Copyright (c) 2023-2025 NVIDIA CORPORATION &
# AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE

# pylint: skip-file

import base64
import io
import json
import logging as log
import os
import pickle
import time
import zipfile
import zlib
from datetime import datetime, timezone

import requests


def _read_zip_dir(files):
    # cuopt returns {} when it writes to "large_result" and NVCF retains
    # that return value, so we actually end up with two files
    # Look for "large_result" but if we receive a single file, read that
    # (this would be the case for a non JSON response from cuopt)
    fname = "large_result"
    if len(files) == 1:
        fname = list(files.keys())[0]
    if fname in files:
        try:
            res = json.loads(files[fname])
        except Exception:
            res = {"error": "non JSON response", "file": {fname: files[fname]}}
    else:
        res = {"error": "multiple file response", "files": files}

    return res


def check_compressed(datafile):
    # zlib compressed files will give an error
    # trying to read the first few bytes
    with open(datafile, "r") as a:
        try:
            a.read(2)
            return False
        except (zlib.error, UnicodeDecodeError):
            return True


class CuOptServiceClient:
    """
    The CuOptServiceClient handles requests to the
    cuOpt service through NVIDIA Cloud Functions (NVCF)

    Parameters
    ----------
    client_id (str): NOTE: This is deprecated, use SAK.
            The client ID obtained during the registration
            process. Only one of the two authorization
            methods (SAK or CLIENT ID-SECRET) should be used.
    client_secret (str): NOTE: This is deprecated, use SAK.
            The client secret obtained during the
            registration process. Only one of the two authorization
            methods (SAK or CLIENT ID-SECRET) should be used.
    sak (str): The sak obtained through NGC. Only one of the two authorization
            methods (SAK or CLIENT ID-SECRET) should be used.
    function_name (str, optional): The name of the function, provided
            during registration or discoverable via a function_list API
            call. This value may be omitted if all available functions have
            the same name or if function_id is set instead. The client will
            select the latest available version of the function with this name.
            Ignored if function_id is set.
    function_id (str, optional): The unique identifier of a function,
            provided during registration or discoverable via a
            function_list API call. Takes precedence over function_name if
            both are set. The client will select the latest available version
            of the function with this id.
    function_version_id (str, optional): Selects a particular version of
            a function specified by name or id. This should only be used when
            there are multiple versions available that are not API compatible.
            If this value is omitted the client will select the latest version
            of the function.
    polling_interval (int, optional): The duration in seconds between
            consecutive polling attempts. Defaults to 1.
    token_expiration_padding (int, optional): The buffer time in
            seconds before the token expiration time, during which a new
            token will be requested. Defaults to 120.
    request_excess_timeout (int, optional): The time in seconds to poll
            for completion of a request. If the polling time expires before
            the request is finished, the client may re-poll the request
            (ie, polling time is effectively unlimited using multiple calls).
            Defaults to 120.
    api_path (str, optional): Deprecated. Set auth/api endpoints for
             cuOpt, useful only for NVIDIA testing.
    disable_compression (boolean, optional): Disable zlib compression
            of large files.
    disable_version_string (boolean, optional): Do not send the client
            version to the server.
    only_validate (boolean, optional): Only validates input and doesn't
            add to billing
    config_path (boolean, optional): Path of a JSON config file for setting
            client defaults in JSON. These values will be used if the
            corresponding arguments are not passed to __init__.
            Format is:

                {
                    "defaults": {
                        "function_name": "",
                        "function_id": "",
                        "function_version_id": ""
                    }
                }


    """

    # Initialize the CuOptServiceClient with client_id and client_secret
    def __init__(
        self,
        client_id: str = "",
        client_secret: str = "",
        sak: str = "",
        function_name: str = "",
        function_id: str = "",
        function_version_id: str = "",
        polling_interval: int = 1,
        token_expiration_padding: int = 120,
        request_excess_timeout: int = 120,
        api_path: str = "",
        disable_compression=False,
        disable_version_string=False,
        only_validate=False,
        config_path="",
    ):
        """
        Initializes the instance with the provided credentials, function
        information, and configuration options.
        """

        self.only_validate = only_validate
        if (client_id or client_secret) and sak:
            raise ValueError(
                "Only one authetication is expected client id/secret or sak"
            )

        if client_id and client_secret:
            # Encode the credentials in base64
            credentials_64_bytes = base64.b64encode(
                f"{client_id}:{client_secret}".encode("utf-8")
            )
            self.credentials_64 = credentials_64_bytes.decode("utf-8")
            # Initialize variables for token management
            self.sak = None
            self.token = None
        elif sak:
            # Initialize variables for token management
            self.sak = sak
            self.token = sak
        else:
            raise ValueError("Need atleast one kind of authorization")

        self.token_expiration = None
        # Initialize variable for version list management
        self.version_cache_location = "version_cache.json"

        # Initialize variables for token management
        self.tkn_cache_location = "token_cache.json"

        # Initialize URLs for authentication and request
        self.auth_url = os.environ.get(
            "CUOPT_AUTH_URL",
            "https://tbyyhdy8-opimayg5nq78mx1wblbi8enaifkmlqrm8m.ssa.nvidia.com/token",  # noqa
        )
        self.request_url = os.environ.get(
            "CUOPT_API_URL", "https://api.nvcf.nvidia.com/v2/nvcf"
        )

        # Set config values from config_path if present
        self.config_path = config_path
        self._read_config()
        self._set_auth_api_from_config()

        # deprecated, but allow it to work for backward compat
        self.api_path = api_path
        self._set_auth_api_from_api_path()

        self.upload_url = self.request_url + "/assets"
        self.functions_url = self.request_url + "/functions"
        self.asset_url = None
        self.asset_id = None

        # Initialize variables for polling
        self.poll_interval = polling_interval

        # Initialize variables for token management
        self.token_expiration_padding = token_expiration_padding

        # Initialize variables for the request
        self.request_excess_timeout = request_excess_timeout
        self.request_timeout = None

        self.version_cache = None
        self.version_cache_time = None

        # If name, id, or version were not set then get defaults from config
        (
            function_name,
            function_id,
            function_version_id,
        ) = self.get_func_defaults_from_config(
            function_name, function_id, function_version_id
        )
        # Set function name, id, and version_id
        if function_id:
            self.set_function_by_id(function_id, function_version_id)
        elif function_name:
            self.set_function_by_name(function_name, function_version_id)
        else:
            self.function_version_id = function_version_id
            self.function_id = function_id
            self.function_name = function_name

        self.request_start_time = None
        self.disable_compression = disable_compression
        self.disable_version_string = disable_version_string

    def _set_auth_api_from_api_path(self):
        if self.api_path:
            log.info("Using api_path is deprecated. Use config_path instead.")
            if "auth" in self.config or "api" in self.config:
                log.warn(
                    f"Ignoring auth/api settings in {self.api_path}, "
                    f"already set in {self.config_path}"
                )
            else:
                try:
                    with open(self.api_path, "r") as api:
                        urls = json.load(api)
                        self.auth_url = urls["auth"]
                        self.request_url = urls["api"]
                except Exception:
                    print(f"Unable to read API endpoints from {self.api_path}")
                    raise

    def _set_auth_api_from_config(self):
        # If they are not present in config, just use defaults
        auth = self.config.get("auth", self.auth_url)
        if auth:
            self.auth_url = auth
        api = self.config.get("api", self.request_url)
        if api:
            self.request_url = api

    def _read_config(self):
        self.config = {}
        if self.config_path:
            try:
                with open(self.config_path, "r") as c:
                    self.config = json.load(c)
            except Exception:
                print(f"Unable to read config from {self.config_path}")
                raise

    def get_func_defaults_from_config(self, name, id, vid):
        n = name
        i = id
        v = vid
        if "defaults" in self.config:
            d = self.config["defaults"]
            if not n:
                n = d.get("function_name", n)
            if not id:
                i = d.get("function_id", id)
            if not v:
                v = d.get("function_version_id", v)

            for x in [
                [n, name, "function_name"],
                [i, id, "function_id"],
                [v, vid, "function_version_id"],
            ]:
                if x[0] != x[1]:
                    log.debug(f"Set {x[2]} to {x[0]} from {self.config_path}")
        return n, i, v

    # Request a new JWT token
    def _get_jwt_token(self):
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {self.credentials_64}",
        }

        payload = {
            "scope": "invoke_function list_functions",
            "grant_type": "client_credentials",
        }

        try:
            response = requests.post(
                self.auth_url, headers=headers, data=payload, timeout=30
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            if response.status_code == 401:
                raise ValueError(
                    "Authentication Error: Invalid Client ID or Client Secret"
                )
            else:
                raise

        data = response.json()

        self._cache_token(data)

    # Check if the token is expired
    def _check_token_expiration(self, expiration_time):
        if expiration_time is None:
            return False

        token_refresh = expiration_time - self.token_expiration_padding

        return token_refresh > time.time()

    # Cache the token to a file
    def _cache_token(self, token_data):
        self.token = token_data["access_token"]
        self.token_expiration = time.time() + token_data["expires_in"]

        token_cache_data = {
            "token": self.token,
            "token_expiration": self.token_expiration,
        }
        try:
            with open(self.tkn_cache_location, "w") as f:
                json.dump(token_cache_data, f)
        except Exception:
            log.debug("ignoring token cache")

    # Check if there is a valid token in the cache
    def _check_token_cache(self):
        if self.sak:
            return True
        try:
            if not os.path.exists(self.tkn_cache_location):
                return False

            with open(self.tkn_cache_location, "r") as f:
                token_cache_data = json.load(f)
        except Exception:
            log.debug("ignorig token cache")
            return False

        if self._check_token_expiration(token_cache_data["token_expiration"]):
            self.token = token_cache_data["token"]
            self.token_expiration = token_cache_data["token_expiration"]
            log.info("Using Cached Token")
            return True
        else:
            log.info("Cached Token Expired")
            return False

    def _version_cache(self, funcs):
        log.info("Updating version cache")
        ids = {}
        functions = {}
        ids_maxMajor = {}
        for f in funcs:
            if f["status"] == "ACTIVE":
                name = f["name"]
                if name not in functions:
                    functions[name] = {"maxMajor": 0, "versions": {}}
                namedf = functions[name]
                major = int(
                    datetime.strptime(f["createdAt"], "%Y-%m-%dT%H:%M:%S.%fZ")
                    .replace(tzinfo=timezone.utc)
                    .timestamp()
                )
                if major > namedf["maxMajor"]:  # type: ignore
                    namedf["maxMajor"] = major
                if major not in namedf["versions"]:  # type: ignore
                    namedf["versions"][major] = []  # type: ignore
                updatev = namedf["versions"][major]  # type: ignore
                updatev.append({"id": f["id"], "version_id": f["versionId"]})

                # We should always store the maxMajor version for the
                # particular function id in the by_id list so it is
                # guaranteed to be the latest version if invoked by id
                if f["id"] not in ids:
                    ids[f["id"]] = {
                        "name": f["name"],
                        "version_id": f["versionId"],
                    }
                    ids_maxMajor[f["id"]] = major
                elif major > ids_maxMajor[f["id"]]:
                    ids[f["id"]]["version_id"] = f["versionId"]
                    ids_maxMajor[f["id"]] = major

        res = {"by_id": ids, "by_name": functions}
        try:
            with open(self.version_cache_location, "w") as f:
                json.dump(res, f)
        except Exception:
            log.debug("ignoring version cache")

        self.version_cache = json.loads(json.dumps(res))
        self.version_cache_time = time.time()  # type: ignore
        return res

    def _read_version_cache(self):
        if (
            not self.version_cache
            or time.time() - self.version_cache_time > 3600
        ):
            if not os.path.exists(self.version_cache_location) or (
                time.time() - os.path.getmtime(self.version_cache_location)
                > 3600
            ):
                self.get_functions()
            else:
                try:
                    with open(self.version_cache_location, "r") as f:
                        self.version_cache = json.load(f)
                        self.version_cache_time = os.path.getmtime(  # type: ignore
                            self.version_cache_location
                        )
                except Exception:
                    self.get_functions()
        return self.version_cache

    # Upload the large cuOpt problem instances
    # as an asset if needed (exceeds 250KB)
    def _upload_asset(
        self, cuopt_problem_json_data, filep=False, compressed=False
    ):

        now = datetime.now()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "accept": "application/json",
        }

        payload = {
            "contentType": "application/octet-stream",
            "description": "Optimization-data",
        }

        response = requests.post(
            self.upload_url, headers=headers, json=payload, timeout=30
        )
        response.raise_for_status()

        self.asset_url = response.json()["uploadUrl"]
        self.asset_id = response.json()["assetId"]

        headers = {
            "Content-Type": "application/octet-stream",
            "x-amz-meta-nvcf-asset-description": "Optimization-data",
        }
        if filep:
            # if the file is already compressed, there is nothing to do here
            with open(cuopt_problem_json_data, "rb") as f:
                cuopt_data = f.read()
                if not self.disable_compression and not compressed:
                    log.debug("Compressing data with zlib")
                    cuopt_data = zlib.compress(cuopt_data, zlib.Z_BEST_SPEED)
                else:
                    log.debug(
                        f"Compression disabled {self.disable_compression}, "
                        f"data already compressed {compressed}"
                    )
        else:
            cuopt_data = cuopt_problem_json_data
        response = requests.put(
            self.asset_url,
            data=cuopt_data,
            headers=headers,
            timeout=300,
        )
        total = datetime.now() - now
        log.debug(f"s3 upload time was {total}")
        response.raise_for_status()

        return response.status_code

    # Delete the asset if uploaded
    def _delete_asset(self):
        headers = {
            "Authorization": f"Bearer {self.token}",
        }

        response = requests.delete(
            f"{self.upload_url}/{self.asset_id}", headers=headers, timeout=30
        )

        response.raise_for_status()

        assert response.status_code == 204
        self.asset_id = None
        self.asset_url = None

    def _handle_response(self, response):
        if "responseReference" in response:
            # This will be a zip of a directory containing the
            # file "large_result"
            # Download it, unzip it, return the result
            log.info("Extracting file response")
            lr = requests.get(
                response["responseReference"], stream=True, timeout=120
            )
            if lr.status_code == 200:
                with io.BytesIO() as data:
                    for chunk in lr.iter_content(chunk_size=1024):
                        if chunk:
                            data.write(chunk)
                    data.seek(0)
                    with zipfile.ZipFile(data, "r") as z:
                        files = {f: z.read(f) for f in z.namelist()}
                    response["response"] = _read_zip_dir(files)
                del response["responseReference"]
            else:
                lr.raise_for_status()
        return response

    def _handle_request_exception(self, response, e):
        try:
            msg = response.json().get("detail", "")
        except Exception:
            msg = response.text
        raise ValueError(f"{response.reason} - {response.status_code}: {msg}")

    # Send the request to the cuOpt service through NVCF
    def _send_request(
        self, cuopt_problem_json_data, action="cuOpt_OptimizedRouting"
    ):
        if (not self.token) and (not self._check_token_cache()):
            log.info("Requesting New Token")
            self._get_jwt_token()

        # If function has not been set, try the default
        # (highest version of single available function)
        if not (self.function_id or self.function_name):
            self.set_function_by_name("", self.function_version_id)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }

        asset_data = None

        # Check if the cuOpt problem instance is larger than 250KB
        filep = not isinstance(
            cuopt_problem_json_data, dict
        ) and os.path.isfile(cuopt_problem_json_data)
        if filep:
            sz = os.path.getsize(cuopt_problem_json_data)
            compressed = check_compressed(cuopt_problem_json_data)
        else:
            # We're going to guess here a little bit.
            # There is no builtin method in Python to find the size
            # of a dictionary, and if the dictionary is large then
            # writing it to a string with json.dumps can take a long time
            # so it's not worth the risk.

            # But pickle is fast, so ...
            # We are going to pickle the data. If the pickled size is <= 120k,
            # we are going to assume that the json.dumps will still be
            # quick and the unpickled object MIGHT be less than 250k
            # (informal testing shows that pickle compression of cuopt data
            # may be anywhere from 52% to 77%)
            # We use json.dumps to get the REAL uncompressed size, and if it's
            # less than 250k we'll just send it uncompressed. Otherwise we'll
            # pass the pickled data we already generated to _upload_asset
            data_bytes = pickle.dumps(cuopt_problem_json_data)
            pickled_sz = len(data_bytes)
            real_sz = None
            if pickled_sz <= 120000:
                log.debug(
                    "Pickled data looks small, checking unpickled size..."
                )
                real_sz = len(json.dumps(cuopt_problem_json_data))
            if real_sz is None or real_sz > 250000:
                log.debug("Sending immediate data pickled")
                cuopt_problem_json_data = data_bytes
                sz = pickled_sz
                compressed = True
            else:
                log.debug("Sending immediate data unpickled")
                sz = real_sz
                compressed = False

        if sz > 250000 or compressed:
            self._upload_asset(cuopt_problem_json_data, filep, compressed)
            asset_data = [self.asset_id]
            cuopt_problem_json_data = None
        elif filep:
            cuopt_problem_json_data = json.load(
                open(cuopt_problem_json_data, "r")
            )

        log.debug(
            f"Calling function {self.function_name} "
            f"{self.function_id} {self.function_version_id}"
        )

        payload = {
            "requestHeader": {},
            "requestBody": {
                "action": action,
                "data": cuopt_problem_json_data,
            },
        }
        if not self.disable_version_string:
            payload["requestBody"]["client_version"] = ("24.03.03")  # type: ignore
        if asset_data:
            payload["requestHeader"]["inputAssetReferences"] = asset_data  # type: ignore

        try:
            # Add function id
            path = "/exec/functions/" + self.function_id
            # Add version id
            path = path + "/versions/" + self.function_version_id
            self.request_start_time = time.time()  # type: ignore
            log.debug(self.request_url + path)
            response = requests.post(
                self.request_url + path,
                headers=headers,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            self._handle_request_exception(response, e)

        return self._handle_response(response.json())

    # Poll for the cuOpt response until it is fulfilled
    def _poll_for_response(self, response_id):
        headers = {"Authorization": f"Bearer {self.token}"}

        response_url = f"{self.request_url}/exec/status/{response_id}"

        while True:
            try:
                response = requests.get(
                    response_url, headers=headers, timeout=30
                )
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                # If we have a token expire while we're polling,
                # get another one and keep going
                if "Unauthorized" in str(e) and not self._check_token_cache():
                    log.info("Token expired while polling, refreshing")
                    self._get_jwt_token()
                    headers["Authorization"] = f"Bearer {self.token}"
                    continue

                self._handle_request_exception(response, e)

            if response.json()["status"] == "pending-evaluation":
                if time.time() > self.request_timeout:  # type: ignore
                    msg = {"reqId": response_id}
                    if self.asset_id:
                        msg["assetId"] = self.asset_id
                    raise TimeoutError(json.dumps(msg))

                log.info("Polling for cuOpt Response...")
                time.sleep(self.poll_interval)
            else:
                return self._handle_response(response.json())

    def _cleanup_response(self, cuopt_response_dict):
        if cuopt_response_dict["status"] == "fulfilled":
            if self.asset_id:
                log.debug("deleting asset")
                self._delete_asset()
            # This should always be a dictionary, but just in case ...
            response = cuopt_response_dict["response"]
            if isinstance(response, dict) and response:
                response["reqId"] = cuopt_response_dict["reqId"]
                if "warnings" in response:
                    for w in response["warnings"]:
                        log.warning(w)
                    del response["warnings"]
                if "notes" in response:
                    for n in response["notes"]:
                        log.info(n)
                    del response["notes"]
            else:
                response = {
                    "reqId": cuopt_response_dict["reqId"],
                    "response": response,
                }
            return response
        else:
            error_code = cuopt_response_dict["errorCode"]
            if error_code == 900:
                raise ValueError("Unknown/unexpected error")
            elif error_code == 901:
                raise ValueError("No request ID in message")
            elif error_code == 902:
                raise ValueError("No inference URL in message")
            elif error_code == 903:
                raise ValueError("No response queue in message")
            elif error_code == 910:
                raise ValueError("Asset download failure")
            elif error_code == 911:
                raise ValueError("Large response upload failure")
            else:
                raise ValueError("Unexpected error occurred")

    def repoll(self, req_id, asset_id=None):
        """
        Poll for a result when get_optimized_routes results in
        a TimeoutError exception. The req_id and asset_id are returned
        in the exception.

        Parameters
        ----------
        req_id : str
            A uuid identifying the original request, returned in
            a TimeoutError exception.
        asset_id : str
            A uuid identifying the asset used (if any) for the original
            request, returned in a TimeoutError exception. The client
            will delete this asset when a result is returned.
        """
        if (not self.token) and (not self._check_token_cache()):
            log.info("Requesting New Token")
            self._get_jwt_token()
        if asset_id:
            self.asset_id = asset_id
        self.request_timeout = time.time() + self.request_excess_timeout  # type: ignore

        return self._cleanup_response(self._poll_for_response(req_id))

    # Get optimized routes for the given cuOpt problem instance
    def get_optimized_routes(self, cuopt_problem_json_data):
        """
        Get optimized routing solution for a given problem.

        Parameters
        ----------
        cuopt_problem_json_data : dict or str
            This is either the problem data as a dictionary or the
            path of a file containing the problem data. The file may be
            a pickle file containing a dictionary, or a text file containing
            a dictionary as JSON, or a zlib-compressed file containing a
            dictionary as JSON. Please refer to the server doc for the
            structure of this dictionary.
        """
        action = (
            "cuOpt_OptimizedRouting"
            if not self.only_validate
            else "cuOpt_RoutingValidator"
        )
        cuopt_response_dict = self._send_request(
            cuopt_problem_json_data, action=action
        )
        # If we get a pending response, poll until we get something
        # different or a timeout
        if cuopt_response_dict["status"] == "pending-evaluation":
            if self.request_excess_timeout == 0:
                self.request_timeout = self.request_start_time
            else:
                self.request_timeout = (
                    self.request_start_time + self.request_excess_timeout  # type: ignore
                )
            cuopt_response_dict = self._poll_for_response(
                cuopt_response_dict["reqId"]
            )

        return self._cleanup_response(cuopt_response_dict)

    def get_functions(self):
        """
        Lists all availble functions for the user in NVCF.
        """
        if (not self.token) and (not self._check_token_cache()):
            log.info("Requesting New Token")
            self._get_jwt_token()

        headers = {
            "Authorization": f"Bearer {self.token}",
        }

        try:
            response = requests.get(
                self.functions_url, headers=headers, timeout=30
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            self._handle_request_exception(response, e)
        res = response.json()

        if "functions" in res:
            res["functions"] = [
                f
                for f in res["functions"]
                if "containerImage" not in f
                or f["containerImage"].split("/")[-1].split(":")[0] == "cuopt"
            ]
        self._version_cache(res.get("functions", []))
        return res

    def set_function_by_name(self, name, version_id=None):
        """
        Set the function to invoke by name and optionally specify a
        version. The current list of functions can be retrieved with
        get_functions().

        Parameters
        ----------
        name : str
            Name of a function to invoke. If name is the empty
            string and all available functions have the same name,
            that name will be used.
        version_id: str
            Optional version id of the function to invoke. If there
            are multiple versions of the named function, version_id
            can be used to select a particular version. If version_id is
            not set, the latest version of the named function will be chosen.
        """
        versions = self._read_version_cache()

        # If name is unspecified and there is only one
        # named function available, use that name
        if not name:
            if len(versions["by_name"]) == 1:
                name = list(versions["by_name"].keys())[0]
            else:
                raise ValueError(
                    "More than one named function available, "
                    "specify a function name or id"
                )
        elif name not in versions["by_name"]:
            raise ValueError(f"No function available with name {name}")

        if version_id:
            vers = {
                v["version_id"]: v["id"]
                for x in versions["by_name"][name]["versions"].values()
                for v in x
            }
            if version_id not in vers.keys():
                raise ValueError(
                    f"Version {version_id} of {name} does not exist"
                )
            maxMajor = str(versions["by_name"][name]["maxMajor"])
            maxMajorVersion = versions["by_name"][name]["versions"][maxMajor][
                0
            ]["version_id"]
            if version_id != maxMajorVersion:
                log.warning(
                    f"Warning: latest version for {name} is {maxMajorVersion}, "  # noqa
                    f"version {version_id} is deprecated"
                )
            self.function_id = vers[version_id]
            self.function_version_id = version_id
        else:
            maxMajor = str(versions["by_name"][name]["maxMajor"])
            self.function_id = versions["by_name"][name]["versions"][maxMajor][
                0
            ]["id"]
            self.function_version_id = versions["by_name"][name]["versions"][
                maxMajor
            ][0]["version_id"]

        self.function_name = name

    def set_function_by_id(self, id, version_id=None):
        """
        Set the function to invoke by id and optionally specify a
        version. The current list of functions can be retrieved with
        get_functions().

        Parameters
        ----------
        id : str
            The id of a function to invoke.
        version_id: str
            Optional version id of the function to invoke. If there
            are multiple versions of the function specified by id, version_id
            can be used to select a particular version. If version_id is
            not set, the latest version of the specified function will be
            chosen.
        """

        versions = self._read_version_cache()

        if id not in versions["by_id"]:
            raise ValueError(f"No function available with id {id}")

        name = versions["by_id"][id]["name"]
        latest_version = versions["by_id"][id]["version_id"]
        if not version_id:
            version_id = latest_version

        if latest_version != version_id:
            vers = {
                v["version_id"]: v["id"]
                for x in versions["by_name"][name]["versions"].values()
                for v in x
            }
            if version_id not in vers.keys() or vers[version_id] != id:
                raise ValueError(
                    f"Version {version_id} of {id} does not exist"
                )
            else:
                log.warning(
                    f"Warning: latest version of {id} is {latest_version}, "
                    f"version {version_id} is deprecated"
                )

        self.function_name = name
        self.function_id = id
        self.function_version_id = version_id
