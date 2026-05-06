from improvers.adaptive_destroy_repair import improve as destroy_repair
from improvers.border_reassignment import improve as border_reassignment
from improvers.ejection_chains import improve as ejection_chains
from improvers.ip_subproblem import improve as ip_subproblem
from improvers.memory_destroy_repair import improve as memory_destroy_repair
from improvers.relocate_swap import improve as relocate_swap


IMPROVERS = {
    "none": None,
    "border_reassignment": border_reassignment,
    "relocate_swap": relocate_swap,
    "destroy_repair": destroy_repair,
    "ip_subproblem": ip_subproblem,
    "memory_destroy_repair": memory_destroy_repair,
    "ejection_chains": ejection_chains,
}
