from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class RobotCommandType(str, Enum):
    """Adapter-internal primitive commands.

    These are intentionally close to robot task primitives rather than UI or
    scoring concepts. Isaac Lab, ROS2, or DDS adapters can lower them into
    concrete controller actions.
    """

    NAVIGATE_TO_FRAME = "navigate_to_frame"
    APPROACH_OBJECT = "approach_object"
    GRASP_OBJECT = "grasp_object"
    RELEASE_OBJECT = "release_object"
    WIPE_SURFACE = "wipe_surface"
    DROP_IN_RECEPTACLE = "drop_in_receptacle"
    HOLD_POSITION = "hold_position"


@dataclass(frozen=True)
class CompiledRobotCommand:
    """Robot-oriented command compiled from a symbolic Soft Life action."""

    command_type: RobotCommandType
    action_index: int
    source_action_type: str
    target_frame: str | None = None
    object_id: str | None = None
    zone: str | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def to_wire(self) -> dict[str, object]:
        return {
            "command_type": self.command_type.value,
            "action_index": self.action_index,
            "source_action_type": self.source_action_type,
            "target_frame": self.target_frame,
            "object_id": self.object_id,
            "zone": self.zone,
            "parameters": dict(self.parameters),
        }
