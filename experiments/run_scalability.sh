#!/usr/bin/env bash
# Scalability experiments for UC3 + UC7.
#   A  data scalability     : SF 1, 3, 5, 10        (8 executor cores, 2 streams)
#   B  resource scalability : executor cores 1, 2, 4, 8 at SF 3   (2 streams)
#   C  concurrency          : serving streams 1, 2, 4 at SF 3     (8 cores)
#
# Usage: run_scalability.sh [A|B|C|all]   (default: all)
# Re-running continues where it stopped; finished runs are skipped.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WHICH="${1:-all}"
REPS="${REPS:-3}"            # repetitions per configuration
REPS_LARGE="${REPS_LARGE:-2}" # repetitions for SF 10

run() { bash "$HERE/run_one.sh" "$@"; }

if [[ "$WHICH" == A || "$WHICH" == all ]]; then
  for SF in 1 3 5 10; do
    n=$REPS; [ "$SF" -ge 10 ] && n=$REPS_LARGE
    for r in $(seq 1 "$n"); do run A "$SF" 8 2 "$r"; done
  done
fi

if [[ "$WHICH" == B || "$WHICH" == all ]]; then
  for C in 1 2 4 8; do
    for r in $(seq 1 "$REPS"); do run B 3 "$C" 2 "$r"; done
  done
fi

if [[ "$WHICH" == C || "$WHICH" == all ]]; then
  for S in 1 2 4; do
    for r in $(seq 1 2); do run C 3 8 "$S" "$r"; done
  done
fi

echo "all requested experiments finished: $(date '+%F %T')"
