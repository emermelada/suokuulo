from typing import Protocol


class Display(Protocol):
    def show_score(self, score: int) -> None: ...  # health 0..100, -1 = none (off season)
    def beep(self) -> None: ...                     # startup beep, the buzzer's only sound


class ConsoleDisplay:
    """Prints what the MCU would show and play."""

    def __init__(self, species):
        self.species = species

    def show_score(self, score):
        if score < 0:
            print("  [display] health --")
        else:
            print(f"  [display] health {score:3d} |{'#' * round(score * 11 / 100):<11}|")

    def beep(self):
        print("  [display] [BEEP]")
