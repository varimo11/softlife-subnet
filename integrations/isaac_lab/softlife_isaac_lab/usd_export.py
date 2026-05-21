from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from integrations.isaac_lab.softlife_isaac_lab.scene_spec import (
    CAMERA_NAMES,
    asset_hint_for_kind,
    pose_for_zone,
    size_for_object_kind,
    size_for_zone,
)


def render_usda_scene(bundle_payload: Mapping[str, Any]) -> str:
    """Render a lightweight USD ASCII scene from a validator replay bundle."""

    _require_schema(bundle_payload)
    room_id = _usd_name(str(bundle_payload["challenge_id"]))
    private_state = _mapping(bundle_payload["validator_private_state"])
    scene_manifest = _mapping(bundle_payload["scene_manifest"])
    zones = tuple(str(zone) for zone in private_state.get("zones", ()))
    if not zones:
        public_state = _mapping(bundle_payload["public_state"])
        zones = tuple(str(zone) for zone in public_state.get("zones", ()))

    objects = tuple(_mapping(item) for item in private_state.get("objects", ()))
    surfaces = tuple(_mapping(item) for item in private_state.get("surfaces", ()))

    lines = [
        "#usda 1.0",
        "(",
        '    defaultPrim = "World"',
        "    metersPerUnit = 1",
        '    upAxis = "Z"',
        ")",
        "",
        'def Xform "World"',
        "{",
        '    def Xform "SoftLifeRooms"',
        "    {",
        f'        def Xform "{room_id}"',
        "        {",
        _custom_string("softlife:bundle_schema", str(bundle_payload["bundle_schema"]), 12),
        _custom_string("softlife:scene_root", str(scene_manifest["root_prim"]), 12),
        _render_zone_prims(zones, indent=12),
        _render_surface_prims(surfaces, indent=12),
        _render_object_prims(objects, indent=12),
        _render_camera_prims(indent=12),
        "        }",
        "    }",
        "}",
        "",
    ]
    return "\n".join(line for line in lines if line is not None)


