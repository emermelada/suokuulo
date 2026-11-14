#!/bin/bash
# Copy applab/ to the UNO Q (symlinks become real files), then check every file
# arrived intact: a weak hotspot once left sketch.ino and sketch.yaml as 0-byte
# files. Exits non-zero if any file differs.
# Usage: ./deploy.sh [--restart]   (--restart: stop and start the app over ssh)
set -euo pipefail
cd "$(dirname "$0")"
BOARD=${BOARD:-arduino@10.145.234.61}
APP=ArduinoApps/suokuulo
# Never ship laptop caches or a laptop events.csv over the board's log.
EXCLUDE=(--exclude=buzzer_test --exclude=__pycache__ --exclude=events.csv)

tar -chf - -C applab "${EXCLUDE[@]}" . | ssh "$BOARD" "mkdir -p ~/$APP && tar -xf - -C ~/$APP"

# sha256 of every file we ship, checked on the board (prints only mismatches).
sums=$(cd applab && find -L . \( -path ./buzzer_test -o -name __pycache__ -o -name events.csv \) -prune \
       -o -type f -print0 | sort -z | xargs -0 sha256sum)
if ! echo "$sums" | ssh "$BOARD" "cd ~/$APP && sha256sum --check --quiet --strict -"; then
    echo "DEPLOY FAILED: files above differ on the board. Run ./deploy.sh again." >&2
    exit 1
fi
echo "Deployed $(git describe --always --dirty) to $BOARD:~/$APP, $(echo "$sums" | wc -l) files verified"

if [[ "${1:-}" == "--restart" ]]; then
    ssh "$BOARD" "arduino-app-cli app stop user:suokuulo || true; arduino-app-cli app start user:suokuulo"
fi
