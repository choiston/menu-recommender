#!/bin/bash
# =============================================================================
# scripts/restore.sh - 백업 파일로 DB 되돌리기                              (test 3.4)
#
# 실행:  ./scripts/restore.sh backups/menu-20261002-0400.sql.gz
#
# ⚠️ 지금 DB의 내용이 백업 시점으로 "덮어써집니다". 그 사이에 가입한 회원·기록은 사라져요.
#    그래서 되돌리기 직전에 지금 상태를 한 번 더 백업해 둡니다.
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

DOCKER="${DOCKER:-docker}"
FILE="${1:-}"

if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
  echo "사용법: ./scripts/restore.sh backups/menu-날짜-시간.sql.gz"
  echo "있는 백업:"; ls -1t backups/menu-*.sql.gz 2>/dev/null || echo "  (없음)"
  exit 1
fi

# read -p : 질문을 보여 주고 입력을 받음 → 실수로 덮어쓰지 않게 한 번 더 확인
read -r -p "정말 '$FILE' 로 DB를 되돌릴까요? 지금 데이터는 덮어써져요. (yes 입력) " answer
[ "$answer" = "yes" ] || { echo "취소했어요."; exit 0; }

echo "되돌리기 전에 지금 상태를 백업해 둘게요…"
./scripts/backup.sh

# 표를 모두 지우고(스키마를 새로 만들고) 백업 내용을 다시 넣음
"$DOCKER" exec menu-db psql -U menu -d menu -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
gunzip -c "$FILE" | "$DOCKER" exec -i menu-db psql -U menu -d menu -q
echo "되돌리기 완료. 백엔드를 다시 켜서 메뉴를 다시 읽어요…"
"$DOCKER" restart menu-backend
