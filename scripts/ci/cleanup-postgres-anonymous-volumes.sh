#!/usr/bin/env bash
set -euo pipefail

is_postgres_data_volume() {
  local volume_name="$1"

  docker run --rm -v "${volume_name}:/v" alpine sh -lc '
    test -f /v/PG_VERSION \
      || test -f /v/data/PG_VERSION \
      || test -f /v/18/docker/PG_VERSION
  ' >/dev/null 2>&1
}

volume_in_use() {
  local volume_name="$1"
  docker ps -a --filter "volume=${volume_name}" -q | grep -q .
}

main() {
  local volume_name
  local removed=0
  local skipped=0

  while IFS= read -r volume_name; do
    [[ -n "${volume_name}" ]] || continue

    if volume_in_use "${volume_name}"; then
      echo "[skip] in use: ${volume_name}"
      skipped=$((skipped + 1))
      continue
    fi

    if ! is_postgres_data_volume "${volume_name}"; then
      echo "[skip] not postgres data: ${volume_name}"
      skipped=$((skipped + 1))
      continue
    fi

    echo "[remove] stale postgres anonymous volume: ${volume_name}"
    docker volume rm "${volume_name}" >/dev/null
    removed=$((removed + 1))
  done < <(docker volume ls -q --filter label=com.docker.volume.anonymous)

  echo "[summary] removed=${removed} skipped=${skipped}"
}

main "$@"
