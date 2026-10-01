# =============================================================================
# db.py - PostgreSQL 데이터베이스 연결 + 처음 준비(표 만들기, 시작 데이터 넣기)     버전: test 3.0
#
# 하는 일
#   1) connect()      : DB에 연결 (요청마다 열고, 다 쓰면 닫음)
#   2) wait_for_db()  : 서버가 켜질 때 DB가 준비될 때까지 기다림 (재시도)
#   3) init_schema()  : schema.sql 을 실행해서 표를 만듦 (이미 있으면 건너뜀)
#   4) seed_menus()   : 메뉴 표가 비어 있으면 data/menus.json 을 DB로 옮김 (시작 데이터 = seed)
#   5) fetch_menus()  : DB의 메뉴를 읽어서 추천 로직이 쓰는 모양(딕셔너리 리스트)으로 돌려줌
#
# 라이브러리: psycopg (파이썬에서 PostgreSQL 을 쓰는 표준 라이브러리, 버전 3)
# =============================================================================

import json
import os
import time
from pathlib import Path

import psycopg                         # PostgreSQL 연결 라이브러리
from psycopg.rows import dict_row      # 결과를 {"칸이름": 값} 딕셔너리로 받기 위한 설정

# DB 접속 주소. docker-compose.yml 에서 환경변수로 넣어 줌
# 형식: postgresql://사용자:비밀번호@호스트:포트/DB이름
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://menu:menu_pw@localhost:5432/menu")

HERE = Path(__file__).parent
SCHEMA_PATH = HERE / "schema.sql"
SEED_PATH = HERE / "data" / "menus.json"


def connect():
    """DB 연결을 하나 엽니다.

    사용법:  with db.connect() as conn:   ← with 블록이 끝나면 자동으로 저장(commit)하고 닫음
                 conn.execute("SELECT ...")
    row_factory=dict_row : 결과 한 줄을 {"name": "국밥", ...} 처럼 딕셔너리로 받음 (칸 이름으로 꺼내기 쉬움)
    """
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def wait_for_db(timeout=60):
    """DB가 켜질 때까지 2초마다 다시 시도합니다 (최대 timeout 초).

    Docker 는 컨테이너를 거의 동시에 켜기 때문에, 백엔드가 먼저 켜지면 DB가 아직 준비 안 됐을 수 있음.
    바로 포기하지 않고 "재시도" 하는 것이 여러 서비스를 함께 돌릴 때의 기본기입니다.
    """
    start = time.time()
    while True:
        try:
            with connect() as conn:
                conn.execute("SELECT 1")   # 가장 간단한 질문: 살아 있니?
            return
        except psycopg.OperationalError:
            if time.time() - start > timeout:
                raise                      # 너무 오래 기다렸으면 에러를 그대로 올려서 알림
            time.sleep(2)


def init_schema():
    """schema.sql 을 실행해서 표를 만듭니다. (IF NOT EXISTS 라서 여러 번 실행해도 안전)"""
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with connect() as conn:
        conn.execute(sql)


