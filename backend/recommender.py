# =============================================================================
# recommender.py - 추천 로직 (음식 성향 분석 + 메뉴 고르기)
#
# 핵심 아이디어: "태그 점수표"
#   1) 태그마다 점수를 매깁니다.  예) {"국물": +3.5, "매움": +2.0, "차가움": -0.7, ...}
#   2) 점수는 아래에서 옵니다.
#      - 독립변수(출발점): 기분, 인원수, 계절, 요일   → 처음부터 점수를 조금 줌
#      - 클릭 반응: 끌린 메뉴의 태그는 +, 넘긴 메뉴의 태그는 -
#   3) 메뉴 점수 = 그 메뉴가 가진 태그 점수의 합 + 식사 시간/재료 보너스
#   4) 점수가 높은 메뉴를 보여 줍니다.
#   이 태그 점수표가 곧 "그 사람의 오늘 음식 성향" 입니다.
#
#   ※ 분석 결과(성향)는 화면에 보여 주지 않고, "다음에 어떤 메뉴를 보여 줄지" 고르는 데만 씁니다.
#     "당신은 ○○ 상태예요" 라고 말하면 분석당하는 느낌이 들기 때문입니다.
#
# 이런 방식을 "콘텐츠 기반 추천" 이라고 부릅니다.
# (메뉴의 내용(특징)을 보고, 사용자가 좋아한 것과 비슷한 것을 추천하는 방식)
#
# AI(LLM)를 쓰지 않고 단순 계산만 하므로 응답이 즉시(0.01초 수준) 나옵니다.
# =============================================================================

import random                        # 같은 조건이어도 매번 조금씩 다른 메뉴가 나오게 하는 "무작위 양념"용
from collections import defaultdict  # 없는 키를 꺼내면 자동으로 0(기본값)을 만들어 주는 딕셔너리

from menus import CATEGORIES, MENU_BY_ID, MENUS  # 같은 폴더의 menus.py 에서 데이터 가져오기


# =============================================================================
# 조절 가능한 숫자들 (튜닝 값)
# 추천이 마음에 안 들면 아래 숫자만 바꿔 보세요. 로직을 고치지 않아도 성격이 바뀝니다.
# 이름을 대문자로 쓰는 건 "바꾸지 않는 상수" 라는 파이썬의 관습입니다.
# =============================================================================

ROUND_SIZE = 5              # 한 화면에 보여 줄 메뉴 개수 (선택 과부하를 피하려고 5개)

LIKE_WEIGHT = 1.5           # 끌려서 클릭한 메뉴의 태그에 더할 점수 (강한 신호)
SKIP_WEIGHT = -0.7          # 보고도 안 누른 메뉴의 태그에 더할 점수 (약한 신호라 작게)
                            #  → 안 누른 이유가 "싫어서"가 아니라 "그냥 덜 끌려서"일 수 있기 때문

MEAL_MATCH = 2.0            # 고른 식사 시간에 어울리는 메뉴 보너스
MEAL_MISMATCH = -5.0        # 어울리지 않는 메뉴 감점 (아침에 삼겹살 X) - 크게 줘서 거의 안 나오게
INGREDIENT_MATCH = 5.0      # 사용자가 적은 재료가 들어간 메뉴 보너스 (직접 말한 거라 아주 강하게)

NOISE = 0.8                 # 무작위 양념의 크기 (0 이면 항상 똑같은 결과)

# 같은 종류(한식, 중식 등)가 한 화면에 몰리지 않게 하는 감점.
# 처음(아직 클릭 정보가 없을 때)엔 크게 → 다양하게 보여 주고,
# 클릭이 쌓이면 작게 → 사용자가 고른 쪽으로 좁혀지게 둡니다.
DIVERSITY_PENALTY_FIRST = 1.5
DIVERSITY_PENALTY_LATER = 0.5

# ---- 독립변수 → 태그 점수 변환표 ----
# "이 기분일 땐 이런 특징이 당길 것이다" 라는 가설입니다. 정답이 아니라 출발점일 뿐이고,
# 실제 취향은 클릭 반응으로 바로잡아 갑니다.
MOOD_WEIGHTS = {
    "피곤":     {"든든": 2.0, "고기": 1.5, "국물": 1.0},           # 기운 나는 것
    "스트레스": {"매움": 2.5, "기름짐": 1.0},                       # 자극적인 것
    "우울":     {"따뜻함": 1.5, "달달": 2.0, "국물": 1.0},          # 위로가 되는 것
    "좋음":     {"특별함": 2.0, "나눠먹기": 0.5},                   # 기분 내는 것
    "보통":     {},                                                  # 영향 없음
}

