#!/usr/bin/env bash
# Stop the Spark History Server, YARN and HDFS. Data in HDFS is kept on disk.
set -uo pipefail
"$SPARK_HOME/sbin/stop-history-server.sh" >/dev/null 2>&1
yarn --daemon stop nodemanager
yarn --daemon stop resourcemanager
hdfs --daemon stop datanode
hdfs --daemon stop namenode
jps