def seed_menus(menus, categories):
    """메뉴 표가 비어 있으면 menus.json 의 데이터를 DB에 넣습니다.

    menus      : menus.json 의 메뉴 리스트 (menus.py 가 검사를 마친 것)
    categories : 종류 이름 목록 (한식, 중식 ...)
    반환: 새로 넣은 메뉴 수 (이미 데이터가 있으면 0)
    """
    with connect() as conn:
        # 이미 메뉴가 있으면 넣지 않음 → DB에 쌓인 자산을 덮어쓰지 않기 위해
        count = conn.execute("SELECT COUNT(*) AS n FROM menus").fetchone()["n"]
        if count > 0:
            return 0

        # 트랜잭션: 아래 작업 전체가 "모두 성공하거나, 하나라도 실패하면 모두 취소"
        # → 메뉴 절반만 들어간 어정쩡한 상태가 생기지 않음
        with conn.transaction():
            # ① 종류
            cat_id = {}
            for name in categories:
                # %s : 값이 들어갈 자리 (플레이스홀더). 값을 문자열로 직접 이어 붙이지 않는 이유 → SQL 인젝션 공격 방지
                row = conn.execute(
                    "INSERT INTO categories (name) VALUES (%s) RETURNING id", (name,)
                ).fetchone()
                cat_id[name] = row["id"]

            # ② 메뉴 본체 (종류 태그는 category_id 로, 나머지 태그는 menu_tags 로)
            menu_id = {}
            for m in menus:
                kind = next(t for t in m["tags"] if t in cat_id)
                row = conn.execute(
                    "INSERT INTO menus (name, emoji, category_id, broad, kcal) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    (m["name"], m["emoji"], cat_id[kind], m["broad"], m["kcal"]),
                ).fetchone()
                menu_id[m["name"]] = row["id"]

            # ③ 여러 개인 정보들 (태그, 식사 시간, 재료, 팁)
            for m in menus:
                mid = menu_id[m["name"]]
                for tag in m["tags"]:
                    if tag not in cat_id:
                        conn.execute("INSERT INTO menu_tags (menu_id, tag) VALUES (%s, %s)", (mid, tag))
                for meal in m["meals"]:
                    conn.execute("INSERT INTO menu_meals (menu_id, meal) VALUES (%s, %s)", (mid, meal))
                # enumerate(리스트) : (순서번호, 값) → 화면에 보여 줄 순서를 position 으로 저장
                for i, ing in enumerate(m["ingredients"]):
                    conn.execute(
                        "INSERT INTO menu_ingredients (menu_id, ingredient, position) VALUES (%s, %s, %s)", (mid, ing, i)
                    )
                for i, tip in enumerate(m["tips"]):
                    conn.execute("INSERT INTO menu_tips (menu_id, tip, position) VALUES (%s, %s, %s)", (mid, tip, i))

            # ④ 관련 메뉴 연결 (모든 메뉴가 들어간 뒤에야 서로의 id 를 알 수 있어서 마지막에)
            for m in menus:
                for i, rel in enumerate(m["related"]):
                    conn.execute(
                        "INSERT INTO menu_relations (menu_id, related_id, position) VALUES (%s, %s, %s)",
                        (menu_id[m["name"]], menu_id[rel], i),
                    )
        return len(menus)


def fetch_menus():
    """DB의 메뉴 전체를 읽어서, 추천 로직이 쓰는 딕셔너리 리스트로 돌려줍니다.

    표가 여러 개로 나뉘어 있으니, 각 표를 읽어서 메뉴별로 다시 모읍니다.
    (JOIN 이나 array_agg 로 SQL 한 번에 모을 수도 있지만, 공부용으로 단계별로 나눠서 읽음)
    """
    with connect() as conn:
        # JOIN : 두 표를 id 로 이어 붙여서 함께 읽기 → 메뉴와 그 종류 이름을 한 번에
        rows = conn.execute(
            """
            SELECT m.id, m.name, m.emoji, m.broad, m.kcal, m.kcal_source, c.name AS category
            FROM menus m JOIN categories c ON c.id = m.category_id
            ORDER BY m.id
            """
        ).fetchall()
        by_id = {}
        for r in rows:
            by_id[r["id"]] = {
                "name": r["name"], "emoji": r["emoji"], "broad": r["broad"], "kcal": r["kcal"],
                "kcal_source": r["kcal_source"],
                "tags": [r["category"]],   # 추천 로직은 종류도 태그로 다루므로 맨 앞에 넣어 줌
                "meals": [], "ingredients": [], "tips": [], "related": [],
            }

        for r in conn.execute("SELECT menu_id, tag FROM menu_tags ORDER BY menu_id, tag"):
            by_id[r["menu_id"]]["tags"].append(r["tag"])
        for r in conn.execute("SELECT menu_id, meal FROM menu_meals"):
            by_id[r["menu_id"]]["meals"].append(r["meal"])
        for r in conn.execute("SELECT menu_id, ingredient FROM menu_ingredients ORDER BY menu_id, position"):
            by_id[r["menu_id"]]["ingredients"].append(r["ingredient"])
        for r in conn.execute("SELECT menu_id, tip FROM menu_tips ORDER BY menu_id, position"):
            by_id[r["menu_id"]]["tips"].append(r["tip"])
        for r in conn.execute("SELECT menu_id, related_id FROM menu_relations ORDER BY menu_id, position"):
            by_id[r["menu_id"]]["related"].append(by_id[r["related_id"]]["name"])

        return list(by_id.values())


def load_seed_file():
    """data/menus.json 을 읽어서 메뉴 리스트를 돌려줍니다."""
    with open(SEED_PATH, encoding="utf-8") as f:
        return json.load(f)["menus"]
