"""Collect every run under results/raw/ into results/summary.csv (one row per run).

Sources per run directory (written by experiments/run_one.sh):
  kit_logs/tpcxai-metrics-*.csv        phase times and quality per use case
  kit_logs/adabench-aiucpm-metrics-*   DATAGEN, TLOAD, TTT
  console.log                          per-stream serving-throughput times
  rowcounts.txt, hdfs_du.txt           measured input size
  vmstat.log                           CPU, memory, swap and I/O samples (5 s)

Usage: python analysis/parse_results.py [results_dir]
Compatible with Python 3.7 (the kit's lib/python-venv).
"""
import csv
import glob
import os
import re
import sys

THRESHOLDS = {"3": 5.4, "7": 1.8}  # lower is better for both metrics
RUN_RE = re.compile(r"sf(\d+)_c(\d+)_s(\d+)_r(\d+)$")


def read_first(pattern):
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


def parse_metrics(run_dir):
    out = {}
    path = read_first(os.path.join(run_dir, "kit_logs", "tpcxai-metrics-*.csv"))
    if not path:
        return out
    with open(path) as f:
        for row in csv.DictReader(f):
            uc = row.get("use_case", "").strip()
            if uc not in THRESHOLDS:
                continue
            tag = "uc%s" % uc
            for key, name in (("Phase.TRAINING_1", "train"), ("Phase.SERVING_1", "serve")):
                if row.get(key):
                    out["%s_%s_s" % (tag, name)] = float(row[key])
            if row.get("qualitity_metric_value"):
                q = float(row["qualitity_metric_value"])
                out[tag + "_quality"] = q
                out[tag + "_metric"] = row.get("qualitity_metric_name", "")
                out[tag + "_pass"] = int(q <= THRESHOLDS[uc])
    return out


def parse_aiucpm(run_dir):
    out = {}
    path = read_first(os.path.join(run_dir, "kit_logs", "adabench-aiucpm-metrics-*"))
    if not path:
        return out
    with open(path) as f:
        for line in f:
            m = re.match(r"\s*(DATAGEN|TLOAD|TTT)\s*:\s*([\d.]+)", line)
            if m:
                out[m.group(1).lower() + "_s"] = float(m.group(2))
    return out


def parse_streams(run_dir):
    out = {}
    path = os.path.join(run_dir, "console.log")
    if not os.path.exists(path):
        return out
    with open(path, errors="replace") as f:
        text = f.read()
    times = [float(t) for t in re.findall(r"serving_throughput_stream_\d+\s+([\d.]+)\s*$", text, re.M)]
    if times:
        out["stream_mean_s"] = sum(times) / len(times)
        out["stream_max_s"] = max(times)
        out["n_streams_reported"] = len(times)
    return out


def parse_rows(run_dir):
    out = {}
    path = os.path.join(run_dir, "rowcounts.txt")
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                parts = line.split()
                if len(parts) == 2 and parts[1] != "total":
                    name = os.path.splitext(os.path.basename(parts[1]))[0]
                    out["rows_" + name] = max(int(parts[0]) - 1, 0)  # minus header line
    path = os.path.join(run_dir, "hdfs_du.txt")
    if os.path.exists(path):
        with open(path) as f:
            first = f.read().split()
        if first and first[0].isdigit():
            out["hdfs_training_bytes"] = int(first[0])
    return out


def parse_vmstat(run_dir):
    out = {}
    path = os.path.join(run_dir, "vmstat.log")
    if not os.path.exists(path):
        return out
    header, rows = None, []
    with open(path) as f:
        for line in f:
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "r" and "free" in parts:
                header = parts
            elif header and parts[0].isdigit():
                rows.append(parts)
    if not header or not rows:
        return out

    def col(name):
        i = header.index(name)
        return [float(r[i]) for r in rows if len(r) > i]

    swpd, free = col("swpd"), col("free")
    us, sy, wa = col("us"), col("sy"), col("wa")
    si, so = col("si"), col("so")
    bi, bo = col("bi"), col("bo")
    n = float(len(us))
    out.update({
        "cpu_busy_mean_pct": sum(a + b for a, b in zip(us, sy)) / n,
        "cpu_busy_max_pct": max(a + b for a, b in zip(us, sy)),
        "iowait_mean_pct": sum(wa) / n,
        "swap_used_max_mb": max(swpd) / 1024.0,
        "free_mem_min_mb": min(free) / 1024.0,
        "swap_in_out_max_kbs": max(a + b for a, b in zip(si, so)),
        "disk_io_max_kbs": max(a + b for a, b in zip(bi, bo)),
        "vmstat_samples": len(rows),
    })
    return out


def parse_run(exp, run_dir):
    m = RUN_RE.search(run_dir.rstrip("/"))
    if not m:
        return None
    rec = {"experiment": exp, "run": os.path.basename(run_dir.rstrip("/")),
           "sf": int(m.group(1)), "cores": int(m.group(2)),
           "streams": int(m.group(3)), "rep": int(m.group(4)),
           "done": int(os.path.exists(os.path.join(run_dir, "DONE")))}
    for name in ("exit_code", "start_epoch", "end_epoch"):
        p = os.path.join(run_dir, name)
        if os.path.exists(p):
            with open(p) as f:
                rec[name] = int(f.read().strip() or -1)
    if "start_epoch" in rec and "end_epoch" in rec:
        rec["wall_clock_s"] = rec["end_epoch"] - rec["start_epoch"]
    for fn in (parse_metrics, parse_aiucpm, parse_streams, parse_rows, parse_vmstat):
        rec.update(fn(run_dir))
    return rec


def main():
    results = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "results")
    raw = os.path.join(results, "raw")
    records = []
    for exp in sorted(os.listdir(raw)) if os.path.isdir(raw) else []:
        exp_dir = os.path.join(raw, exp)
        if not os.path.isdir(exp_dir):
            continue  # e.g. .gitkeep
        for run in sorted(os.listdir(exp_dir)):
            run_dir = os.path.join(exp_dir, run)
            if not os.path.isdir(run_dir):
                continue
            rec = parse_run(exp, run_dir)
            if rec:
                records.append(rec)
    if not records:
        print("no runs found under", raw)
        return
    keys = []
    for r in records:
        for k in r:
            if k not in keys:
                keys.append(k)
    out = os.path.join(results, "summary.csv")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(records)
    print("wrote %s (%d runs)" % (out, len(records)))


if __name__ == "__main__":
    main()
