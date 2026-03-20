# Objectives Context System - User Guide

## Overview

The Objectives Context System enables behavior trees where nodes can share data. Previous nodes store results, and subsequent nodes can reference that data to create dynamic, adaptive missions.

## Key Features

- **Simple Variable References**: Use `$variable` to access stored data
- **Vocabulary Extractors**: Pre-defined, safe data extractors for common patterns
- **Offset Parameters**: Built-in support for position/orientation adjustments
- **Safe Access**: Schema-validated attribute access with security restrictions

## Basic Syntax

### Variable References
Reference stored data using `$variable_name`:

```json
{
  "object_id": "$object_ids['3'][0]",
  "pos_x": "$tag_poses['2'].pos_x",
  "pos_y": "$tag_poses['2'].pos_y"
}
```

### Supported Access Patterns
- **Simple variables**: `$my_variable`
- **Dictionary keys**: `$objects['3']` or `$objects[key_name]` (quoted strings for IDs)
- **Array indexing**: `$poses[0]`, `$poses[2]` (unquoted integers for positions)
- **Combined access**: `$object_ids['3'][0]`
- **Attribute access**: `$pose.pos_x`, `$pose.quat_w`

### Key vs Index Access
**Important:** Dictionary keys (IDs) use quoted strings, array positions use unquoted integers:

```json
{
  "by_class_id": "$object_ids['3'][0]",    // Class ID "3", first object
  "by_tag_id": "$tag_poses['2'].pos_x",    // Tag ID "2" pose
  "by_position": "$poses[2].pos_x"         // 3rd detected tag (index 2)
}
```

## Node Types and Vocabulary

### Object Detection (`OBJ_DETECTION`)

**Available Extractors:**
- `class_ids` - List of detected class IDs (as strings)
- `detection_count` - Number of objects detected
- `object_id_by_class` - Object IDs grouped by class ID
- `object_pose2D_by_class` - 2D pose data (x, y, theta) grouped by class ID
- `object_pose3D_by_class` - 3D pose data (pos_x, pos_y, pos_z, quat_x, quat_y, quat_z, quat_w) grouped by class ID
- `has_objects` - Boolean: true if any objects detected
- `detection_timestamp` - ISO timestamp when detection completed

**Example:**
```json
{
  "node_type": "OBJ_DETECTION",
  "parameters": {"robot_name": "arm01"},
  "outputs": {
    "object_id_by_class": "object_ids",
    "object_pose3D_by_class": "object_poses",
    "detection_count": "num_objects"
  }
}
```

### AprilTag Detection (`APRILTAG_DETECTION`)

**Available Extractors:**
- `tag_ids` - List of detected tag IDs (as integers)
- `tag_count` - Number of tags detected
- `tags_pose` - Array of flattened pose data (indexed by detection order)
- `tags_pose_by_id` - Flattened pose data grouped by tag ID (keyed by tag ID string)
- `has_tags` - Boolean: true if any tags detected
- `detection_timestamp` - ISO timestamp when detection completed

**Example:**
```json
{
  "node_type": "APRILTAG_DETECTION", 
  "parameters": {"robot_name": "arm01"},
  "outputs": {
    "tags_pose_by_id": "tag_poses",
    "tag_count": "num_tags"
  }
}
```

**Access Patterns:**
```json
{
  // Access by tag ID (quoted string keys)
  "pos_x": "$tag_poses['2'].pos_x",    // Tag ID "2" pose  
  "pos_y": "$tag_poses['0'].pos_y",    // Tag ID "0" pose
  
  // Access by detection order (unquoted integer index)  
  "pos_x": "$tag_list[0].pos_x",       // First detected tag
  "pos_y": "$tag_list[2].pos_y"        // Third detected tag
}
```

**Two Access Methods:**
- `tags_pose_by_id` → Dictionary keyed by tag ID strings: `$tag_poses['2'].pos_x`
- `tags_pose` → Array indexed by detection order: `$tag_list[0].pos_x`

### Other Node Types

**Navigation (`NAVIGATION`):**
- `completion_time` - ISO timestamp when navigation completed
- `mission_success` - Boolean: true (mission succeeded)

**PickPlace (`PICKPLACE`):**
- `completion_time` - ISO timestamp when pick and place completed  
- `mission_success` - Boolean: true (mission succeeded)

**Charging (`CHARGING`):**
- `completion_time` - ISO timestamp when charging completed
- `mission_success` - Boolean: true (mission succeeded)

**Undock (`UNDOCK`):**
- `completion_time` - ISO timestamp when undocking completed
- `mission_success` - Boolean: true (mission succeeded)

**Example for other node types:**
```json
{
  "node_type": "NAVIGATION",
  "parameters": {"robot_name": "robot_a", "route": [{"x": 10, "y": 20}]},
  "outputs": {
    "completion_time": "nav_completed_at",
    "mission_success": "nav_succeeded"
  }
}
```

## Flattened Pose Data

Pose data is automatically flattened for easy access:

**Instead of** `pose.position.x` **use** `pose.pos_x`

```json
{
  "pos_x": 1.5,     // position.x
  "pos_y": 2.5,     // position.y  
  "pos_z": 3.5,     // position.z
  "quat_x": 0.1,    // orientation.x
  "quat_y": 0.2,    // orientation.y
  "quat_z": 0.3,    // orientation.z
  "quat_w": 0.9     // orientation.w
}
```

## Offset Parameters

Handle position/orientation adjustments using offset parameters:

