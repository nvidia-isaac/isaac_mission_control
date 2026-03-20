"""
SPDX-FileCopyrightText: NVIDIA CORPORATION & AFFILIATES
Copyright (c) 2023-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.

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
import threading
import datetime
import inspect
import re
from typing import Any, Dict, List
from cloud_common.objects.objective import ObjectiveNodeType


# =============================================================================
# CONFIGURATION SECTION
# =============================================================================

# Output extractors for node outputs - focused on safe, grouped data
OUTPUT_EXTRACTORS = {
    ObjectiveNodeType.OBJ_DETECTION: {
        # Class information
        "class_ids": lambda result: [str(obj.class_id) for obj in result],
        "detection_count": lambda result: len(result),
        "detection_timestamp": lambda: datetime.datetime.now().isoformat(),
        
        # Objects grouped by class ID for easy access
        "object_id_by_class": lambda result: {
            str(class_id): [obj.object_id for obj in result if obj.class_id == class_id]
            for class_id in set(obj.class_id for obj in result)
        },
        # Object pose 2D by class
        "object_pose2D_by_class": lambda result: {
            str(class_id): [
                {
                    "x": obj.bbox2d.center.x,
                    "y": obj.bbox2d.center.y,
                    "theta": obj.bbox2d.center.theta
                } for obj in result if obj.class_id == class_id and obj.bbox2d and obj.bbox2d.center
            ]
            for class_id in set(obj.class_id for obj in result)
        },
        # Object pose 3D by class
        "object_pose3D_by_class": lambda result: {
            str(class_id): [
                {
                    "pos_x": obj.bbox3d.center.position.x,
                    "pos_y": obj.bbox3d.center.position.y,
                    "pos_z": obj.bbox3d.center.position.z,
                    "quat_x": obj.bbox3d.center.orientation.x,
                    "quat_y": obj.bbox3d.center.orientation.y,
                    "quat_z": obj.bbox3d.center.orientation.z,
                    "quat_w": obj.bbox3d.center.orientation.w
                } for obj in result if obj.class_id == class_id and obj.bbox3d and obj.bbox3d.center
            ]
            for class_id in set(obj.class_id for obj in result)
        },
        
        # Status flags
        "has_objects": lambda result: len(result) > 0,
    },
    
    ObjectiveNodeType.APRILTAG_DETECTION: {
        # Tag information
        "tag_ids": lambda result: [tag.tag_id for tag in result],
        "tag_count": lambda result: len(result),
        "detection_timestamp": lambda: datetime.datetime.now().isoformat(),
        
        # Poses accessible by index - flattened for direct use with PickPlace schema
        "tags_pose": lambda result: [
            {
                "pos_x": tag.pose.position.x,
                "pos_y": tag.pose.position.y,
                "pos_z": tag.pose.position.z,
                "quat_x": tag.pose.orientation.x,
                "quat_y": tag.pose.orientation.y,
                "quat_z": tag.pose.orientation.z,
                "quat_w": tag.pose.orientation.w
            } for tag in result if tag.pose
        ],
        
        # Poses grouped by tag ID - flattened for direct use with PickPlace schema
        "tags_pose_by_id": lambda result: {
            str(tag.tag_id): {
                "pos_x": tag.pose.position.x,
                "pos_y": tag.pose.position.y,
                "pos_z": tag.pose.position.z,
                "quat_x": tag.pose.orientation.x,
                "quat_y": tag.pose.orientation.y,
                "quat_z": tag.pose.orientation.z,
                "quat_w": tag.pose.orientation.w
            } for tag in result if tag.pose
        },
        
        # Status flags
        "has_tags": lambda result: len(result) > 0,
    },
    
    ObjectiveNodeType.NAVIGATION: {
        "completion_time": lambda: datetime.datetime.now().isoformat(),
        "mission_success": lambda: True,
    },
    
    ObjectiveNodeType.PICKPLACE: {
        "completion_time": lambda: datetime.datetime.now().isoformat(),
        "mission_success": lambda: True,
    },
    
    ObjectiveNodeType.CHARGING: {
        "completion_time": lambda: datetime.datetime.now().isoformat(),
        "mission_success": lambda: True,
    },
    
    ObjectiveNodeType.UNDOCK: {
        "completion_time": lambda: datetime.datetime.now().isoformat(),
        "mission_success": lambda: True,
    }
}


# =============================================================================
# CONTEXT IMPLEMENTATION
# =============================================================================

class ContextAccessError(Exception):
    """Specific exception for context access failures"""
    pass


class ObjectivesContext:
    """
    Simplified thread-safe context for sharing data between objective nodes.
    
    Supports simple variable resolution with $variable format.
    Examples:
    - Simple reference: $variable_name
    - Dictionary access: $object_ids['3']
    - Array indexing: $object_ids['3'][0]
    - Attribute access: $tag_poses['2'].pos_x (dictionaries from output extractors)
    
    Security: Only allows access to dictionaries created by output extractors.
    All data access must go through output extractors in node 'outputs'.
    """
    
    def __init__(self):
        self._variables: Dict[str, Any] = {}
        self._lock = threading.Lock()
    
    # === PUBLIC API ===
    
    def set_variable(self, name: str, value: Any) -> None:
        """Store variable in context with thread safety."""
        with self._lock:
            self._variables[name] = value
    
    def get_variable(self, name: str, default: Any = None) -> Any:
        """Retrieve variable from context with thread safety."""
        with self._lock:
            return self._variables.get(name, default)
    
    def has_variable(self, name: str) -> bool:
        """Check if variable exists in context."""
        with self._lock:
            return name in self._variables

    def resolve_parameters(self, params: dict) -> dict:
        """Replace $variable references with actual values in parameters."""
        resolved = {}
        
        for key, value in params.items():
            if isinstance(value, str) and value.startswith('$'):
                try:
                    resolved[key] = self._resolve_variable_path(value)
                except ContextAccessError as e:
                    raise ContextAccessError(f"Context resolution failed for parameter {key}={value}: {e}") from e
            else:
                resolved[key] = value
                
        return resolved

    # === PRIVATE RESOLUTION METHODS ===

    def _resolve_variable_path(self, path: str) -> Any:
        """
        Resolve variable path like:
        - $object_ids -> get variable object_ids
        - $object_ids['3'] -> get variable object_ids, then key '3'  
        - $object_ids['3'][0] -> get variable object_ids, then key '3', then index 0
        - $tag_poses['2'].pos_x -> get variable tag_poses, then key '2', then attribute pos_x
        """
        # Remove $ prefix
        path = path[1:]
        
        # Security checks
        if '__' in path:
            raise ContextAccessError("Double underscore access not allowed")
        
        if len(path) > 100:  # Prevent extremely long paths
            raise ContextAccessError("Variable path too long")
        
        # Parse into parts: variable_name + [access_parts]
        variable_name, access_parts = self._parse_variable_path(path)
        
        # Security: Limit depth to prevent deep traversal attacks
        if len(access_parts) > 5:
            raise ContextAccessError("Variable path depth limited to 5 levels")
        
        # Get base variable
        current = self.get_variable(variable_name)
        if current is None:
            raise ContextAccessError(f"Variable '{variable_name}' not found")
        
        # Apply each access part sequentially
        for part in access_parts:
            current = self._apply_access(current, part)
        
        return current
    
    def _parse_variable_path(self, path: str) -> tuple[str, List[str]]:
        """
        Parse variable path using regex while disallowing nested brackets.
        
        This function parses variable references in the format: $variable_name[key].attr
        Examples:
        - $poses[0].pos_x → variable_name="poses", parts=["[0]", ".pos_x"]
        - $object_ids['3'][0] → variable_name="object_ids", parts=["['3']", "[0]"]
        
        Args:
            path: The variable path string starting with $ (e.g., "$objects['3'][0]")
            
        Returns:
            tuple: (variable_name, list_of_access_parts)
        """
        # REGEX BREAKDOWN:
        # ^([a-zA-Z_][a-zA-Z0-9_]*) - Capture group 1: Variable name
        #   - Must start with letter or underscore
        #   - Followed by letters, digits, or underscores
        # ((?:\[[^\[\]]*\]|\.[A-Za-z_][A-Za-z0-9_]*)*) - Capture group 2: Access chain
        #   - Non-capturing group (?:...) repeated zero or more times
        #   - Either: \[[^\[\]]*\] (bracket notation: [key] with no nested brackets)
        #   - Or: \.[A-Za-z_][A-Za-z0-9_]* (dot notation: .attribute, only allowed for
        #     dictionary keys)
        # $ - End of string
        pattern = r"^([a-zA-Z_][a-zA-Z0-9_]*)((?:\[[^\[\]]*\]|\.[A-Za-z_][A-Za-z0-9_]*)*)$"
        match = re.match(pattern, path)
        if not match:
            raise ContextAccessError(f"Invalid variable path format: {path}")

        variable_name: str = match.group(1)
        access_string: str = match.group(2)

        # Extract each access part while preserving delimiters ( [key] / .attr )
        parts: List[str] = []
        if access_string:
            parts = re.findall(r"\[[^\[\]]*\]|\.[A-Za-z_][A-Za-z0-9_]*", access_string)

        # Final safeguard against nested brackets
        for part in parts:
            if part.startswith('[') and '[' in part[1:-1]:
                raise ContextAccessError(f"Nested brackets not allowed in context variable: {path}")

        return variable_name, parts
    
    def _apply_access(self, obj: Any, access_part: str) -> Any:
        """Apply single access operation with security checks"""
        if access_part.startswith('[') and access_part.endswith(']'):
            # Array/dict access: ['3'] or [0]
            return self._safe_index_access(obj, access_part)
            
        elif access_part.startswith('.'):
            # Attribute access: .pos_x (STRICT SECURITY REQUIRED)
            return self._safe_attribute_access(obj, access_part)
            
        else:
            raise ContextAccessError(f"Invalid access part: {access_part}")
    
    def _safe_index_access(self, obj: Any, access_part: str) -> Any:
        """Safely handle array/dict indexing"""
        index_str = access_part[1:-1]  # Remove brackets
        
        # Block any dangerous index attempts
        if '__' in index_str:
            raise ContextAccessError("Double underscore access not allowed in indexing")
        
        try:
            if index_str.startswith('"') or index_str.startswith("'"):
                # String key: ['3'] -> '3'
                key = index_str.strip('"\'')
                if not isinstance(obj, (dict, list)):
                    raise ContextAccessError(f"Cannot index object of type {type(obj)}")
                return obj[key]
                
            elif index_str.isdigit():
                # Numeric index/key: [0] -> 0
                index = int(index_str)
                if isinstance(obj, (list, tuple)):
                    if index < 0:
                        raise ContextAccessError("Negative indexing not allowed for safety")
                    return obj[index]
                elif isinstance(obj, dict):
                    # Try numeric key on dictionary (e.g., tag_id: 2)
                    return obj[index]
                else:
                    raise ContextAccessError(f"Cannot use numeric index on {type(obj)}")
                
            else:
                # Direct key access - treat as string key
                # This is safe for dictionary access: obj['key_name']
                if not isinstance(obj, dict):
                    raise ContextAccessError(f"Cannot access key '{index_str}' on non-dict type {type(obj)}")
                
                # Basic safety checks for the key
                if len(index_str) > 50:  # Prevent extremely long keys
                    raise ContextAccessError(f"Key too long: {len(index_str)} chars")
                if '\x00' in index_str:  # Prevent null bytes
                    raise ContextAccessError("Null bytes not allowed in keys")
                
                return obj[index_str]
                
        except (IndexError, KeyError) as e:
            raise ContextAccessError(f"Index/key access failed for {access_part}: {e}") from e
    
    def _safe_attribute_access(self, obj: Any, access_part: str) -> Any:
        """Check object's actual fields when attribute access is attempted"""
        attr_name = access_part[1:]  # Remove dot
        
        # SECURITY: Block dangerous patterns
        if attr_name.startswith('_'):
            raise ContextAccessError(f"Private attribute '{attr_name}' not allowed")
        
        # SECURITY: Only allow attribute access on dictionaries from output extractors
        if isinstance(obj, dict):
            # Dictionaries in context come from output extractors, so they're safe by design
            if attr_name not in obj:
                raise ContextAccessError(f"Key '{attr_name}' not found in dictionary")
            
            return obj[attr_name]
        
        else:
            # All other objects blocked - must use output extractors
            raise ContextAccessError(
                "Attribute access only allowed on dictionaries from output extractors. "
                "Use output extractors in node 'outputs' to access object fields."
            )




# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def validate_output_extractors(node_type: ObjectiveNodeType, outputs: dict) -> None:
    """Validate that all output keys are allowed output extractor keys for the node type."""
    allowed_output_keys = OUTPUT_EXTRACTORS.get(node_type, {}).keys()
    for output_key in outputs.keys():
        if output_key not in allowed_output_keys:
            raise ValueError(
                f"Invalid output key '{output_key}' for node type {node_type}. "
                f"Available output extractor keys: {sorted(allowed_output_keys)}"
            )


def extract_outputs_from_result(node_type: ObjectiveNodeType, outputs: dict, result: Any) -> Dict[str, Any]:
    """Extract output values from mission results using output extractors."""
    extractors = OUTPUT_EXTRACTORS.get(node_type, {})
    extracted_values = {}
    
    for vocab_key, context_var_name in outputs.items():
        extractor = extractors[vocab_key]
        
        if callable(extractor):
            sig = inspect.signature(extractor)
            if len(sig.parameters) == 0:
                value = extractor()
            else:
                value = extractor(result)
        else:
            value = extractor
            
        extracted_values[context_var_name] = value
    
    return extracted_values 