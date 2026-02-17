from __future__ import annotations

"""
ROS2 optional bridge (stub).

Design intent:
- Subscribe via image_transport for compressed streams (recommended in ROS2 docs).
- Convert sensor_msgs/Image to numpy arrays and feed the same downstream pipeline.

The starter repo keeps this optional to avoid forcing ROS2 dependencies into a Cookoff demo.
"""