PEOPLE_WEIGHTS = {
    "혼자":   {"혼밥": 2.0, "나눠먹기": -1.0},
    "2명":    {},
    "3~4명":  {"나눠먹기": 2.0},
    "5명 이상": {"나눠먹기": 3.0, "혼밥": -1.5},
}

# 성향 태그 목록(profile)에서 뺄 태그. 인원수에서 온 "상황" 정보라서 입맛(취향)과는 다르기 때문.
PROFILE_EXCLUDE = {"혼밥", "나눠먹기"}


# =============================================================================
# 1) 태그 점수표 만들기 - 이 프로그램의 "심리 분석" 부분
# =============================================================================

def build_tag_weights(req):
    """모든 정보(독립변수 + 클릭 반응)를 모아서 태그 점수표를 만듭니다.

    req: main.py 의 RecommendRequest (사용자가 고른 것 + 지금까지의 클릭 기록)
    반환: {"태그": 점수} 딕셔너리
    """
    # defaultdict(float): 없는 태그를 꺼내면 0.0 으로 시작 → weights["국물"] += 1 을 바로 쓸 수 있음
    weights = defaultdict(float)

    # ---- 독립변수 1: 기분 ----
    # .get(키, {}) : 기분을 안 골랐으면(None) 빈 딕셔너리 → 아무 영향 없음
    for tag, value in MOOD_WEIGHTS.get(req.mood, {}).items():
        weights[tag] += value

    # ---- 독립변수 2: 인원수 ----
    for tag, value in PEOPLE_WEIGHTS.get(req.people, {}).items():
        weights[tag] += value

    # ---- 독립변수 3: 계절 (브라우저가 보낸 월: 1~12) ----
    if req.month in (6, 7, 8):        # 여름
        weights["차가움"] += 1.5
        weights["따뜻함"] -= 0.5
    elif req.month in (12, 1, 2):     # 겨울
        weights["따뜻함"] += 1.5
        weights["국물"] += 0.5

    # ---- 독립변수 4: 요일 (0=일요일 ... 5=금요일, 6=토요일) ----
    if req.weekday in (5, 6):         # 금요일, 토요일은 기분 내는 날
        weights["특별함"] += 1.0

    # ---- 클릭 반응: 끌린 메뉴 / 넘긴 메뉴 ----
    liked_ids = set(req.liked)
    # 넘긴 메뉴 = 보여 줬던 메뉴 중에서 클릭하지 않은 것
    # 집합의 빼기(-) 연산: A - B = A에는 있고 B에는 없는 것
    skipped_ids = set(req.shown) - liked_ids

    for menu_id in liked_ids:
        if menu_id in MENU_BY_ID:                 # 혹시 이상한 id 가 와도 에러 나지 않게 확인
            for tag in MENU_BY_ID[menu_id]["tags"]:
                weights[tag] += LIKE_WEIGHT

    for menu_id in skipped_ids:
        if menu_id in MENU_BY_ID:
            for tag in MENU_BY_ID[menu_id]["tags"]:
                weights[tag] += SKIP_WEIGHT

    return weights


# =============================================================================
# 2) 메뉴 하나의 점수 계산
# =============================================================================

def ingredient_matches(menu, text):
    """사용자가 적은 재료가 이 메뉴에 들어가는지 확인합니다.

    예) text="고기 계란" → 단어별로 나눠서 "고기" 가 "돼지고기" 안에 있는지 등을 확인
    """
    if not text:
        return False
    # 쉼표도 띄어쓰기처럼 취급한 뒤 단어별로 나눔.  "돼지고기, 김치" → ["돼지고기", "김치"]
    words = text.replace(",", " ").split()
    for word in words:
        if word in menu["name"]:          # 메뉴 이름에 들어 있으면 (예: "김치" → 김치찌개)
            return True
        for ingredient in menu["ingredients"]:
            # 양쪽 방향으로 포함 확인: "고기" in "돼지고기" / "돼지고기" in "돼지고기볶음"
            if word in ingredient or ingredient in word:
                return True
    return False


