#!/usr/bin/env bash
# The TPCx-AI v2.0.0 Spark kit's bin/tpcxai.sh builds the driver command without --streams,
# so the serving-throughput test always runs the driver default of 2 streams.
# This appends --streams ${TPCXAI_STREAMS:-2} to that command (backup: bin/tpcxai.sh.orig).
set -euo pipefail
KIT_DIR="${KIT_DIR:-$HOME/spark-kit/tpcx-ai-v2.0.0}"
F="$KIT_DIR/bin/tpcxai.sh"
grep -q 'TPCXAI_STREAMS' "$F" && { echo "already patched"; exit 0; }
cp "$F" "$F.orig"
sed -i 's|^CMD="\$PYTHON -u -m tpcxai-driver \$ARGS"$|CMD="$PYTHON -u -m tpcxai-driver $ARGS --streams ${TPCXAI_STREAMS:-2}"|' "$F"
grep -n '^CMD=' "$F"
grep -q 'TPCXAI_STREAMS' "$F" || { echo "patch failed" >&2; exit 1; }
