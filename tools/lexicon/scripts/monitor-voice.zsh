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

VOICE_DIR="${1:-${VOICE_DIR:-.}}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-5}"
TAIL_ROWS="${TAIL_ROWS:-3}"

if [[ ! -d "$VOICE_DIR" ]]; then
  print -u2 "voice dir not found: $VOICE_DIR"
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

numeric_or_zero() {
  local value="$1"
  if [[ "$value" == <-> ]]; then
    print "$value"
  else
    print "0"
  fi
}

while true; do
  planned=""
  manifest=""
  errors=""
  generated=""
  existing=""
  failed=""
  scheduled=""
  planned="$(count_lines "$VOICE_DIR/voice_plan.jsonl")"
  manifest="$(count_lines "$VOICE_DIR/voice_manifest.jsonl")"
  errors="$(count_lines "$VOICE_DIR/voice_errors.jsonl")"
  generated="$(numeric_or_zero "$( [[ -f "$VOICE_DIR/voice_manifest.jsonl" ]] && rg -c '"status": "generated"' "$VOICE_DIR/voice_manifest.jsonl" || print 0 )")"
  existing="$(numeric_or_zero "$( [[ -f "$VOICE_DIR/voice_manifest.jsonl" ]] && rg -c '"status": "existing"' "$VOICE_DIR/voice_manifest.jsonl" || print 0 )")"
  failed="$(numeric_or_zero "$( [[ -f "$VOICE_DIR/voice_errors.jsonl" ]] && rg -c '"status": "failed"' "$VOICE_DIR/voice_errors.jsonl" || print 0 )")"
  scheduled=$(( $(numeric_or_zero "$planned") - $(numeric_or_zero "$generated") - $(numeric_or_zero "$existing") - $(numeric_or_zero "$failed") ))
  if (( scheduled < 0 )); then
    scheduled=0
  fi

  clear
  print "$(date '+%Y-%m-%d %H:%M:%S')"
  print "voice dir: $VOICE_DIR"
  print ""
  printf "%-24s %s\n" "voice_plan.jsonl" "$planned"
  printf "%-24s %s\n" "voice_manifest.jsonl" "$manifest"
  printf "%-24s %s\n" "voice_errors.jsonl" "$errors"
  print ""
  printf "%-24s %s\n" "generated" "$generated"
  printf "%-24s %s\n" "existing" "$existing"
  printf "%-24s %s\n" "failed" "$failed"
  printf "%-24s %s\n" "remaining" "$scheduled"

  if [[ "$SHOW_TAIL" -eq 1 && "$TAIL_ROWS" -gt 0 ]]; then
    if [[ -f "$VOICE_DIR/voice_manifest.jsonl" ]]; then
      print ""
      print "latest manifest rows:"
      tail -n "$TAIL_ROWS" "$VOICE_DIR/voice_manifest.jsonl"
    fi
    if [[ -f "$VOICE_DIR/voice_errors.jsonl" ]]; then
      print ""
      print "latest error rows:"
      tail -n "$TAIL_ROWS" "$VOICE_DIR/voice_errors.jsonl"
    fi
  fi

  sleep "$INTERVAL_SECONDS"
done
