from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SoftLifeIsaacRunConfig:
    task_name: str = "SoftLife-HotelRoom-Restore-v0"
    robot_name: str = "unitree_g1"
    headless: bool = True
    physics_dt: float = 1.0 / 60.0
    render_dt: float = 1.0 / 30.0
    max_steps: int = 2400
    record_video: bool = False
    output_dir: str = "outputs/softlife_isaac"