def write_usda_scene(bundle_payload: Mapping[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_usda_scene(bundle_payload), encoding="utf-8")
    return path


def load_bundle_payload(path: str | Path) -> Mapping[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise TypeError("bundle payload must be a JSON object")
    _require_schema(payload)
    return payload


def _render_zone_prims(zones: tuple[str, ...], indent: int) -> str:
    pad = " " * indent
    lines = [f'{pad}def Xform "Zones"', f"{pad}{{"]
    for zone in zones:
        name = _usd_name(zone)
        x, y, z = pose_for_zone(zone)
        sx, sy, sz = size_for_zone(zone)
        lines.extend(
            [
                f'{pad}    def Xform "{name}"',
                f"{pad}    {{",
                _translate_attr(x, y, z, indent + 8),
                _xform_order(("translate",), indent + 8),
                _custom_string("softlife:zone", zone, indent + 8),
                f'{pad}        def Cube "bounds"',
                f"{pad}        {{",
                f"{pad}            double3 xformOp:scale = ({sx:.4f}, {sy:.4f}, {sz:.4f})",
                f'{pad}            uniform token[] xformOpOrder = ["xformOp:scale"]',
                f"{pad}            color3f[] primvars:displayColor = [(0.22, 0.22, 0.24)]",
                f"{pad}        }}",
                f'{pad}        def Xform "target_frame"',
                f"{pad}        {{",
                _custom_string("softlife:target_frame_for", zone, indent + 12),
                f"{pad}        }}",
                f"{pad}    }}",
            ]
        )
    lines.append(f"{pad}}}")
    return "\n".join(lines)


def _render_surface_prims(surfaces: tuple[Mapping[str, Any], ...], indent: int) -> str:
    pad = " " * indent
    lines = [f'{pad}def Xform "Surfaces"', f"{pad}{{"]
    for surface in surfaces:
        zone = str(surface["zone"])
        dirt = float(surface.get("dirt", 0.0))
        x, y, z = pose_for_zone(zone)
        sx, sy, _ = size_for_zone(zone)
        lines.extend(
            [
                f'{pad}    def Cube "{_usd_name(zone)}"',
                f"{pad}    {{",
                _translate_attr(x, y, z + 0.04, indent + 8),
                f"{pad}        double3 xformOp:scale = ({sx:.4f}, {sy:.4f}, 0.0150)",
                _xform_order(("translate", "scale"), indent + 8),
                f"{pad}        color3f[] primvars:displayColor = [({_surface_color(dirt)})]",
                f"{pad}        double softlife:dirt = {dirt:.6f}",
                f"{pad}    }}",
            ]
        )
    lines.append(f"{pad}}}")
    return "\n".join(lines)


def _render_object_prims(objects: tuple[Mapping[str, Any], ...], indent: int) -> str:
    pad = " " * indent
    zone_counts: dict[str, int] = {}
    lines = [f'{pad}def Xform "Objects"', f"{pad}{{"]
    for obj in objects:
        object_id = str(obj["object_id"])
        kind = str(obj["kind"])
        zone = str(obj["location"])
        zone_counts[zone] = zone_counts.get(zone, 0) + 1
        x, y, z = _object_pose(zone, zone_counts[zone], kind)
        sx, sy, sz = size_for_object_kind(kind)
        lines.extend(
            [
                f'{pad}    def Cube "{_usd_name(object_id)}"',
                f"{pad}    {{",
                _translate_attr(x, y, z, indent + 8),
                f"{pad}        double3 xformOp:scale = ({sx:.4f}, {sy:.4f}, {sz:.4f})",
                _xform_order(("translate", "scale"), indent + 8),
                f"{pad}        color3f[] primvars:displayColor = [({_object_color(kind)})]",
                _custom_string("softlife:object_id", object_id, indent + 8),
                _custom_string("softlife:kind", kind, indent + 8),
                _custom_string("softlife:target_zone", str(obj["target_zone"]), indent + 8),
                _custom_string("softlife:asset_hint", asset_hint_for_kind(kind), indent + 8),
                f"{pad}    }}",
            ]
        )
    lines.append(f"{pad}}}")
    return "\n".join(lines)


def _render_camera_prims(indent: int) -> str:
    pad = " " * indent
    poses = {
        "wide_validator_camera": (0.0, -5.6, 4.2),
        "robot_follow_camera": (-2.8, -2.8, 1.6),
        "overhead_audit_camera": (0.0, 0.0, 6.4),
    }
    lines = [f'{pad}def Xform "Cameras"', f"{pad}{{"]
    for camera_name in CAMERA_NAMES:
        x, y, z = poses[camera_name]
        lines.extend(
            [
                f'{pad}    def Camera "{camera_name}"',
                f"{pad}    {{",
                _translate_attr(x, y, z, indent + 8),
                _xform_order(("translate",), indent + 8),
                f"{pad}        float focalLength = 24",
                f"{pad}        float horizontalAperture = 20.955",
                f"{pad}    }}",
            ]
        )
    lines.append(f"{pad}}}")
    return "\n".join(lines)


def _object_pose(zone: str, index_in_zone: int, kind: str) -> tuple[float, float, float]:
    x, y, z = pose_for_zone(zone)
    _, _, sz = size_for_object_kind(kind)
    offset = (index_in_zone - 1) * 0.18
    return (x + offset, y - offset * 0.35, z + sz + 0.08)


def _translate_attr(x: float, y: float, z: float, indent: int) -> str:
    pad = " " * indent
    return f"{pad}double3 xformOp:translate = ({x:.4f}, {y:.4f}, {z:.4f})"


def _xform_order(ops: tuple[str, ...], indent: int) -> str:
    quoted_ops = ", ".join(f'"xformOp:{op}"' for op in ops)
    return f'{" " * indent}uniform token[] xformOpOrder = [{quoted_ops}]'


def _custom_string(name: str, value: str, indent: int) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'{" " * indent}string {name} = "{escaped}"'


def _surface_color(dirt: float) -> str:
    dirt = max(0.0, min(1.0, dirt))
    clean = 1.0 - dirt
    return f"{0.18 + dirt * 0.35:.3f}, {0.20 + clean * 0.18:.3f}, {0.22 + clean * 0.16:.3f}"


def _object_color(kind: str) -> str:
    colors = {
        "towel": "0.92, 0.78, 0.46",
        "pillow": "0.82, 0.80, 0.74",
        "mug": "0.62, 0.68, 0.72",
        "remote": "0.08, 0.09, 0.10",
        "shoes": "0.22, 0.18, 0.14",
        "trash": "0.72, 0.56, 0.20",
        "toiletry": "0.52, 0.64, 0.70",
    }
    return colors.get(kind, "0.65, 0.62, 0.56")


def _usd_name(value: str) -> str:
    return "".join(char if char.isalnum() or char == "_" else "_" for char in value)


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"expected mapping, got {type(value).__name__}")
    return value


def _require_schema(payload: Mapping[str, Any]) -> None:
    if payload.get("bundle_schema") != "softlife.isaac_replay_bundle.v1":
        raise ValueError("expected softlife.isaac_replay_bundle.v1 payload")
