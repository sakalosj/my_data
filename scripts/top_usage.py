#!/usr/bin/env python3
import subprocess
from collections import defaultdict

def parse_ps_output(fields, sort_by):
    cmd = ["ps", "-eo", ",".join(fields), f"--sort=-{sort_by}"]
    output = subprocess.check_output(cmd, text=True)
    lines = output.strip().split('\n')[1:]  # skip header

    grouped = defaultdict(lambda: {"rss": 0, "cpu": 0.0, "procs": 0, "threads": 0})

    for line in lines:
        parts = line.strip().split(None, len(fields) - 1)
        if len(parts) < 4:
            continue
        cmd_name = parts[-1]
        try:
            rss_kb = int(parts[0])
            cpu = float(parts[1])
            nlwp = int(parts[2])
        except ValueError:
            continue

        g = grouped[cmd_name]
        g["rss"] += rss_kb
        g["cpu"] += cpu
        g["procs"] += 1
        g["threads"] += nlwp

    return grouped

def print_table(data, sort_key, title):
    print(f"\n=== Top by {title} ===")
    header = f"{'COMMAND':<25} {'RSS_MB':>8} {'CPU_%':>8} {'PROCS':>6} {'THREADS':>8}"
    print(header)
    print("-" * len(header))
    for cmd, stats in sorted(data.items(), key=lambda x: x[1][sort_key], reverse=True)[:20]:
        rss_mb = stats["rss"] / 1024
        print(f"{cmd:<25} {rss_mb:8.1f} {stats['cpu']:8.1f} {stats['procs']:6d} {stats['threads']:8d}")

def main():
    fields = ["rss", "%cpu", "nlwp", "comm"]
    data = parse_ps_output(fields, sort_by="%cpu")  # sorting doesn't matter here, we re-sort

    print_table(data, sort_key="rss", title="Memory (RSS)")
    print_table(data, sort_key="cpu", title="CPU Usage")

if __name__ == "__main__":
    main()

