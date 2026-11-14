#!/bin/bash
BOARD=arduino@10.145.234.61
tar -chf - -C applab --exclude=buzzer_test . | ssh $BOARD 'mkdir -p ~/ArduinoApps/suokuulo && tar -xf - -C ~/ArduinoApps/suokuulo'
echo "Deployed $(git rev-parse --short HEAD) to board"