from dataclasses import dataclass


@dataclass(frozen=True)
class SolverConfig:
    constructor: str = "farthest_nearest"
    improver: str = "none"
    granular: bool = False
    tabu: bool = False
    time_limit: float = 0.0
    seed: int = 0
    neighbor_count: int = 20
    tabu_tenure: int = 25
    destroy_fraction: float = 0.15
    max_ejection_depth: int = 2

    @property
    def mode_name(self) -> str:
        parts = [self.constructor]
        if self.improver != "none":
            parts.append(self.improver)
        if self.granular:
            parts.append("granular")
        if self.tabu:
            parts.append("tabu")
        return "+".join(parts)
