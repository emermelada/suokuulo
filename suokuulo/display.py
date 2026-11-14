from typing import Protocol


class Display(Protocol):
    def show_score(self, score: int) -> None: ...        # 0..100
    def show_bird(self, species_index: int) -> None: ... # index into species.yaml
    def alarm(self, on: bool) -> None: ...


class ConsoleDisplay:
    def __init__(self, species):
        self.species = species

    def show_score(self, score):
        bar = "#" * round(score * 13 / 100)
        print(f"  [display] score {score:3d} |{bar:<13}|")

    def show_bird(self, species_index):
        print(f"  [display] bird  {self.species[species_index].id}")

    def alarm(self, on):
        print(f"  [display] ALARM {'ON' if on else 'off'}")
