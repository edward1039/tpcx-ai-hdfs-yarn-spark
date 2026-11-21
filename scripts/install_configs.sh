#!/usr/bin/env bash
# Install this repository's Hadoop and Spark configuration on the host.
# Safe to re-run. Requires HADOOP_HOME and SPARK_HOME.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${HADOOP_HOME:?set HADOOP_HOME}"
: "${SPARK_HOME:?set SPARK_HOME}"
HCONF="$HADOOP_HOME/etc/hadoop"

for f in core-site.xml hdfs-site.xml yarn-site.xml; do
  sed "s|__HOME__|$HOME|g" "$REPO_DIR/config/hadoop/$f" > "$HCONF/$f"
  echo "installed $HCONF/$f"
done

JAVA8=/usr/lib/jvm/java-8-openjdk-amd64
if ! grep -q "^export JAVA_HOME=$JAVA8" "$HCONF/hadoop-env.sh"; then
  echo "export JAVA_HOME=$JAVA8" >> "$HCONF/hadoop-env.sh"
  echo "set JAVA_HOME in hadoop-env.sh"
fi

SDEF="$SPARK_HOME/conf/spark-defaults.conf"
touch "$SDEF"
if ! grep -q "^spark.eventLog.enabled" "$SDEF"; then
  cat "$REPO_DIR/config/spark/spark-defaults.conf" >> "$SDEF"
  echo "enabled Spark event logs in $SDEF"
else
  echo "Spark event logs already configured in $SDEF"
fi

mkdir -p "$HOME/hadoop-data"
echo "done. If this is a new install, run: hdfs namenode -format   (only once)"
