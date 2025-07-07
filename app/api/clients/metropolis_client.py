# Copyright (c) 2022-2025, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import copy
import logging
import math
from typing import List, Optional

import pydantic
from scipy.spatial import KDTree

from app.api.clients.base_api_client import BaseAPIClient
from app.common.waypoint_graph import WaypointGraph


class GetUniqueObjects(pydantic.BaseModel):
    place: str = "city=Santa Clara/building=K"
    timestamp: Optional[str] = None
    time_window_in_ms: Optional[int] = pydantic.Field(
        default=5000, alias="timeWindowInMs")


class LocationItem(pydantic.BaseModel):
    id: str
    locations: List[List[int]]


class UniqueObjectsLocations(pydantic.BaseModel):
    place: str
    timestamp: str
    count: int
    locations_of_objects: List[LocationItem] = pydantic.Field(
        alias="locationsOfObjects")


class MetropolisClient(BaseAPIClient):
    """ Mission Control API client """
    _config: dict = {}
    _endpoints: dict = {
        "traffic": {
            "path": "/tracker/unique-object-count-with-locations"
        }
    }

    def get_traffic(self, tracker: GetUniqueObjects):
        """ Calls the metropolis API endpoint """
        logging.info("Getting traffic data from Metropolis")
        endpoint_info = self._endpoints["traffic"]
        endpoint = self._base_url + endpoint_info["path"]

        return self.make_request_with_logs("post", endpoint, "Metropolis error",
                                           "Sent request to Metropolis for getting traffic data",
                                           params=tracker.dict)


class TrafficUpdater:
    """ Traffic Update """

    def __init__(self, graph: WaypointGraph):
        """ Initialize the class with the original graph and proximity threshold """
        self.graph = graph

        # Extract nodes and edges
        self.nodes = self.graph.nodes
        self.edges = self.extract_edges_in_sequence(
            self.graph.offsets, self.graph.edges)

        # Create a KD-tree for spatial indexing
        node_coords = [(node["x"], node["y"]) for node in self.nodes]
        self.tree = KDTree(node_coords)

    def get_people_locations(self, metropolis_data: UniqueObjectsLocations):
        """ Extract the last location from each object's locations and gather people's locations """
        people_locations = []

        for obj in metropolis_data.locations_of_objects:
            locations = obj.locations
            if locations:
                last_location = locations[-1]
                people_locations.append(last_location)

        return people_locations

    def extract_edges_in_sequence(self, offset: list, edges: list):
        """ Extract edges in sequence from the offset and edges arrays """
        edge_list = []

        for i in range(len(offset) - 1):
            start_idx = offset[i]
            end_idx = offset[i + 1]
            vertex_edges = edges[start_idx:end_idx]
            edge_list.extend([(i, dest) for dest in vertex_edges])

        return edge_list

    def calculate_influence_factor(self, person_location, node_coords):
        """ Calculate influence factor based on distance between person and node """
        person_x, person_y = person_location
        node_x, node_y = node_coords

        distance = math.sqrt((person_x - node_x)**2 + (person_y - node_y)**2)
        influence_factor = 1 / (distance + 1)

        return influence_factor

    def update_graph_weights_with_traffic(self, metropolis_data,
                                          proximity_threshold: float = 2.0,
                                          scaling_factor: float = 1.0):
        """ Update graph weights based on traffic influence """
        people_locations = self.get_people_locations(metropolis_data)
        updated_weights = copy.deepcopy(self.graph.weights)
        affected_nodes = []
        affected_edges = []
        for person_location in people_locations:
            # Query nodes within proximity to the person's location
            nearby_node_indices = self.tree.query_ball_point(
                person_location, proximity_threshold)
            affected_nodes.extend(nearby_node_indices)
            # Calculate influence factor for nodes
            for node_index in nearby_node_indices:
                influence_factor = self.calculate_influence_factor(
                    person_location,
                    (self.nodes[node_index]["x"], self.nodes[node_index]["y"])
                )
                # Consider edges connected to influenced nodes as influenced
                for idx, edge in enumerate(self.edges):
                    if node_index in edge:
                        affected_edges.append(idx)
                        adjusted_weight = updated_weights[idx] * \
                            (1 + influence_factor * scaling_factor)
                        updated_weights[idx] = round(
                            adjusted_weight, 2)
        logging.debug("Original Graph Weights: %s", self.graph.weights)
        logging.debug("Updated Graph Weights: %s", updated_weights)
        return updated_weights, affected_nodes, affected_edges
