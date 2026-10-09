#!/usr/bin/env bash
# 일일 백업 (RA §10 '백업은 pg_dump 일 1회 + rawdata rsync', runbook §8, R3 minor 34).
#
#   infra/backup.sh [백업 디렉터리]        # 기본 ./backup  (cron: 0 3 * * * cd <repo> && infra/backup.sh /srv/backup)
#
# - DB: docker compose 의 db 서비스에서 pg_dump -Fc(사용자 지정 형식 — pg_restore 로 골라 복구) → db-<날짜>.dump
# - 원문: rawdata 볼륨(/data)을 rsync 로 raw/ 에 증분 복사(삭제 전파 없음 — 보존 무기한, D1 #14).
#   rsync 가 없으면 tar 스냅샷(raw-<날짜>.tgz)으로 대신한다.
# - 덤프는 pg_restore --list 로 바로 검증한다. 실패하면 0 이 아닌 코드로 끝난다(cron 메일).
# 비밀값(POSTGRES_PASSWORD 등)은 infra/.env 에서 compose 가 읽는다 — 이 스크립트는 값을 출력하지 않는다.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE=(docker compose -f "$HERE/docker-compose.yml")
DEST="${1:-./backup}"
DAY="$(date +%F)"
PROJECT="${COMPOSE_PROJECT_NAME:-subscription-analyzer}"
VOLUME="${PROJECT}_rawdata"

mkdir -p "$DEST/raw"

# --- DB (pg_dump -Fc)
DUMP="$DEST/db-$DAY.dump"
"${COMPOSE[@]}" exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' >"$DUMP.part"
mv "$DUMP.part" "$DUMP"
"${COMPOSE[@]}" exec -T db pg_restore --list >/dev/null <"$DUMP"
echo "db: $DUMP ($(wc -c <"$DUMP") bytes)"

# --- 원문 (rawdata 볼륨 → raw/, 증분)
if command -v rsync >/dev/null 2>&1; then
  docker run --rm -v "$VOLUME:/data:ro" -v "$(cd "$DEST" && pwd)/raw:/backup" alpine:3.20 \
    sh -c 'apk add --no-cache rsync >/dev/null && rsync -a /data/ /backup/'
  echo "raw: rsync → $DEST/raw/"
else
  docker run --rm -v "$VOLUME:/data:ro" -v "$(cd "$DEST" && pwd):/backup" alpine:3.20 \
    tar -czf "/backup/raw-$DAY.tgz" -C /data .
  tar -tzf "$DEST/raw-$DAY.tgz" >/dev/null
  echo "raw: $DEST/raw-$DAY.tgz"
fi
