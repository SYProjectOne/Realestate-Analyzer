#!/usr/bin/env bash
# 원문 월별 압축 (runbook §6 디스크 부족, R3 minor 34). 삭제가 아니라 압축 — 보존 무기한(D1 #14).
#
#   infra/raw_archive.sh <RAW_DIR> <source> <yyyy-mm>
#   예) docker compose exec worker infra/raw_archive.sh /data/raw applyhome_list 2026-08
#
# 결과: <RAW_DIR>/<source>/<yyyy-mm>.tar.gz. 구성원 이름은 RAW_DIR 기준 상대 경로(<source>/<yyyy-mm-dd>/<sha256>.<ext>)
# = DB raw_document.path 그대로라서 API GET /raw/{id} 가 원본이 없으면 이 압축에서 읽는다(api.routers.complexes).
# 압축을 tar -tzf 로 검증하고 모든 파일이 들어 있음을 확인한 뒤에만 원본 날짜 디렉터리를 지운다.
set -euo pipefail

RAW_DIR="${1:?RAW_DIR}"
SOURCE="${2:?source (예: applyhome_list)}"
MONTH="${3:?yyyy-mm}"

[[ "$MONTH" =~ ^[0-9]{4}-[0-9]{2}$ ]] || { echo "월 형식은 yyyy-mm" >&2; exit 2; }
[[ "$SOURCE" =~ ^[a-z0-9][a-z0-9_.-]*$ ]] || { echo "source 형식 오류" >&2; exit 2; }
[[ "$MONTH" < "$(date +%Y-%m)" ]] || { echo "이번 달은 압축하지 않는다(수집 중)" >&2; exit 2; }

cd "$RAW_DIR"
shopt -s nullglob
DAYS=("$SOURCE"/"$MONTH"-*/)
if [ ${#DAYS[@]} -eq 0 ]; then
  echo "압축할 날짜 디렉터리 없음: $SOURCE/$MONTH-*"
  exit 0
fi
ARCHIVE="$SOURCE/$MONTH.tar.gz"
[ -e "$ARCHIVE" ] && { echo "이미 있음: $ARCHIVE (덮어쓰지 않는다)" >&2; exit 3; }

tar -C "$RAW_DIR" -czf "$ARCHIVE.part" "${DAYS[@]%/}"
# 검증: 압축 목록 = 디스크의 파일 목록
diff <(tar -tzf "$ARCHIVE.part" | grep -v '/$' | sort) <(find "${DAYS[@]%/}" -type f | sort) >/dev/null \
  || { echo "검증 실패 — 원본을 그대로 둔다" >&2; rm -f "$ARCHIVE.part"; exit 4; }
mv "$ARCHIVE.part" "$ARCHIVE"
rm -rf -- "${DAYS[@]%/}"
echo "archived: $RAW_DIR/$ARCHIVE (${#DAYS[@]} days)"