```json
{
  "node_type": "PICKPLACE",
  "parameters": {
    "robot_name": "arm01",
    "object_id": "$object_ids['3'][0]",
    "class_id": "3",
    
    // Base position from context
    "pos_x": "$tag_poses['2'].pos_x",
    "pos_y": "$tag_poses['2'].pos_y", 
    "pos_z": "$tag_poses['2'].pos_z",
    
    // Base orientation from context (detected object/tag pose)
    "quat_x": "$tag_poses['2'].quat_x",
    "quat_y": "$tag_poses['2'].quat_y",
    "quat_z": "$tag_poses['2'].quat_z", 
    "quat_w": "$tag_poses['2'].quat_w",
    
    // Offset adjustments (applied before mission execution)
    "pos_z_offset": 0.35,        // +35cm above detected position
    "pos_x_offset": -0.1,        // -10cm in X direction
    "yaw_offset": 1.57           // +90 degrees rotation around Z-axis
  }
}
```

**Available Offset Parameters:**
- `pos_x_offset`, `pos_y_offset`, `pos_z_offset` - Position offsets in meters
- `roll_offset`, `pitch_offset`, `yaw_offset` - Angular offsets in radians (Euler angles)

**Orientation Sources:**
- **From Context**: `"quat_x": "$tag_poses['2'].quat_x"` - Use detected object/tag orientation
- **Static Values**: `"quat_x": 0.707` - Use fixed orientation values

## Usage Examples

### Example 1: Context-Based Orientation + Euler Offsets
```json
{
  "node_type": "PICKPLACE",
  "parameters": {
    "robot_name": "arm01",
    "object_id": "$object_ids['3'][0]",
    "class_id": "3",
    
    // Position and orientation from detected AprilTag
    "pos_x": "$tag_poses['2'].pos_x",
    "pos_y": "$tag_poses['2'].pos_y", 
    "pos_z": "$tag_poses['2'].pos_z",
    "quat_x": "$tag_poses['2'].quat_x",
    "quat_y": "$tag_poses['2'].quat_y",
    "quat_z": "$tag_poses['2'].quat_z", 
    "quat_w": "$tag_poses['2'].quat_w",
    
    // Apply offsets for precise placement
    "pos_z_offset": 0.35,        // Lift 35cm above tag
    "yaw_offset": 1.57           // Rotate 90° for proper gripper alignment
  }
}
```

### Example 2: Static Orientation + Position from Context
```json
{
  "node_type": "PICKPLACE", 
  "parameters": {
    "robot_name": "arm01",
    "object_id": "$object_ids['box'][0]",
    "class_id": "box",
    
    // Position from detected object
    "pos_x": "$object_poses['box'][0].pos_x",
    "pos_y": "$object_poses['box'][0].pos_y",
    "pos_z": "$object_poses['box'][0].pos_z",
    
    // Fixed orientation (gripper pointing down)
    "quat_x": 0.707,
    "quat_y": 0.0,
    "quat_z": 0.0,
    "quat_w": 0.707,
    
    // Small adjustment for better grip
    "pos_z_offset": 0.05,
    "roll_offset": 0.1
  }
}
```

## Complete Workflow Example

```json
{
  "node_class": "COMPOSITE",
  "node_type": "SEQUENCE",
  "children": [
    {
      "node_class": "BEHAVIOR",
      "node_type": "OBJ_DETECTION",
      "parameters": {"robot_name": "arm01"},
      "outputs": {
        "object_id_by_class": "object_ids",
        "object_pose3D_by_class": "object_poses"
      }
    },
    {
      "node_class": "BEHAVIOR",
      "node_type": "APRILTAG_DETECTION",
      "parameters": {"robot_name": "arm01"},
      "outputs": {
        "tags_pose_by_id": "tag_poses"
      }
    },
    {
      "node_class": "BEHAVIOR",
      "node_type": "PICKPLACE",
      "parameters": {
        "robot_name": "arm01",
        "object_id": "$object_ids['3'][0]",
        "class_id": "3",
        "pos_x": "$tag_poses['2'].pos_x",
        "pos_y": "$tag_poses['2'].pos_y", 
        "pos_z": "$tag_poses['2'].pos_z",
        "pos_z_offset": 0.35,
        "quat_x": 0.996,
        "quat_y": 0.066,
        "quat_z": 0.042,
        "quat_w": 0.034
      }
    }
  ]
}
```

## Security Features

- **Safe Attribute Access**: Only Pydantic model fields are accessible
- **Path Validation**: Blocks dangerous patterns like `__class__`, `_private`
- **Depth Limits**: Maximum 5 levels of nested access
- **Length Limits**: Variable paths limited to 100 characters
- **Type Safety**: Validates dictionary/array access types

## Best Practices

### 1. Use Descriptive Variable Names
```json
"outputs": {
  "object_id_by_class": "warehouse_objects",
  "tags_pose_by_id": "dock_positions"
}
```

### 2. Leverage Offset Parameters
```json
{
  "pos_z": "$detected_height",
  "pos_z_offset": 0.1,  // Add 10cm safety margin
  "pos_x_offset": -0.05 // Slight adjustment for gripper alignment
}
```

### 3. Handle Multiple Objects
```json
{
  "first_object": "$object_ids['3'][0]",   // First object of class '3'
  "second_object": "$object_ids['3'][1]",  // Second object of class '3'
  "backup_object": "$object_ids['5'][0]"   // Fallback to different class
}
```

## Troubleshooting

**Variable Not Found:**
```
ContextAccessError: Variable 'my_var' not found
```
- Check that a previous node set this variable in `outputs`
- Verify variable name spelling

**Invalid Attribute Access:**
```
ContextAccessError: 'invalid_field' not a valid field
```
- Only use fields defined in Pydantic schemas (pos_x, pos_y, etc.)
- Check available fields for the object type

**Access Denied:**
```
ContextAccessError: Double underscore access not allowed
```
- Don't use `__` in variable paths for security
- Use only safe, defined attributes
