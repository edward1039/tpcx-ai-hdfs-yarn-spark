#!/usr/bin/env bash
# Derive a TPCx-AI driver configuration for this host from the kit's own
# driver/config/default-spark.yaml. The kit is not redistributed here (TPC EULA),
# so the configuration is produced by editing the user's local copy.
#
# Usage: make_config.sh <executor-cores>
# Prints the path of the generated file.
set -euo pipefail

CORES="${1:?usage: make_config.sh <executor-cores>}"
KIT_DIR="${KIT_DIR:-$HOME/spark-kit/tpcx-ai-v2.0.0}"
SRC="$KIT_DIR/driver/config/default-spark.yaml"
DST="$KIT_DIR/driver/config/scal-c${CORES}.yaml"

[ -f "$SRC" ] || { echo "kit config not found: $SRC (set KIT_DIR)" >&2; exit 1; }

sed \
  -e 's/--driver-memory 10g/--driver-memory 2g/' \
  -e "s/--executor-cores 5/--executor-cores ${CORES}/" \
  -e 's/--executor-memory 40g/--executor-memory 3g/g' \
  -e 's/memoryOverhead=4g/memoryOverhead=512m/g' \
  -e 's/scala_2\.11/scala_2.12/g' \
  -e 's/workload-assembly_2\.11-0\.1\.jar/workload-assembly_2.12-0.1.jar/g' \
  -e 's/pdgf_node_parallel: True/pdgf_node_parallel: False/' \
  -e 's/: \*HDFS /: *HDFS_LOCAL /g' \
  -e 's|scoring_data_url: &SCORING_DATA_URL "output/raw_data/scoring"|scoring_data_url: \&SCORING_DATA_URL "output/data/scoring"|' \
  "$SRC" > "$DST"

# sanity checks: every edit must have applied
grep -q -- "--master yarn" "$DST"
grep -q -- "--executor-cores ${CORES}" "$DST"
grep -q -- "--executor-memory 3g" "$DST"
grep -q "workload-assembly_2.12" "$DST"
grep -q "\*HDFS_LOCAL" "$DST"

echo "$DST"
