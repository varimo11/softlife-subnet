from __future__ import annotations

from typing import Protocol

from softlife_subnet.actions import Trajectory
from softlife_subnet.state import PublicRoomState


class Miner(Protocol):
    miner_id: str

    def solve(self, public_state: PublicRoomState) -> Trajectory:
        """Return a trajectory from public state only."""
