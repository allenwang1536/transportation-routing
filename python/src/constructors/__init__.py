from constructors.farthest_nearest import construct as farthest_nearest
from constructors.regret_bidding import construct as regret_bidding
from constructors.sweep import construct as sweep


CONSTRUCTORS = {
    "farthest_nearest": farthest_nearest,
    "sweep": sweep,
    "regret_bidding": regret_bidding,
}