def score_menu(menu, weights, req):
    """메뉴 하나의 점수 = 태그 점수의 합 + 식사 시간 보너스 + 재료 보너스"""
    # sum(... for ...) : 메뉴의 태그마다 점수를 꺼내서 모두 더함 (제너레이터 표현식)
    score = sum(weights[tag] for tag in menu["tags"])

    # 식사 시간이 어울리면 +, 아니면 크게 - (사용자가 고르지 않았으면 영향 없음)
    if req.meal:
        score += MEAL_MATCH if req.meal in menu["meals"] else MEAL_MISMATCH

    # 사용자가 직접 적은 재료가 들어가면 큰 보너스
    if ingredient_matches(menu, req.ingredient):
        score += INGREDIENT_MATCH

    return score


def category_of(menu):
    """메뉴의 종류 태그(한식/중식/...)를 찾아 돌려줍니다."""
    # next(제너레이터, 기본값) : 조건에 맞는 첫 번째 값을 꺼냄. 없으면 기본값 "기타"
    return next((tag for tag in menu["tags"] if tag in CATEGORIES), "기타")


# =============================================================================
# 3) 결과를 브라우저로 보낼 모양으로 정리
# =============================================================================

def top_tags(weights, limit=3):
    """점수가 높은(양수인) 태그를 높은 순서로 limit 개 돌려줍니다. = 오늘의 성향 (개발 확인용)"""
    positive = [(tag, value) for tag, value in weights.items()
                if value > 0 and tag not in PROFILE_EXCLUDE]
    # sort(key=점수, reverse=True) : 점수가 큰 것부터 정렬
    positive.sort(key=lambda pair: pair[1], reverse=True)
    return [tag for tag, _ in positive[:limit]]


def to_output(menu):
    """메뉴 데이터를 브라우저로 보낼 모양으로 바꿉니다. (화면에 필요한 것만)"""
    return {
        "id": menu["id"],
        "name": menu["name"],
        "emoji": menu["emoji"],
        "tags": menu["tags"],
    }


# =============================================================================
# 4) 외부(main.py)에서 부르는 함수
# =============================================================================

def next_round(req):
    """다음 라운드에 보여 줄 메뉴 5개를 고릅니다.

    - req.keep 에 있는 메뉴(이번에 끌려서 클릭한 것)는 그대로 남깁니다.
    - 빈자리는 아직 안 보여 준 메뉴 중에서 점수가 높은 것으로 채웁니다.
    - 한 번 넘긴 메뉴는 다시 나오지 않습니다.
    """
    weights = build_tag_weights(req)

    # 남길 메뉴 (최대 5개). 리스트 컴프리헨션 + 조건(if)으로 올바른 id 만 걸러냄
    picked = [MENU_BY_ID[i] for i in req.keep if i in MENU_BY_ID][:ROUND_SIZE]

    # 후보 = 지금까지 한 번도 안 보여 준 메뉴
    excluded = set(req.shown) | set(req.keep)   # 집합의 합(|) 연산
    candidates = [m for m in MENUS if m["id"] not in excluded]

    # 후보마다 점수 계산 (+ 무작위 양념 조금)
    # 결과 모양: [(점수, 메뉴), (점수, 메뉴), ...]
    scored = [(score_menu(m, weights, req) + random.uniform(0, NOISE), m) for m in candidates]

    # 클릭 정보가 없을 땐 다양하게, 있으면 좁혀지게
    penalty = DIVERSITY_PENALTY_FIRST if not req.liked else DIVERSITY_PENALTY_LATER

    # 빈자리를 하나씩 채움 (탐욕 알고리즘: 매번 "지금 가장 좋아 보이는 것"을 고름)
    while len(picked) < ROUND_SIZE and scored:
        used = [category_of(m) for m in picked]   # 이미 고른 메뉴들의 종류

        # 같은 종류가 이미 많을수록 감점해서 최고점 후보를 찾음
        def adjusted(pair):
            score, menu = pair
            return score - penalty * used.count(category_of(menu))

        best_index = max(range(len(scored)), key=lambda i: adjusted(scored[i]))
        # pop(index) : 리스트에서 꺼내면서 삭제 → 같은 메뉴를 두 번 고르지 않음
        picked.append(scored.pop(best_index)[1])

    return {
        "menus": [to_output(m) for m in picked],
        "profile": top_tags(weights),   # 지금까지 파악한 성향 (화면엔 안 보여 줌, 개발 확인용)
    }
