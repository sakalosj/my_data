#!/bin/bash

echo "=== Top Memory Usage by Program Name (Grouped, RSS in MB) ==="
ps -eo comm=,rss=,nlwp= | \
awk '
{
    mem[$1] += $2;           # sum RSS
    procs[$1] += 1;          # count processes
    threads[$1] += $3;       # sum threads
}
END {
    printf "%-20s %8s %8s %8s\n", "COMMAND", "RSS_MB", "PROCS", "THREADS"
    for (cmd in mem)
        printf "%-20s %8.1f %8d %8d\n", cmd, mem[cmd]/1024, procs[cmd], threads[cmd]
}' | sort -k2 -nr | head -n 20

