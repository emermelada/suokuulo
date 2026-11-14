## Seasonal extension: candidate species

Six candidates for the migration and winter profiles, 5 quality-A Xeno-canto
clips each (`fetch_bird_clips.py --quality-a`), evaluated with the board
settings (`eval/seasonal.md`, `.csv`). Rule fixed before the run: keep a
species if at least 4 of 5 clips confirm and it is not confirmed on other
species' clips.

| species | profile | clips confirmed | confirmed on other clips | decision |
| --- | --- | --- | --- | --- |
| whooper_swan | migration | 4/5 | 0 (highest other window 0.36) | added |
| spotted_redshank | migration | 5/5 | 1, on ruff XC821333, which lists Tringa erythropus as a background species | added |
| taiga_bean_goose | migration | 2/5 | 0 | left out |
| ruff | migration | 0/5 | 0 | left out |
| willow_ptarmigan | winter | 4/5 | 0 (highest other window 0.31) | added |
| black_grouse | winter | 5/5 | 0 | added |

Winter expectations are low on purpose (both grouse together under 3
detection-minutes per hour), so winter health reads "Off season (low bird
activity expected)" and the dashboard leads with disturbance.
