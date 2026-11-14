from typing import Protocol


class Display(Protocol):
    def show_score(self, score: int) -> None: ...        # 0..100
    def show_bird(self, species_index: int) -> None: ... # index into species.yaml
    def alarm(self, on: bool) -> None: ...                # matrix blink + siren
    def chirp(self, kind: int) -> None: ...               # 0 = indicator, 1 = headline species
    def mute(self, on: bool) -> None: ...                 # silence the buzzer only


class ConsoleDisplay:
    """Prints what the MCU would show and play."""

    def __init__(self, species):
        self.species, self.muted = species, False
        print("  [display] [BEEP] (MCU plays this once the Bridge is up)")

    def show_score(self, score):
        bar = "#" * round(score * 13 / 100)
        print(f"  [display] score {score:3d} |{bar:<13}|")

    def show_bird(self, species_index):
        print(f"  [display] bird  {self.species[species_index].id}")

    def alarm(self, on):
        print(f"  [display] ALARM {'ON' if on else 'off'}" + ("" if self.muted else f" [SIREN {'ON' if on else 'OFF'}]"))

    def chirp(self, kind):
        if not self.muted:
            print(f"  [display] [CHIRP{' x2' if kind else ''}]")

    def mute(self, on):
        self.muted = on
        print(f"  [display] buzzer {'muted' if on else 'unmuted'}")
