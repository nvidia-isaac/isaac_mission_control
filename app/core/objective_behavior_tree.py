"""
SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
Copyright (c) 2021-2025, NVIDIA CORPORATION & AFFILIATES. All rights reserved.

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


def tree2objective_state(type: py_trees.common.Status) -> objective.ObjectiveStateV1:
    if type == py_trees.common.Status.SUCCESS:
        return objective.ObjectiveStateV1.COMPLETED
    elif type == py_trees.common.Status.FAILURE:
        return objective.ObjectiveStateV1.FAILED
    elif type == py_trees.common.Status.RUNNING:
        return objective.ObjectiveStateV1.RUNNING
    else:
        return objective.ObjectiveStateV1.PENDING


def objective2tree_state(type: objective.ObjectiveStateV1) -> py_trees.common.Status:
    if type == objective.ObjectiveStateV1.COMPLETED:
        return py_trees.common.Status.SUCCESS
    elif type == objective.ObjectiveStateV1.RUNNING:
        return py_trees.common.Status.RUNNING
    elif type == objective.ObjectiveStateV1.PENDING:
        return py_trees.common.Status.INVALID
    else:
        return py_trees.common.Status.FAILURE


class ObjectiveLeafNode(py_trees.behaviour.Behaviour):
    """
    Behavior tree node
    """

    def __init__(self, objective_node: objective.ObjectiveBehaviorNode,
                 running_nodes: list, status=py_trees.common.Status.INVALID):
        self.objective_node = objective_node
        self.node_type = objective_node.node_type
        self.running_nodes = running_nodes
        self.status = status
        super(ObjectiveLeafNode, self).__init__(  # pylint: disable=super-with-arguments
            name=objective_node.node_type.value)

    def initialise(self):
        self.status = py_trees.common.Status.RUNNING

    def update(self) -> py_trees.common.Status:
        if self.objective_node.state == objective.ObjectiveStateV1.PENDING:
            if self not in self.running_nodes:
                self.running_nodes.append(self)
            return py_trees.common.Status.RUNNING
        else:
            return objective2tree_state(self.objective_node.state)


class SequenceNode(py_trees.composites.Sequence):
    """
    Sequence behavior tree node
    """

    def __init__(self, objective_node: objective.ObjectiveCompositeNode,
                 status=py_trees.common.Status.INVALID):
        self.objective_node = objective_node
        self.status = status
        super().__init__(name="Sequence", memory=True)


class SelectorNode(py_trees.composites.Selector):
    """
    Selector behavior tree node
    """

    def __init__(self, objective_node: objective.ObjectiveCompositeNode,
                 status=py_trees.common.Status.INVALID):
        self.objective_node = objective_node
        self.status = status
        super().__init__(name="Selector", memory=True)


class ParallelNode(py_trees.composites.Parallel):
    """
    Selector behavior tree node
    """

    def __init__(self, objective_node: objective.ObjectiveCompositeNode,
                 status=py_trees.common.Status.INVALID):
        self.objective_node = objective_node
        self.status = status
        super().__init__(name="Parallel",
                         policy=py_trees.common.ParallelPolicy.SuccessOnAll())


class ObjectiveBehaviorTree():
    """Objective behavior Tree
    """

    def __init__(self, objective_obj: objective.ObjectiveV1, running_nodes: list):
        # The behavior tree has an implicit sequence node as its root which is named “root”
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
        if objective_node.node_class == objective.ObjectiveNodeClass.COMPOSITE:
            if objective_node.node_type == objective.ObjectiveNodeType.SELECTOR:
                curr_node = SelectorNode(objective_node=objective_node)  # type: ignore
            elif objective_node.node_type == objective.ObjectiveNodeType.SEQUENCE:
                curr_node = SequenceNode(objective_node=objective_node)  # type: ignore
            elif objective_node.node_type == objective.ObjectiveNodeType.PARALLEL:
                curr_node = ParallelNode(objective_node=objective_node)  # type: ignore
            for child in objective_node.children:  # type: ignore[attr-defined]
                curr_node.add_child(ObjectiveBehaviorTree.objective_to_tree(child, running_nodes))
            return curr_node
        elif objective_node.node_class == objective.ObjectiveNodeClass.BEHAVIOR:
            return ObjectiveLeafNode(objective_node=objective_node,  # type: ignore
                                     running_nodes=running_nodes)
        # Decorator not supported for now
        # elif objective_node.node_class == objective.ObjectiveNodeClass.DECORATOR:
        #     pass
        else:
            raise ValueError("invalid node type")

    def update(self):
        logging.info("Updating behavior tree")
        self.root.tick_once()
        self.post_tick()
        logging.debug("\n%s", py_trees.display.unicode_tree(root=self.root,
                      show_status=True, indent=3))

    def post_tick(self):
        # Update all the non-pending control node
        for node in self.root.iterate():
            if isinstance(node, py_trees.composites.Composite):
                node.objective_node.state = tree2objective_state(  # type: ignore[attr-defined]
                    node.status)
