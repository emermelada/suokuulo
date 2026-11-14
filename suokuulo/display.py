from typing import Protocol


class Display(Protocol):
    def show_score(self, score: int) -> None: ...  # health 0..100, -1 = none (off season)
    def beep(self) -> None: ...                     # startup beep, the buzzer's only sound
    def uplink(self, health: int, richness: int, activity: int, species_mask: int, detections: int) -> None: ...
                                                    # hourly summary; the MCU encodes and transmits it
    def heartbeat(self) -> None: ...                # every 10 s; the MCU watchdog reports when it stops


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

    def heartbeat(self):
        pass

    def uplink(self, health, richness, activity, species_mask, detections):
        print(f"  [uplink] health {health} richness {richness}% activity {activity}% "
              f"species {species_mask:#06x} detections {detections}")
