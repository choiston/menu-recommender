# =============================================================================
# records.py - 선택 기록 저장 + 📒 내 기록 + 개인 취향 계산              버전: test 3.0
#
# 로그인한 사람만 해당됩니다. (로그인하지 않은 사람의 선택은 아무것도 저장하지 않음 → 시작 화면의 약속)
#
#   save_decision()   : "✅ 이걸로 먹을래요" 를 누르면 DB에 한 줄 저장
#   get_records()     : 📒 내 기록 화면용 - 결정 목록 + 통계(많이 먹은 메뉴, 종류, 시간대)
#   personal_weights(): 기록으로 계산한 "개인 취향 태그 점수" → 추천 순서에 조용히 반영
#
# 역할 나누기 (지금까지와 같은 원칙)
#   - 숫자(통계, 취향 점수)는 코드가 정확하게 계산
#   - AI는 그 숫자를 받아서 📒 내 기록 화면에 보여 줄 "문장"만 씀 (ai_comment.write_insight)
# =============================================================================

from collections import Counter

from fastapi import HTTPException

import db
from menus import MENU_BY_ID

# 취향 점수에서 뺄 태그: 인원수에서 온 "상황" 정보라서 입맛과는 다름
PERSONAL_EXCLUDE = {"혼밥", "나눠먹기"}
PERSONAL_MAX = 2.0        # 한 태그의 개인 취향 점수 최대값 (기분 가중치와 비슷한 크기 → 너무 세지 않게)
PERSONAL_MIN_RECORDS = 3  # 기록이 이 개수보다 적으면 취향을 반영하지 않음 (한두 번으로 판단하면 틀리기 쉬움)
RECENT_LIMIT = 50         # 취향 계산과 목록에 쓰는 최근 기록 수


def save_decision(user_id, req):
    """"✅ 이걸로 먹을래요" 기록 저장. req = main.py 의 DecisionRequest"""
    with db.connect() as conn:
        row = conn.execute("SELECT id FROM menus WHERE name = %s", (req.menu,)).fetchone()
        if not row:
            raise HTTPException(404, "없는 메뉴예요.")
        conn.execute(
            """
            INSERT INTO decisions (user_id, menu_id, source, ai_pick, meal, mood, people, ingredient, picks)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, row["id"], req.source, req.ai_pick, req.meal, req.mood, req.people, req.keyword, req.picks),
        )


def _recent(user_id, limit=RECENT_LIMIT):
    """이 사용자의 최근 기록 (새것부터)"""
    with db.connect() as conn:
        return conn.execute(
            """
            SELECT d.decided_at, d.source, d.ai_pick, d.meal, d.mood, d.people, m.name AS menu, m.emoji
            FROM decisions d JOIN menus m ON m.id = d.menu_id
            WHERE d.user_id = %s
            ORDER BY d.decided_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        ).fetchall()


def get_records(user_id):
    """📒 내 기록 화면에 필요한 것: 결정 목록 + 통계"""
    rows = _recent(user_id)

    # Counter : 값마다 몇 번 나왔는지 세어 주는 도구.  most_common(3) → 많이 나온 순서로 3개
    menu_count = Counter(r["menu"] for r in rows)
    kind_count = Counter(MENU_BY_ID[r["menu"]]["tags"][0] for r in rows if r["menu"] in MENU_BY_ID)
    meal_count = Counter(r["meal"] for r in rows if r["meal"])
    # AI 추천(🤖 오늘은 이거예요)을 그대로 고른 비율 → AI 추천이 얼마나 맞았나
    # 룰렛은 운으로 정한 것이라 빼고, AI 추천 화면(오늘은 이거예요 / One More Think!)에서 고른 것만 세어 비율 계산
    ai_rows = [r for r in rows if r["source"] in ("decide", "onemore")]
    ai_hits = sum(1 for r in ai_rows if r["source"] == "decide")

    return {
        "total": len(rows),
        "top_menus": [{"name": n, "count": c, "emoji": MENU_BY_ID.get(n, {}).get("emoji", "🍽️")}
                      for n, c in menu_count.most_common(3)],
        "top_kinds": [{"name": n, "count": c} for n, c in kind_count.most_common(3)],
        "top_meals": [{"name": n, "count": c} for n, c in meal_count.most_common(4)],
        "ai_hit_rate": round(ai_hits / len(ai_rows) * 100) if ai_rows else 0,
        "items": [
            {
                # isoformat() : 날짜시간을 "2026-10-01T12:30:00+00:00" 같은 표준 문자열로 → 브라우저가 한국 시간으로 바꿔 보여 줌
                "decided_at": r["decided_at"].isoformat(),
                "menu": r["menu"], "emoji": r["emoji"], "source": r["source"],
                "meal": r["meal"], "mood": r["mood"], "people": r["people"],
            }
            for r in rows
        ],
    }


def personal_weights(user_id):
    """기록으로 "개인 취향 태그 점수"를 계산합니다.

    방법: 최근 결정한 메뉴들에서 각 태그가 나온 "비율"을 구해서 점수로 바꿈
      예) 10번 중 7번이 국물 메뉴 → 국물 = 0.7 × PERSONAL_MAX = 1.4점
    비율을 쓰는 이유: 기록이 많은 사람이라고 점수가 끝없이 커지지 않게 (0 ~ PERSONAL_MAX 사이)
    """
    rows = _recent(user_id)
    if len(rows) < PERSONAL_MIN_RECORDS:
        return {}
    tag_count = Counter()
    for r in rows:
        menu = MENU_BY_ID.get(r["menu"])
        if menu:
            tag_count.update(t for t in menu["tags"] if t not in PERSONAL_EXCLUDE)   # update : 여러 개를 한 번에 세기
    return {tag: round(count / len(rows) * PERSONAL_MAX, 2) for tag, count in tag_count.items()}


def insight_stats(user_id):
    """AI가 취향 문장을 쓸 때 줄 "사실" 묶음 (코드가 계산한 숫자만 줌 → AI가 지어내지 못하게)"""
    rec = get_records(user_id)
    weights = personal_weights(user_id)
    top_tags = sorted(
        ((t, w) for t, w in weights.items() if t not in {r["name"] for r in rec["top_kinds"]}),
        key=lambda p: p[1], reverse=True,
    )[:3]
    return {
        "total": rec["total"],
        "top_menus": [m["name"] for m in rec["top_menus"]],
        "top_kinds": [k["name"] for k in rec["top_kinds"]],
        "top_meals": [m["name"] for m in rec["top_meals"]],
        "top_tags": [t for t, _ in top_tags],
        "ai_hit_rate": rec["ai_hit_rate"],
    }
