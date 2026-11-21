#!/usr/bin/env bash
# One TPCx-AI run of UC3 + UC7 on HDFS + YARN + Spark, with resource monitoring
# and collection of every result into results/raw/<experiment>/<run>/.
#
# Usage: run_one.sh <experiment> <scale-factor> <executor-cores> <streams> <repetition>
# A run that finished before (DONE marker) is skipped, so an interrupted batch can be resumed.
set -uo pipefail

EXP="${1:?experiment}"; SF="${2:?scale factor}"; CORES="${3:?executor cores}"
STREAMS="${4:?throughput streams}"; REP="${5:?repetition}"

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KIT_DIR="${KIT_DIR:-$HOME/spark-kit/tpcx-ai-v2.0.0}"
RUN="sf${SF}_c${CORES}_s${STREAMS}_r${REP}"
OUT="$REPO_DIR/results/raw/$EXP/$RUN"

if [ -f "$OUT/DONE" ]; then echo "[skip] $EXP/$RUN already done"; exit 0; fi
rm -rf "$OUT"; mkdir -p "$OUT/kit_logs" "$OUT/eventlogs"

CFG="$(KIT_DIR="$KIT_DIR" bash "$REPO_DIR/config/tpcx-ai/make_config.sh" "$CORES")" || exit 1
cp "$CFG" "$OUT/config.yaml"

echo "[run] $EXP/$RUN  (SF=$SF, cores=$CORES, streams=$STREAMS, rep=$REP)  $(date '+%F %T')"

# event logs that already exist, so only this run's are collected afterwards
hdfs dfs -ls -C /spark-logs 2>/dev/null | sort > "$OUT/.eventlogs_before"

cd "$KIT_DIR" || exit 1
set +u; source ./setenv.sh; set -u
export TPCxAI_SERVING_THROUGHPUT_STREAMS="$STREAMS"

touch "$OUT/.start"
date +%s > "$OUT/start_epoch"
vmstat -n -t 5 > "$OUT/vmstat.log" &
VMSTAT_PID=$!

./bin/tpcxai.sh -c "$CFG" -uc 3 7 -sf "$SF" 2>&1 | tee "$OUT/console.log"
RC=${PIPESTATUS[0]}

kill "$VMSTAT_PID" 2>/dev/null
date +%s > "$OUT/end_epoch"
echo "$RC" > "$OUT/exit_code"

# kit metric files and logs written during this run
find logs -maxdepth 1 -type f -newer "$OUT/.start" -exec cp {} "$OUT/kit_logs/" \;

# measured input size (training data actually generated for this SF)
wc -l output/raw_data/training/*.csv > "$OUT/rowcounts.txt" 2>/dev/null
hdfs dfs -du -s output/data/training > "$OUT/hdfs_du.txt" 2>/dev/null

# this run's Spark event logs
hdfs dfs -ls -C /spark-logs 2>/dev/null | sort > "$OUT/.eventlogs_after"
comm -13 "$OUT/.eventlogs_before" "$OUT/.eventlogs_after" | while read -r f; do
  hdfs dfs -get "$f" "$OUT/eventlogs/" 2>/dev/null
done

touch "$OUT/DONE"
echo "[done] $EXP/$RUN exit=$RC  $(date '+%F %T')"
