from __future__ import annotations

from dataclasses import dataclass

from softlife_subnet.validators.validator import EvaluationResult


@dataclass(frozen=True)
class LeaderboardEntry:
    miner_id: str
    latest_score: float
    best_score: float
    evaluations: int

    def to_wire(self) -> dict[str, str | float | int]:
        return {
            "miner_id": self.miner_id,
            "latest_score": self.latest_score,
            "best_score": self.best_score,
            "evaluations": self.evaluations,
        }


class Leaderboard:
    def __init__(self) -> None:
        self._entries: dict[str, LeaderboardEntry] = {}

    def update(self, result: EvaluationResult) -> LeaderboardEntry:
        previous = self._entries.get(result.miner_id)
        readiness = result.score.readiness
        entry = LeaderboardEntry(
            miner_id=result.miner_id,
            latest_score=readiness,
            best_score=max(readiness, previous.best_score if previous else readiness),
            evaluations=(previous.evaluations + 1) if previous else 1,
        )
        self._entries[result.miner_id] = entry
        return entry

    def ranking(self) -> tuple[LeaderboardEntry, ...]:
        return tuple(
            sorted(
                self._entries.values(),
                key=lambda entry: (-entry.best_score, entry.miner_id),
            )
        )

    def normalized_weights(self) -> dict[str, float]:
        entries = self.ranking()
        if not entries:
            return {}

        positive_scores = {
            entry.miner_id: max(0.0, entry.best_score)
            for entry in entries
        }
        total = sum(positive_scores.values())
        if total <= 0.0:
            equal_weight = 1.0 / len(entries)
            return {entry.miner_id: equal_weight for entry in entries}

        return {
            miner_id: score / total
            for miner_id, score in positive_scores.items()
        }

    def ranking_with_weights(self) -> tuple[dict[str, str | float | int], ...]:
        weights = self.normalized_weights()
        return tuple(
            {
                **entry.to_wire(),
                "normalized_weight": round(weights.get(entry.miner_id, 0.0), 6),
            }
            for entry in self.ranking()
        )
