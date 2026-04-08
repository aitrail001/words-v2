#!/bin/zsh

set -u

SHOW_TAIL=1
ONCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --once)
      ONCE=1
      shift
      ;;
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

print_section() {
  local title="$1"
  shift
  local file
  print "$title"
  for file in "$@"; do
    printf "%-36s %s\n" "$file" "$(count_lines "$SNAPSHOT_DIR/$file")"
  done
}

while true; do
  if [[ "$ONCE" -ne 1 ]]; then
    clear
  fi
  print "$(date '+%Y-%m-%d %H:%M:%S')"
  print "snapshot: $SNAPSHOT_DIR"
  print ""

  print_section "realtime artifacts:" \
    words.enriched.jsonl \
    enrich.checkpoint.jsonl \
    enrich.decisions.jsonl \
    enrich.failures.jsonl

  print ""
  print_section "staged core artifacts:" \
    words.enriched.core.jsonl \
    words.enriched.core.runtime.jsonl \
    enrich.core.checkpoint.jsonl \
    enrich.core.decisions.jsonl \
    enrich.core.failures.jsonl

  print ""
  print_section "staged translation artifacts:" \
    words.translations.jsonl \
    enrich.translations.checkpoint.jsonl \
    enrich.translations.decisions.jsonl \
    enrich.translations.failures.jsonl

  if [[ "$SHOW_TAIL" -eq 1 && "$TAIL_ROWS" -gt 0 && -f "$SNAPSHOT_DIR/words.enriched.jsonl" ]]; then
    print ""
    print "latest accepted rows:"
    tail -n "$TAIL_ROWS" "$SNAPSHOT_DIR/words.enriched.jsonl"
  elif [[ "$SHOW_TAIL" -eq 1 && "$TAIL_ROWS" -gt 0 && -f "$SNAPSHOT_DIR/words.enriched.core.jsonl" ]]; then
    print ""
    print "latest staged core rows:"
    tail -n "$TAIL_ROWS" "$SNAPSHOT_DIR/words.enriched.core.jsonl"
  elif [[ "$SHOW_TAIL" -eq 1 && "$TAIL_ROWS" -gt 0 && -f "$SNAPSHOT_DIR/words.translations.jsonl" ]]; then
    print ""
    print "latest staged translation rows:"
    tail -n "$TAIL_ROWS" "$SNAPSHOT_DIR/words.translations.jsonl"
  fi

  if [[ "$ONCE" -eq 1 ]]; then
    break
  fi
  sleep "$INTERVAL_SECONDS"
done
