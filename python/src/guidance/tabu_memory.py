class TabuMemory:
    def __init__(self, tenure: int = 20):
        self.tenure = max(1, tenure)
        self.iteration = 0
        self._tabu_until: dict[tuple[int, int, int], int] = {}

    def next_iteration(self):
        self.iteration += 1

    def forbid_reverse_move(self, customer: int, from_vehicle: int, to_vehicle: int):
        reverse = (customer, to_vehicle, from_vehicle)
        self._tabu_until[reverse] = self.iteration + self.tenure

    def is_tabu(
        self,
        customer: int,
        from_vehicle: int,
        to_vehicle: int,
        aspiration: bool = False,
    ) -> bool:
        if aspiration:
            return False

        expires = self._tabu_until.get((customer, from_vehicle, to_vehicle), -1)
        return expires > self.iteration

    def prune(self):
        expired = [
            key
            for key, expires in self._tabu_until.items()
            if expires <= self.iteration
        ]
        for key in expired:
            del self._tabu_until[key]
