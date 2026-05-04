from improvers.adaptive_destroy_repair import improve as destroy_repair
from improvers.ejection_chains import improve as ejection_chains
from improvers.memory_destroy_repair import improve as memory_destroy_repair
from improvers.relocate_swap import improve as relocate_swap


IMPROVERS = {
    "none": None,
    "relocate_swap": relocate_swap,
    "destroy_repair": destroy_repair,
    "memory_destroy_repair": memory_destroy_repair,
    "ejection_chains": ejection_chains,
}
