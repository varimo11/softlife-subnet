from __future__ import annotations


HOTEL_ROOM_ZONES: tuple[str, ...] = (
    "entry",
    "floor",
    "bed",
    "nightstand",
    "desk",
    "bathroom_counter",
    "hamper",
    "closet",
    "trash_bin",
)


OBJECT_KIND_TO_ASSET_HINT: dict[str, str] = {
    "towel": "soft_props/towel.usd",
    "pillow": "soft_props/pillow.usd",
    "mug": "tableware/mug.usd",
    "remote": "electronics/remote.usd",
    "shoes": "closet/shoes_pair.usd",
    "trash": "trash/wrapper.usd",
    "toiletry": "bathroom/toiletry_bottle.usd",
}


CAMERA_NAMES: tuple[str, ...] = (
    "wide_validator_camera",
    "robot_follow_camera",
    "overhead_audit_camera",
)

ZONE_POSES: dict[str, tuple[float, float, float]] = {
    "entry": (-3.2, -2.4, 0.0),
    "floor": (0.0, -0.4, 0.0),
    "bed": (2.4, 1.6, 0.55),
    "nightstand": (0.8, 1.9, 0.45),
    "desk": (-2.4, 1.4, 0.72),
    "bathroom_counter": (-3.0, -0.4, 0.85),
    "hamper": (2.8, -0.8, 0.15),
    "closet": (1.8, -2.4, 0.0),
    "trash_bin": (3.2, -2.3, 0.1),
}

ZONE_SIZES: dict[str, tuple[float, float, float]] = {
    "entry": (1.3, 1.0, 0.05),
    "floor": (2.4, 2.0, 0.03),
    "bed": (2.2, 1.6, 0.32),
    "nightstand": (0.7, 0.55, 0.45),
    "desk": (1.6, 0.75, 0.72),
    "bathroom_counter": (1.2, 0.6, 0.62),
    "hamper": (0.65, 0.65, 0.5),
    "closet": (1.2, 0.8, 0.05),
    "trash_bin": (0.45, 0.45, 0.55),
}

OBJECT_SIZES: dict[str, tuple[float, float, float]] = {
    "towel": (0.42, 0.28, 0.05),
    "pillow": (0.5, 0.35, 0.14),
    "mug": (0.16, 0.16, 0.2),
    "remote": (0.25, 0.08, 0.04),
    "shoes": (0.42, 0.28, 0.12),
    "trash": (0.16, 0.12, 0.03),
    "toiletry": (0.12, 0.12, 0.32),
}


def asset_hint_for_kind(kind: str) -> str:
    return OBJECT_KIND_TO_ASSET_HINT.get(kind, "props/generic_object.usd")


def pose_for_zone(zone: str) -> tuple[float, float, float]:
    return ZONE_POSES.get(zone, (0.0, 0.0, 0.0))


def size_for_zone(zone: str) -> tuple[float, float, float]:
    return ZONE_SIZES.get(zone, (0.6, 0.6, 0.05))


def size_for_object_kind(kind: str) -> tuple[float, float, float]:
    return OBJECT_SIZES.get(kind, (0.2, 0.2, 0.2))
