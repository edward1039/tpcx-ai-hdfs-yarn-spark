"""Summarize Spark event logs collected by experiments/run_one.sh.

For every application (one per use case and benchmark phase) it reports duration,
task time, GC time, shuffle read/write and memory/disk spill, plus its slowest stages.

Outputs:
  results/spark_apps.csv         one row per Spark application
  results/spark_top_stages.csv   the 3 longest stages of each application

Usage: python analysis/spark_stages.py [results_dir]
Compatible with Python 3.7.
"""
import csv
import glob
import json
import os
import re
import sys

RUN_RE = re.compile(r"sf(\d+)_c(\d+)_s(\d+)_r(\d+)$")
PHASES = ["training UC3", "training UC7", "serving UC3", "serving UC7", "scoring UC3", "scoring UC7"]


def summarize_log(path):
    app = {"app_name": "", "app_id": "", "start_ms": None, "end_ms": None,
           "tasks": 0, "executor_run_ms": 0, "executor_cpu_ns": 0, "gc_ms": 0,
           "shuffle_read_bytes": 0, "shuffle_write_bytes": 0,
           "spill_memory_bytes": 0, "spill_disk_bytes": 0, "input_bytes": 0}
    stages = []
    with open(path, errors="replace") as f:
        for line in f:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            kind = ev.get("Event")
            if kind == "SparkListenerApplicationStart":
                app["app_name"] = ev.get("App Name", "")
                app["app_id"] = ev.get("App ID", "")
                app["start_ms"] = ev.get("Timestamp")
            elif kind == "SparkListenerApplicationEnd":
                app["end_ms"] = ev.get("Timestamp")
            elif kind == "SparkListenerTaskEnd":
                m = ev.get("Task Metrics") or {}
                app["tasks"] += 1
                app["executor_run_ms"] += m.get("Executor Run Time", 0)
                app["executor_cpu_ns"] += m.get("Executor CPU Time", 0)
                app["gc_ms"] += m.get("JVM GC Time", 0)
                app["spill_memory_bytes"] += m.get("Memory Bytes Spilled", 0)
                app["spill_disk_bytes"] += m.get("Disk Bytes Spilled", 0)
                sr = m.get("Shuffle Read Metrics") or {}
                app["shuffle_read_bytes"] += sr.get("Remote Bytes Read", 0) + sr.get("Local Bytes Read", 0)
                sw = m.get("Shuffle Write Metrics") or {}
                app["shuffle_write_bytes"] += sw.get("Shuffle Bytes Written", 0)
                im = m.get("Input Metrics") or {}
                app["input_bytes"] += im.get("Bytes Read", 0)
            elif kind == "SparkListenerStageCompleted":
                s = ev.get("Stage Info") or {}
                if s.get("Submission Time") and s.get("Completion Time"):
                    stages.append({"stage_id": s.get("Stage ID"),
                                   "stage_name": (s.get("Stage Name") or "")[:80],
                                   "tasks": s.get("Number of Tasks"),
                                   "duration_s": (s["Completion Time"] - s["Submission Time"]) / 1000.0})
    if app["start_ms"] and app["end_ms"]:
        app["duration_s"] = (app["end_ms"] - app["start_ms"]) / 1000.0
    app["stages"] = len(stages)
    return app, stages


def main():
    results = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "results")
    app_rows, stage_rows = [], []
    for run_dir in sorted(glob.glob(os.path.join(results, "raw", "*", "*"))):
        m = RUN_RE.search(run_dir)
        if not m:
            continue
        exp = os.path.basename(os.path.dirname(run_dir))
        base = {"experiment": exp, "run": os.path.basename(run_dir), "sf": int(m.group(1)),
                "cores": int(m.group(2)), "streams": int(m.group(3)), "rep": int(m.group(4))}
        apps = []
        for path in glob.glob(os.path.join(run_dir, "eventlogs", "*")):
            app, stages = summarize_log(path)
            if app["start_ms"] is not None:
                apps.append((app, stages))
        apps.sort(key=lambda a: a[0]["start_ms"])
        for i, (app, stages) in enumerate(apps):
            row = dict(base)
            row["app_seq"] = i + 1
            row["phase_guess"] = PHASES[i] if i < len(PHASES) else "throughput"
            row.update({k: v for k, v in app.items() if k not in ("start_ms", "end_ms")})
            app_rows.append(row)
            for s in sorted(stages, key=lambda s: -s["duration_s"])[:3]:
                srow = {k: row[k] for k in ("experiment", "run", "sf", "cores", "streams", "rep", "app_seq", "phase_guess", "app_name")}
                srow.update(s)
                stage_rows.append(srow)
    if not app_rows:
        print("no event logs found under", os.path.join(results, "raw"))
        return
    for name, rows in (("spark_apps.csv", app_rows), ("spark_top_stages.csv", stage_rows)):
        keys = []
        for r in rows:
            for k in r:
                if k not in keys:
                    keys.append(k)
        out = os.path.join(results, name)
        with open(out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
        print("wrote %s (%d rows)" % (out, len(rows)))


if __name__ == "__main__":
    main()
