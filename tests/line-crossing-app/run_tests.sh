#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
APP_DIR="$ROOT/apps/line-crossing"
TEST_DIR="$ROOT/tests/line-crossing-app"
WORK="$TEST_DIR/work"
CC=${CC:-cc}
CFLAGS="-Wall -Wextra -Werror -std=c11 -O2 -I$APP_DIR/include -I$APP_DIR/app -I$TEST_DIR"

mkdir -p "$WORK"
make -C "$APP_DIR" clean all
bash "$ROOT/tests/line-crossing/run_tests.sh"
"$CC" $CFLAGS "$TEST_DIR/test_unit.c" \
  "$APP_DIR/app/lc_arena.c" "$APP_DIR/app/lc_json.c" \
  "$APP_DIR/app/lc_stateblob.c" "$APP_DIR/app/lc_bus_config.c" \
  -o "$WORK/test_unit"
"$WORK/test_unit"
bash "$ROOT/tests/line-crossing-enable/run_tests.sh"
echo "RESULT: PASS (current native application and line-crossing core)"
