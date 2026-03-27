#!/bin/zsh
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <output-file> [interval-seconds]" >&2
  exit 1
fi

output_file="$1"
interval="${2:-2}"

mkdir -p "$(dirname "$output_file")"
echo "timestamp,container,cpu_perc,mem_usage,mem_perc,net_io,block_io,pids" > "$output_file"

while true; do
  timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  docker stats --no-stream --format '{{.Name}},{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}},{{.NetIO}},{{.BlockIO}},{{.PIDs}}' \
    words-prod-postgres words-prod-redis words-prod-backend words-prod-worker words-prod-frontend words-prod-admin-frontend words-prod-nginx \
    | while IFS= read -r line; do
        echo "${timestamp},${line}" >> "$output_file"
      done
  sleep "$interval"
done
