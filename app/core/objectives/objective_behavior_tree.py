"""
SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

SPDX-License-Identifier: Apache-2.0
"""
import py_trees
import logging
from cloud_common.objects import objective
from app.core.objectives.objectives_common import (
    ObjectiveLeafNode, 
    SelectorNode, 
    SequenceNode, 
    ParallelNode, 
    tree2objective_state,
    ConditionalNode,
    RetryNode,
    InverterNode,
    RepeatNode)


logger = logging.getLogger("Isaac Mission Control")


class ObjectiveBehaviorTree():
    """Objective behavior Tree
    """

    def __init__(self, objective_obj: objective.ObjectiveV1, running_nodes: list):
        self.objective_obj = objective_obj
        self.failure_reason = ""
        self.running_nodes = running_nodes
        self.root = self.objective_to_tree(
            self.objective_obj.status.objective_tree, running_nodes)  # type: ignore
        logging.info("\n%s", py_trees.display.ascii_tree(
            root=self.root, show_status=True, indent=3))

    @property
    def current_node(self) -> ObjectiveLeafNode:
        # Recursive function to extract the last running node of the tree
        return self.root.tip()

    @property
    def status(self) -> py_trees.common.Status:
        return self.root.status

    @property
    def has_completed(self) -> bool:
        return self.root.status in (py_trees.common.Status.SUCCESS, py_trees.common.Status.FAILURE)

    @staticmethod
    def objective_to_tree(objective_node: objective.ObjectiveNode, running_nodes: list):
        """
        Convert an objective node to a behavior tree node.
        """
        if objective_node.node_class == objective.ObjectiveNodeClass.COMPOSITE:
            if objective_node.node_type == objective.ObjectiveNodeType.SELECTOR:
                curr_node = SelectorNode(objective_node=objective_node)  # type: ignore
            elif objective_node.node_type == objective.ObjectiveNodeType.SEQUENCE:
                curr_node = SequenceNode(objective_node=objective_node)  # type: ignore
            elif objective_node.node_type == objective.ObjectiveNodeType.PARALLEL:
                curr_node = ParallelNode(objective_node=objective_node)  # type: ignore
            else:
                raise ValueError("Invalid Composite Node Type")
            for child in objective_node.children:  # type: ignore[attr-defined]
                curr_node.add_child(ObjectiveBehaviorTree.objective_to_tree(child, running_nodes))
            return curr_node
        elif objective_node.node_class == objective.ObjectiveNodeClass.BEHAVIOR:
            return ObjectiveLeafNode(objective_node=objective_node,  # type: ignore
                                     running_nodes=running_nodes)
        elif objective_node.node_class == objective.ObjectiveNodeClass.DECORATOR:
            child = ObjectiveBehaviorTree.objective_to_tree(objective_node.child, running_nodes)
            if objective_node.node_type == objective.ObjectiveNodeType.CONDITIONAL:
                curr_node = ConditionalNode(objective_node=objective_node, child=child)  # type: ignore
            elif objective_node.node_type == objective.ObjectiveNodeType.RETRY:
                curr_node = RetryNode(objective_node=objective_node, child=child)  # type: ignore
            elif objective_node.node_type == objective.ObjectiveNodeType.INVERTER:
                curr_node = InverterNode(objective_node=objective_node, child=child)  # type: ignore
            elif objective_node.node_type == objective.ObjectiveNodeType.REPEAT:
                curr_node = RepeatNode(objective_node=objective_node, child=child)  # type: ignore
            else:
                raise ValueError("Invalid Decorator Node Type")
            return curr_node
        else:
            raise ValueError("invalid node type")

    def update(self):
        logger.debug("Updating behavior tree")
        self.root.tick_once()
        logger.debug("First tick nodes: %s", self.running_nodes)
        self.post_tick()
        # In the case of a Retry or Repeat node, we need to tick the tree again
        # to reset the state of the child node and add it to the running nodes again.
        # For clarity on why we do this:
        # - Let's say on the first tick, the child of the Repeat node is ticked and returns SUCCESS.
        # - The child has been removed from the running nodes list.
        # - The Repeat node will then increment num_success, but remain in the RUNNING state.
        # - If we don't tick the tree again, the child will not be ticked again and the objective will never complete.
        # - We need to tick the tree again to reset the state of the child node and add it to the running nodes again.
        if not self.has_completed:
            self.root.tick_once()
            self.post_tick()
            logger.debug("Second tick nodes: %s", self.running_nodes)
        logger.debug("\n%s", py_trees.display.unicode_tree(root=self.root,
                        show_status=True, indent=3))

    def post_tick(self):
        # Update all the non-pending control node
        for node in self.root.iterate():
            if isinstance(node, py_trees.composites.Composite):
                node.objective_node.state = tree2objective_state(  # type: ignore[attr-defined]
                    node.status)
            elif isinstance(node, py_trees.decorators.Decorator):
                node.objective_node.state = tree2objective_state(  # type: ignore[attr-defined]
                    node.status)

