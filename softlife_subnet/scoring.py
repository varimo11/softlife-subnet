from __future__ import annotations

from dataclasses import dataclass

from softlife_subnet.simulation import ReplayResult
from softlife_subnet.state import HELD_LOCATION, clamp01


@dataclass(frozen=True)
class EvaluationScore:
    readiness: float
    object_score: float
    cleanliness_score: float
    efficiency_score: float
    invalid_penalty: float

    def to_wire(self) -> dict[str, float]:
        return {
            "readiness": self.readiness,
            "object_score": self.object_score,
            "cleanliness_score": self.cleanliness_score,
            "efficiency_score": self.efficiency_score,
            "invalid_penalty": self.invalid_penalty,
        }


@dataclass(frozen=True)
class RoomReadinessScorer:
    object_weight: float = 55.0
    cleanliness_weight: float = 35.0
    efficiency_weight: float = 10.0
    invalid_action_penalty: float = 4.0

    def score(self, result: ReplayResult) -> EvaluationScore:
        final_state = result.final_state

        placed_objects = sum(
            1
            for obj in final_state.objects
            if obj.location == obj.target_zone and obj.location != HELD_LOCATION
        )
        object_ratio = placed_objects / max(1, len(final_state.objects))
        object_score = self.object_weight * object_ratio

        clean_ratio = sum(1.0 - clamp01(surface.dirt) for surface in final_state.surfaces)
        clean_ratio /= max(1, len(final_state.surfaces))
        cleanliness_score = self.cleanliness_weight * clean_ratio

        ideal_actions = max(1, len(final_state.objects) * 4 + len(final_state.surfaces) * 2)
        overage = max(0, result.action_count - ideal_actions)
        efficiency_score = self.efficiency_weight * max(0.0, 1.0 - overage / ideal_actions)

        invalid_penalty = self.invalid_action_penalty * result.invalid_actions
        readiness = clamp_score(
            object_score + cleanliness_score + efficiency_score - invalid_penalty
        )

        return EvaluationScore(
            readiness=round(readiness, 3),
            object_score=round(object_score, 3),
            cleanliness_score=round(cleanliness_score, 3),
            efficiency_score=round(efficiency_score, 3),
            invalid_penalty=round(invalid_penalty, 3),
        )


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, value))
