from __future__ import annotations

from dataclasses import dataclass

from softlife_subnet.state import EnvironmentState


VALIDATOR_CAMERA_NAMES: tuple[str, ...] = (
    "wide_validator_camera",
    "robot_follow_camera",
    "overhead_audit_camera",
)


@dataclass(frozen=True)
class HotelRoomSceneManifest:
    """Deterministic symbolic-to-scene mapping for future Isaac Lab adapters."""

    room_id: str
    root_prim: str
    zone_frames: dict[str, str]
    object_prims: dict[str, str]
    surface_prims: dict[str, str]
    camera_prims: dict[str, str]

    @classmethod
    def from_environment(cls, environment_state: EnvironmentState) -> "HotelRoomSceneManifest":
        root = f"/World/SoftLifeRooms/{environment_state.room_id}"
        return cls(
            room_id=environment_state.room_id,
            root_prim=root,
            zone_frames={
                zone: f"{root}/Zones/{_usd_name(zone)}/target_frame"
                for zone in environment_state.zones
            },
            object_prims={
                obj.object_id: f"{root}/Objects/{_usd_name(obj.object_id)}"
                for obj in environment_state.objects
            },
            surface_prims={
                surface.zone: f"{root}/Surfaces/{_usd_name(surface.zone)}"
                for surface in environment_state.surfaces
            },
            camera_prims={
                camera_name: f"{root}/Cameras/{camera_name}"
                for camera_name in VALIDATOR_CAMERA_NAMES
            },
        )

    def zone_frame(self, zone: str | None) -> str | None:
        if zone is None:
            return None
        return self.zone_frames.get(zone)

    def object_prim(self, object_id: str | None) -> str | None:
        if object_id is None:
            return None
        return self.object_prims.get(object_id)

    def surface_prim(self, zone: str | None) -> str | None:
        if zone is None:
            return None
        return self.surface_prims.get(zone)

    def camera_prim(self, camera_name: str | None) -> str | None:
        if camera_name is None:
            return None
        return self.camera_prims.get(camera_name)

    def to_wire(self) -> dict[str, object]:
        return {
            "room_id": self.room_id,
            "root_prim": self.root_prim,
            "zone_frames": dict(self.zone_frames),
            "object_prims": dict(self.object_prims),
            "surface_prims": dict(self.surface_prims),
            "camera_prims": dict(self.camera_prims),
        }


def _usd_name(value: str) -> str:
    return "".join(char if char.isalnum() or char == "_" else "_" for char in value)
