#!/bin/bash
# =============================================================================
# scripts/backup.sh - DB 백업 (회원·기록 = 우리 자산 지키기)                 (test 3.4)
#
# 하는 일: DB 전체를 SQL 파일로 뽑아(pg_dump) 압축해서 backups/ 폴더에 저장하고,
#          오래된 백업은 KEEP 개만 남기고 지움 (기본 14개 = 하루 1번이면 2주)
#
# 실행:   ./scripts/backup.sh
# 매일 자동 (Mac): crontab -e 에 한 줄 추가  →  매일 새벽 4시
#   0 4 * * * DOCKER=/usr/local/bin/docker /Users/내이름/menu-recommender/scripts/backup.sh >> /Users/내이름/menu-backup.log 2>&1
#   (OrbStack 이면 DOCKER=$HOME/.orbstack/bin/docker. `which docker` 로 확인)
#
# ⚠️ 백업 파일에는 회원 이메일과 기록이 들어 있어요. backups/ 는 .gitignore 에 있어서 GitHub 에 안 올라가요.
#    서버 고장에 대비하려면 가끔 다른 곳(NAS 등)에도 복사해 두세요.
# =============================================================================

# set -e : 중간에 하나라도 실패하면 바로 멈춤 / -u : 정의 안 된 변수를 쓰면 멈춤 / -o pipefail : 파이프(|) 중간 실패도 잡음
set -euo pipefail

# 이 스크립트가 있는 폴더의 한 단계 위(프로젝트 폴더)로 이동 → 어디서 실행해도 같은 곳에 저장
cd "$(dirname "$0")/.."

DOCKER="${DOCKER:-docker}"          # docker 명령 위치 (cron 에서는 전체 경로가 필요할 때가 있음)
KEEP="${KEEP:-14}"                  # 남길 백업 개수
STAMP="$(date +%Y%m%d-%H%M)"        # 파일 이름에 붙일 날짜-시간  예) 20261002-0400
FILE="backups/menu-$STAMP.sql.gz"

mkdir -p backups
chmod 700 backups                   # 백업 폴더는 나만 볼 수 있게

# pg_dump : PostgreSQL 이 표 구조 + 데이터를 SQL 문장으로 뽑아 주는 도구
# gzip    : 압축 (보통 1/5 크기)
"$DOCKER" exec menu-db pg_dump -U menu menu | gzip > "$FILE"
chmod 600 "$FILE"                   # 백업 파일도 나만 읽을 수 있게
echo "[$(date '+%F %T')] 백업 완료: $FILE ($(du -h "$FILE" | cut -f1))"

# 오래된 백업 지우기: 최신순으로 정렬해서 KEEP 개 다음부터 삭제
# (macOS 의 xargs 에는 -r 옵션이 없어서 while 반복문으로 처리)
ls -1t backups/menu-*.sql.gz | tail -n +"$((KEEP + 1))" | while read -r old; do
  rm -f "$old"
  echo "  오래된 백업 삭제: $old"
done
