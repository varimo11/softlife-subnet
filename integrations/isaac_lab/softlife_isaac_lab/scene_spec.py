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


def asset_hint_for_kind(kind: str) -> str:
    return OBJECT_KIND_TO_ASSET_HINT.get(kind, "props/generic_object.usd")
