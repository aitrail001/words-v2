#!/bin/zsh

set -u

SHOW_TAIL=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-tail)
      SHOW_TAIL=0
      shift
      ;;
    *)
      break
      ;;
  esac
done

SNAPSHOT_DIR="${1:-${SNAPSHOT_DIR:-.}}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-5}"
TAIL_ROWS="${TAIL_ROWS:-3}"

if [[ ! -d "$SNAPSHOT_DIR" ]]; then
  print -u2 "snapshot dir not found: $SNAPSHOT_DIR"
  exit 1
fi

count_lines() {
  local file_path="$1"
  if [[ -f "$file_path" ]]; then
    wc -l < "$file_path"
  else
    print "missing"
  fi
}

while true; do
  clear
  print "$(date '+%Y-%m-%d %H:%M:%S')"
  print "snapshot: $SNAPSHOT_DIR"
  print ""

  for file in words.enriched.jsonl enrich.checkpoint.jsonl enrich.decisions.jsonl enrich.failures.jsonl; do
    printf "%-28s %s\n" "$file" "$(count_lines "$SNAPSHOT_DIR/$file")"
  done

  if [[ "$SHOW_TAIL" -eq 1 && "$TAIL_ROWS" -gt 0 && -f "$SNAPSHOT_DIR/words.enriched.jsonl" ]]; then
    print ""
    print "latest accepted rows:"
    tail -n "$TAIL_ROWS" "$SNAPSHOT_DIR/words.enriched.jsonl"
  fi

  sleep "$INTERVAL_SECONDS"
done
