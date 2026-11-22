#!/usr/bin/env bash
# Start HDFS, YARN and the Spark History Server (if not already running) and check them.
set -uo pipefail

running() { jps | awk '{print $2}' | grep -qx "$1"; }

running NameNode        || setsid hdfs --daemon start namenode
running DataNode        || setsid hdfs --daemon start datanode
running ResourceManager || setsid yarn --daemon start resourcemanager
running NodeManager     || setsid yarn --daemon start nodemanager
sleep 5

# HDFS home directory for the kit's relative paths, and the Spark event-log directory
timeout 120 hdfs dfsadmin -safemode wait >/dev/null \
  || echo "WARNING: NameNode still in safe mode (see README Troubleshooting)"
hdfs dfs -mkdir -p "/user/$USER" /spark-logs

running HistoryServer || setsid "$SPARK_HOME/sbin/start-history-server.sh" >/dev/null

echo "== daemons =="
jps | grep -E "NameNode|DataNode|ResourceManager|NodeManager|HistoryServer" | sort -k2
echo "== HDFS =="
hdfs dfsadmin -report 2>/dev/null | grep -E "Live datanodes|DFS Remaining:" | head -2
echo "== YARN =="
yarn node -list 2>/dev/null | tail -n +2
echo
echo "Web UIs: HDFS http://localhost:9870  YARN http://localhost:8088  Spark history http://localhost:18080"
