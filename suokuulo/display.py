from typing import Protocol


class Display(Protocol):
    def show_score(self, score: int) -> None: ...  # health 0..100, -1 = none (off season)
    def alarm(self, on: bool) -> None: ...          # machinery/gunshot alert: matrix corner + siren
    def chirp(self, kind: int) -> None: ...         # 0 bird, 1 headline species, 2 startup beep
    def mute(self, on: bool) -> None: ...           # chirps and siren off (startup beep still plays)


class ConsoleDisplay:
    """Prints what the MCU would show and play."""

    def __init__(self, species):
        self.species, self.muted = species, False

    def show_score(self, score):
        if score < 0:
            print("  [display] health --")
        else:
            print(f"  [display] health {score:3d} |{'#' * round(score * 11 / 100):<11}|")

    def alarm(self, on):
        siren = "" if self.muted else f" [SIREN {'ON' if on else 'OFF'}]"
        print(f"  [display] machinery alert {'ON' if on else 'off'}{siren}")

    def chirp(self, kind):
        if kind == 2:
            print("  [display] [BEEP]")
        elif not self.muted:
            print(f"  [display] [CHIRP{' x2' if kind else ''}]")

    def mute(self, on):
        self.muted = on
        print(f"  [display] buzzer alerts {'off' if on else 'on'}")
