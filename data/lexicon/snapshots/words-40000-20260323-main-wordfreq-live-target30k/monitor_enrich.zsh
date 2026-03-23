#!/bin/zsh

SNAPSHOT_DIR="/Users/johnson/AI/src/words-v2/data/lexicon/snapshots/words-40000-20260323-main-wordfreq-live-target30k"

while true; do
  clear
  print "$(date '+%Y-%m-%d %H:%M:%S')"
  for f in words.enriched.jsonl enrich.checkpoint.jsonl enrich.decisions.jsonl enrich.failures.jsonl; do
    p="$SNAPSHOT_DIR/$f"
    if [[ -f "$p" ]]; then
      printf "%-28s %s\n" "$f" "$(wc -l < "$p")"
    else
      printf "%-28s %s\n" "$f" "missing"
    fi
  done
  print ""
  #tail -n 3 "$SNAPSHOT_DIR/words.enriched.jsonl" 2>/dev/null
  sleep 30
done
