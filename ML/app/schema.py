from dataclasses import dataclass, asdict
from typing import Any

@dataclass
class LogEvent:
    timestamp: str
    service: str
    level: str
    message: str
    status_code: int | None = None
    latency_ms: float | None = None

@dataclass
class Window:
    window_id: str
    scenario_truth: str
    events: list[LogEvent]
    health: dict[str, float]
    resources: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_id": self.window_id,
            "scenario_truth": self.scenario_truth,
            "events": [asdict(e) for e in self.events],
            "health": self.health,
            "resources": self.resources,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Window":
        return cls(
            window_id=raw["window_id"],
            scenario_truth=raw.get("scenario_truth", "unknown"),
            events=[LogEvent(**e) for e in raw["events"]],
            health=raw["health"], resources=raw["resources"],
        )
