import os
import random
from time import perf_counter

from constructors import CONSTRUCTORS
from constructors.farthest_nearest import construct as fallback_construct
from guidance import GranularNeighborhood, TabuMemory
from improvers import IMPROVERS
from route_utils import (
    format_solution,
    objective,
    normalize_routes,
    two_opt_routes,
    validate_routes,
)
from solver_config import SolverConfig


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def config_from_env() -> SolverConfig:
    return SolverConfig(
        constructor=os.environ.get("VRP_CONSTRUCTOR", "farthest_nearest"),
        improver=os.environ.get("VRP_IMPROVER", "none"),
        granular=env_bool("VRP_GRANULAR"),
        tabu=env_bool("VRP_TABU"),
        time_limit=float(os.environ.get("VRP_TIME_LIMIT", "0")),
        seed=int(os.environ.get("VRP_SEED", "0")),
        neighbor_count=int(os.environ.get("VRP_NEIGHBOR_COUNT", "20")),
        tabu_tenure=int(os.environ.get("VRP_TABU_TENURE", "25")),
    )


def solve_instance(instance, config: SolverConfig | None = None):
    config = config or config_from_env()
    rng = random.Random(config.seed)
    deadline = perf_counter() + config.time_limit if config.time_limit > 0 else None
    constructor = CONSTRUCTORS.get(config.constructor)
    if constructor is None:
        raise ValueError(f"Unknown constructor: {config.constructor}")

    routes = constructor(instance, rng)
    routes = normalize_routes(routes, instance.numVehicles)
    if validate_routes(instance, routes):
        routes = fallback_construct(instance, rng)

    improver = IMPROVERS.get(config.improver)
    if improver is None and config.improver != "none":
        raise ValueError(f"Unknown improver: {config.improver}")

    if improver is not None and deadline is not None and perf_counter() < deadline:
        routes = improver(instance, routes, config, rng, deadline)
        routes = normalize_routes(routes, instance.numVehicles)
        routes = two_opt_routes(instance, routes)

    errors = validate_routes(instance, routes)
    if errors:
        routes = fallback_construct(instance, rng)

    solution = format_solution(routes)
    return solution, objective(instance, routes), routes


def guidance_objects(instance, config: SolverConfig):
    granular = (
        GranularNeighborhood(instance, config.neighbor_count)
        if config.granular
        else None
    )
    tabu = TabuMemory(config.tabu_tenure) if config.tabu else None
    return granular, tabu
