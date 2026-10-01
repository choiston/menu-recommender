# =============================================================================
# recommender.py - 추천 로직                                     버전: test 3.2
#
# [test 3.0 에서 바뀐 것]
#   - 개인 취향(personal): 로그인한 사람은 지난 결정 기록으로 계산한 취향 점수가 더해짐 (records.personal_weights)
#     · 취향 감옥 방지: 1라운드 5개 중 마지막 1개는 취향을 빼고 고름 → 새로운 발견의 자리
#   - 다른 방향 보기: 가 본 종류를 모두 기억(explored_kinds)하고, 한 화면 = 서로 다른 종류 5개 (종류마다 1개)
#     · 다른 방향에서는 이전 선택과 개인 취향의 영향을 절반으로 줄임 → 진짜 "다른" 방향
#   - 새 특징표: "안주"(야식 시간에 +), "간편식"(혼자일 때 +)
#
# [test 3.1] 룰렛(roulette): 시작 화면 입력(+개인 취향)에 맞춘 메뉴 10칸 + 당첨 메뉴를 서버가 미리 정함
#
# test 2.0 의 핵심: "고른 메뉴를 따라 깊이 들어가기"
#
#   [1라운드]  큰 분류 메뉴 5개 (broad=true)        ← 독립변수(기분, 인원 등)로 고름
#        ↓ 국밥 선택
#   [2라운드]  국밥의 관련 메뉴 (돼지국밥, 순대국밥, 소머리국밥 ...)   ← menus.json 의 related
#        ↓ 순대국밥 선택
#   [3라운드]  순대국밥의 관련 메뉴 (순대, 순대볶음, 뼈해장국 ...)
#        ↓ ...
#
#   - 여러 개를 고르면: 각 메뉴의 관련 메뉴를 번갈아 하나씩 섞어서 보여 줌
#   - 아무것도 안 고르거나 [다른 방향 보기]: 지금과 다른 종류의 큰 분류 메뉴를 보여 줌
#   - 키워드를 적었으면: 키워드에 맞는 메뉴만 후보가 됨 (filter_required → keywords.py, test 3.2)
#
# 결과 화면 (test 2.1):
#   - decide()   : 고른 메뉴 중 처음 입력에 가장 잘 맞는 하나 → "오늘은 이거예요!"
#   - one_more() : [🤔 원 모어 띵크] 고른 메뉴 밖에서 하나 더 추천 (처음엔 가깝게, 누를수록 멀리)
#   - 추천 한 줄 코멘트는 ai_comment.py 가 AI(Ollama)로 작성
#
# 그럼 test 1.0 의 "태그 점수표"는? → 여전히 씁니다. 다만 역할이 바뀌었어요.
#   - test 1.0 : 무엇을 보여 줄지 "직접" 결정
#   - test 2.0 : 관련 메뉴 후보가 여러 개일 때 "어떤 순서로" 보여 줄지 정하는 데 사용
#                (예: 국밥 관련 메뉴 6개 중, 아침이면 콩나물국밥을 앞에)
#
# 분석 결과(성향)는 화면에 보여 주지 않습니다. 분석당하는 느낌을 주지 않기 위해서입니다.
# =============================================================================

import random                        # 같은 조건이어도 매번 조금씩 다른 메뉴가 나오게 하는 "무작위 양념"용
from collections import defaultdict  # 없는 키를 꺼내면 자동으로 0(기본값)을 만들어 주는 딕셔너리

import keywords                                  # [test 3.2] 키워드 이해 + 걸러내기
from menus import CATEGORIES, MENU_BY_ID, MENUS  # 같은 폴더의 menus.py 에서 데이터 가져오기


# =============================================================================
# 조절 가능한 숫자들 (튜닝 값)
# 추천이 마음에 안 들면 아래 숫자만 바꿔 보세요. 로직을 고치지 않아도 성격이 바뀝니다.
# =============================================================================

ROUND_SIZE = 5              # 한 화면에 보여 줄 메뉴 개수 (선택 과부하를 피하려고 5개)

LIKE_WEIGHT = 1.5           # 고른 메뉴의 태그에 더할 점수
SKIP_WEIGHT = -0.5          # 보고도 안 고른 메뉴의 태그에 더할 점수 (약한 신호라 작게)

MEAL_MATCH = 2.0            # 고른 식사 시간에 어울리는 메뉴 보너스
MEAL_MISMATCH = -5.0        # 어울리지 않는 메뉴 감점 (아침에 삼겹살 X)
KEYWORD_HIT = 2.0           # [test 3.2] 키워드 조건을 하나 맞출 때마다 보너스
                            #  (걸러내기를 하므로 대부분 같지만, "하나라도 맞는" 모드에선 더 많이 맞는 메뉴가 앞으로)

NOISE = 0.8                 # 무작위 양념의 크기 (0 이면 항상 똑같은 결과)
DIVERSITY_PENALTY = 1.5     # 한 화면에 같은 종류(한식, 중식 ...)가 몰리지 않게 하는 감점

# ---- 독립변수 → 태그 점수 변환표 ----
# "이 기분일 땐 이런 특징이 당길 것이다" 라는 가설(출발점)입니다.
MOOD_WEIGHTS = {
    "피곤":     {"든든": 2.0, "고기": 1.5, "국물": 1.0},           # 기운 나는 것
    "스트레스": {"매움": 2.5, "기름짐": 1.0},                       # 자극적인 것
    "우울":     {"따뜻함": 1.5, "달달": 2.0, "국물": 1.0},          # 위로가 되는 것
    "좋음":     {"특별함": 2.0, "나눠먹기": 0.5},                   # 기분 내는 것
    "보통":     {},                                                  # 영향 없음
}

PEOPLE_WEIGHTS = {
    "혼자":     {"혼밥": 2.0, "나눠먹기": -1.0},
    "2명":      {},
    "3~4명":    {"나눠먹기": 2.0},
    "5명 이상": {"나눠먹기": 3.0, "혼밥": -1.5},
}

# 성향 태그 목록(profile)에서 뺄 태그. 인원수에서 온 "상황" 정보라서 입맛(취향)과는 다르기 때문.
PROFILE_EXCLUDE = {"혼밥", "나눠먹기"}

# [test 3.0] 새 특징표 보너스
LATE_NIGHT_ANJU = 1.5       # 식사 시간이 "야식"이면 안주 메뉴 +
SOLO_QUICK = 0.5            # 혼자면 간편식 메뉴 +

# [test 3.0] 다른 방향 보기에서 이전 선택·개인 취향의 영향을 얼마나 남길지 (0.5 = 절반)
EXPLORE_FACTOR = 0.5


# =============================================================================
# 1) 태그 점수표 만들기 - "심리 분석" 부분 (화면에는 안 보임)
# =============================================================================

def build_tag_weights(req, personal=None, factor=1.0):
    """모든 정보(독립변수 + 고른 기록 + 개인 취향)를 모아서 태그 점수표를 만듭니다.

    req      : main.py 의 RecommendRequest
    personal : 로그인 사용자의 개인 취향 점수 {"국물": 1.4, ...} (로그인 안 했으면 None)
    factor   : 고른 기록과 개인 취향을 얼마나 반영할지 (1.0 = 그대로, 0.5 = 절반 → 다른 방향 보기용)
    반환: {"태그": 점수} 딕셔너리
    """
    weights = defaultdict(float)

    # ---- 독립변수: 기분, 인원수 ----
    # .get(키, {}) : 선택 안 했으면(None) 빈 딕셔너리 → 아무 영향 없음
    for tag, value in MOOD_WEIGHTS.get(req.mood, {}).items():
        weights[tag] += value
    for tag, value in PEOPLE_WEIGHTS.get(req.people, {}).items():
        weights[tag] += value

    # ---- [test 3.0] 새 특징표: 안주, 간편식 ----
    if req.meal == "야식":
        weights["안주"] += LATE_NIGHT_ANJU
    if req.people == "혼자":
        weights["간편식"] += SOLO_QUICK

    # ---- [test 3.0] 개인 취향 (로그인 사용자) ----
    for tag, value in (personal or {}).items():
        weights[tag] += value * factor

    # ---- 독립변수: 계절 (월 1~12) ----
    if req.month in (6, 7, 8):        # 여름
        weights["차가움"] += 1.5
        weights["따뜻함"] -= 0.5
    elif req.month in (12, 1, 2):     # 겨울
        weights["따뜻함"] += 1.5
        weights["국물"] += 0.5

    # ---- 독립변수: 요일 (5=금, 6=토) ----
    if req.weekday in (5, 6):
        weights["특별함"] += 1.0

    # ---- 고른 기록 ----
    liked = set(req.liked)
    skipped = set(req.shown) - liked   # 집합의 빼기: 보여 줬지만 안 고른 것
    for name in liked:
        for tag in MENU_BY_ID.get(name, {}).get("tags", []):
            weights[tag] += LIKE_WEIGHT * factor
    for name in skipped:
        for tag in MENU_BY_ID.get(name, {}).get("tags", []):
            weights[tag] += SKIP_WEIGHT * factor

    return weights


# =============================================================================
# 2) 메뉴 하나의 점수 계산
# =============================================================================

def filter_required(menus, req):
    """키워드가 있으면, 키워드에 맞는 메뉴만 남깁니다. (test 3.2: 필수 재료 → 키워드)

    어떤 기준(모두 맞음 / 하나라도 맞음 / 걸러내지 않음)으로 거를지는 keywords.plan() 이
    "전체 메뉴 기준으로 한 번" 정함 → 라운드·룰렛·One More 어디서든 같은 기준
    """
    if not req.keyword:
        return menus
    return [m for m in menus if keywords.keep(m, req.keyword)]


def required_notice(req, count):
    """키워드 관련 안내 문구 (없으면 None)
    ① 키워드를 그대로 적용하지 못했을 때(하나라도 맞음 / 전체) → 그 안내
    ② 맞는 메뉴가 화면 칸(5개)보다 적을 때 → 개수 안내
    """
    if not req.keyword:
        return None
    _, _, plan_notice = keywords.plan(req.keyword)
    if plan_notice:
        return plan_notice
    if count == 0:
        return f"'{req.keyword}'에 맞는 메뉴를 다 봤어요. 다른 방향을 보거나 [🤖 골라 줘!]를 눌러 주세요."
    if count < ROUND_SIZE:
        return f"'{req.keyword}'에 맞는 메뉴가 {count}개 더 있어요."
    return None


def score_menu(menu, weights, req, noise=True):
    """메뉴 하나의 점수 = 태그 점수의 합 + 식사 시간 보너스 + 재료 보너스 (+ 무작위 양념)"""
    score = sum(weights[tag] for tag in menu["tags"])
    if req.meal:
        score += MEAL_MATCH if req.meal in menu["meals"] else MEAL_MISMATCH
    if req.keyword:
        score += KEYWORD_HIT * keywords.hits(menu, req.keyword)
    if noise:
        score += random.uniform(0, NOISE)
    return score


def category_of(menu):
    """메뉴의 종류 태그(한식/중식/...)를 돌려줍니다."""
    return next((tag for tag in menu["tags"] if tag in CATEGORIES), "기타")


def pick_diverse(candidates, weights, req, count, already=()):
    """후보 중에서 점수 높은 순으로 count 개를 고르되, 같은 종류가 몰리지 않게 합니다.

    탐욕 알고리즘: 매번 "지금 가장 좋아 보이는 것"을 하나씩 골라 채움
    already: 이미 화면에 들어가기로 한 메뉴들 (종류 겹침 계산에 포함)
    """
    scored = [(score_menu(m, weights, req), m) for m in candidates]
    picked = []
    while len(picked) < count and scored:
        used = [category_of(m) for m in list(already) + picked]

        def adjusted(pair):
            score, menu = pair
            return score - DIVERSITY_PENALTY * used.count(category_of(menu))

        best_index = max(range(len(scored)), key=lambda i: adjusted(scored[i]))
        picked.append(scored.pop(best_index)[1])
    return picked


def top_tags(weights, limit=3):
    """점수가 높은(양수인) 태그 = 오늘의 성향. 화면엔 안 보여 주고 개발 확인용으로만 응답에 넣음"""
    positive = [(t, v) for t, v in weights.items() if v > 0 and t not in PROFILE_EXCLUDE]
    positive.sort(key=lambda pair: pair[1], reverse=True)
    return [t for t, _ in positive[:limit]]


def to_output(menu):
    """메뉴 데이터를 브라우저로 보낼 모양으로 바꿉니다. 결과 화면에 쓸 정보까지 함께 보냄"""
    return {
        "id": menu["name"],          # test 2.0 부터 이름이 곧 id
        "name": menu["name"],
        "emoji": menu["emoji"],
        "category": category_of(menu),   # [test 3.0] 종류 (다른 방향 보기에서 "가 본 종류"를 기억하는 데 사용)
        "tags": menu["tags"],
        "kcal": menu["kcal"],
        "ingredients": menu["ingredients"],
        "tips": menu["tips"],
    }


# =============================================================================
# 3) 다음 라운드 메뉴 고르기 - main.py 가 부르는 함수
# =============================================================================

def next_round(req, personal=None):
    """상황에 따라 3가지 방식 중 하나로 메뉴 5개를 고릅니다.

    - start   : 첫 화면. 큰 분류 메뉴 중에서 독립변수(+개인 취향)로 고름
    - drill   : 이번에 고른 메뉴(req.picked)의 관련 메뉴로 깊이 들어감
    - explore : [다른 방향 보기] 또는 아무것도 안 골랐을 때. 아직 안 가 본 종류의 큰 분류 메뉴
    personal  : 로그인 사용자의 개인 취향 점수 (없으면 None)
    """
    weights = build_tag_weights(req, personal)

    # 한 번 보여 줬거나 이미 고른 메뉴는 다시 나오지 않게
    excluded = set(req.shown) | set(req.liked)   # 집합의 합(|)
    # 필수 재료가 있으면 그 재료가 들어간 메뉴만 후보로 (걸러내기)
    unseen = filter_required([m for m in MENUS if m["name"] not in excluded], req)

    if not req.shown:
        mode = "start"
    elif req.mode == "explore" or not req.picked:
        mode = "explore"
    else:
        mode = "drill"

    picked = []

    if mode == "start":
        broad = [m for m in unseen if m["broad"]]
        if personal:
            # [test 3.0] 취향 감옥 방지: 4개는 개인 취향을 반영해서 고르고,
            # 마지막 1개는 개인 취향을 뺀 점수로 고름 → 늘 먹던 것만 나오지 않게 "새로운 발견"의 자리를 남겨 둠
            picked = pick_diverse(broad, weights, req, ROUND_SIZE - 1)
            fresh = [m for m in broad if m not in picked]
            picked += pick_diverse(fresh, build_tag_weights(req), req, 1, already=picked)
        else:
            picked = pick_diverse(broad, weights, req, ROUND_SIZE)
        # 필수 재료 때문에 큰 분류 메뉴가 모자라면 세부 메뉴에서도 채움
        if len(picked) < ROUND_SIZE:
            rest = [m for m in unseen if m not in picked]
            picked += pick_diverse(rest, weights, req, ROUND_SIZE - len(picked), already=picked)

    elif mode == "drill":
        # ① 고른 메뉴마다 "관련 메뉴 줄"을 만들고, 각 줄은 점수 높은 순으로 정렬
        #    예) 국밥 → [순대국밥, 돼지국밥, 콩나물국밥, ...]
        #        라멘 → [돈코츠라멘, 미소라멘, 우동, ...]
        lines = []
        for name in req.picked:
            menu = MENU_BY_ID.get(name)
            if not menu:
                continue
            related = filter_required([MENU_BY_ID[r] for r in menu["related"] if r not in excluded], req)
            related.sort(key=lambda m: score_menu(m, weights, req), reverse=True)
            lines.append(related)

        # ② 줄마다 하나씩 번갈아 뽑기 (라운드 로빈) → 여러 개 골랐을 때 골고루 섞임
        #    국밥줄 1번 → 라멘줄 1번 → 국밥줄 2번 → 라멘줄 2번 → ...
        depth = 0
        while len(picked) < ROUND_SIZE and any(depth < len(line) for line in lines):
            for line in lines:
                if depth < len(line) and line[depth] not in picked and len(picked) < ROUND_SIZE:
                    picked.append(line[depth])
            depth += 1

        # ③ 관련 메뉴가 5개가 안 되면 "관련 메뉴의 관련 메뉴"(2단계 연결)로 채움
        #    예) 순대국밥 → 관련: 돼지국밥(이미 봄) → 돼지국밥의 관련: 밀면, 수육 ...
        #    이렇게 하면 빈자리에도 엉뚱한 메뉴가 아니라 "가까운" 메뉴가 들어감
        if len(picked) < ROUND_SIZE:
            second = []
            for name in req.picked:
                for r in MENU_BY_ID.get(name, {}).get("related", []):
                    for r2 in MENU_BY_ID[r]["related"]:
                        menu2 = MENU_BY_ID[r2]
                        if r2 not in excluded and menu2 not in picked and menu2 not in second:
                            second.append(menu2)
            second = filter_required(second, req)
            second.sort(key=lambda m: score_menu(m, weights, req), reverse=True)
            picked += second[:ROUND_SIZE - len(picked)]

        # ④ 그래도 모자라면, 아직 안 본 메뉴 중 점수(=지금까지의 성향) 높은 것으로 채움
        if len(picked) < ROUND_SIZE:
            rest = [m for m in unseen if m not in picked]
            rest.sort(key=lambda m: score_menu(m, weights, req), reverse=True)
            picked += rest[:ROUND_SIZE - len(picked)]

    else:  # explore
        picked = explore(req, personal, unseen)

    return {
        "menus": [to_output(m) for m in picked],
        "mode": mode,                 # 어떤 방식으로 골랐는지 (개발 확인용)
        "profile": top_tags(weights), # 지금까지 파악한 성향 (화면엔 안 보여 줌, 개발 확인용)
        "notice": required_notice(req, len(picked)),  # 키워드 안내 (없으면 None)
    }


def explore(req, personal, unseen):
    """[test 3.0] 🔀 다른 방향 보기: 아직 안 가 본 종류에서 1개씩, 서로 다른 종류 5개를 보여 줍니다.

    피하는 종류 = 바로 전 화면의 종류 + 지금까지 다른 방향에서 이미 보여 준 종류(req.explored_kinds)
    → 한식 → (중식, 일식, 분식, 양식, 멕시칸) → (아시안, 인도·중동, 패스트푸드, 브런치·카페 …) 처럼 돌아감
    가 볼 종류가 5개보다 적어지면, 기억을 지우고 "바로 전 화면의 종류"만 피해서 처음부터 다시 돎

    이전 선택과 개인 취향의 영향은 절반(EXPLORE_FACTOR)만 → 진짜 "다른" 방향이 되도록
    """
    weights = build_tag_weights(req, personal, factor=EXPLORE_FACTOR)
    broad = [m for m in unseen if m["broad"]]
    last_kinds = {category_of(MENU_BY_ID[n]) for n in req.current if n in MENU_BY_ID}

    def kinds_available(avoid):
        # 피할 종류를 뺀 나머지 중, 아직 보여 줄 메뉴가 남아 있는 종류들
        return [k for k in CATEGORIES if k not in avoid and any(category_of(m) == k for m in broad)]

    kinds = kinds_available(last_kinds | set(req.explored_kinds))
    if len(kinds) < ROUND_SIZE:
        kinds = kinds_available(last_kinds)          # 한 바퀴 다 돌았으면 기억을 지우고 다시

    # 종류마다 "그 종류에서 가장 점수 높은 메뉴" 하나씩 → 그중 점수 높은 5개 종류를 고름
    best_per_kind = []
    for k in kinds:
        menus_k = [m for m in broad if category_of(m) == k]
        best = max(menus_k, key=lambda m: score_menu(m, weights, req))
        best_per_kind.append(best)
    best_per_kind.sort(key=lambda m: score_menu(m, weights, req, noise=False), reverse=True)
    picked = best_per_kind[:ROUND_SIZE]

    # 그래도 모자라면(필수 재료로 많이 걸러졌을 때 등) 남은 메뉴로 채움
    if len(picked) < ROUND_SIZE:
        rest = [m for m in unseen if m not in picked]
        picked += pick_diverse(rest, weights, req, ROUND_SIZE - len(picked), already=picked)
    return picked


# =============================================================================
# 4) 결과 화면 - AI가 하나 고르기 / One More Think!
# =============================================================================

def decide(req, personal=None):
    """사용자가 고른 메뉴(req.liked) 중에서 처음 입력(식사 시간, 기분, 인원, 재료)에
    가장 잘 맞는 메뉴 하나를 고릅니다. → 결과 화면의 "오늘은 이거예요!"

    고른 메뉴가 1개면 그 메뉴를 그대로 돌려줍니다.
    로그인 사용자는 개인 취향도 함께 반영합니다.
    """
    weights = build_tag_weights(req, personal)
    candidates = [MENU_BY_ID[n] for n in req.liked if n in MENU_BY_ID]
    if not candidates:
        return {"menu": None, "notice": "고른 메뉴가 없어요."}

    # enumerate : (순서번호, 값) 을 함께 꺼냄
    # 점수가 같으면 나중에 고른 메뉴(더 깊이 들어간 메뉴)가 이기도록 순서번호 × 0.01 을 더함
    best = max(
        enumerate(candidates),
        key=lambda pair: score_menu(pair[1], weights, req, noise=False) + pair[0] * 0.01,
    )[1]
    return {"menu": to_output(best), "notice": None}


def one_more(req, personal=None):
    """[🤔 One More Think!] : 고른 메뉴 밖에서 다른 음식을 하나 추천합니다. (로그인 사용자는 개인 취향 반영)

    처음엔 가깝게, 누를수록 멀리:
      - 1~2번째 (req.recommended 가 0~1개) : 고른 메뉴와 "가까운" 메뉴 (관련 메뉴 → 2단계 연결)
      - 3번째부터                           : 고른 메뉴와 "다른 종류"의 메뉴 (기분 전환)
    """
    weights = build_tag_weights(req, personal)
    liked = [MENU_BY_ID[n] for n in req.liked if n in MENU_BY_ID]
    excluded = set(req.liked) | set(req.recommended)   # 고른 것, 이미 추천한 것은 제외
    seen = set(req.shown)

    def rank(menus):
        # 정렬 기준: ① 아직 화면에서 못 본 메뉴 먼저 (새로운 발견) ② 점수 높은 순
        # sort 의 key 에 튜플을 주면 첫 번째 값으로 먼저 비교하고, 같으면 두 번째 값으로 비교
        return sorted(menus, key=lambda m: (m["name"] in seen, -score_menu(m, weights, req, noise=False)))

    candidate = None

    if len(req.recommended) < 2:
        # ---- 가까운 메뉴: 관련 메뉴 → 없으면 2단계 연결 ----
        near = []
        for m in liked:
            for r in m["related"]:
                if r not in excluded and MENU_BY_ID[r] not in near:
                    near.append(MENU_BY_ID[r])
        near = filter_required(near, req)
        if not near:
            for m in liked:
                for r in m["related"]:
                    for r2 in MENU_BY_ID[r]["related"]:
                        if r2 not in excluded and MENU_BY_ID[r2] not in near:
                            near.append(MENU_BY_ID[r2])
            near = filter_required(near, req)
        if near:
            candidate = rank(near)[0]

    if candidate is None:
        # ---- 다른 종류의 메뉴: 고른 메뉴와 이미 추천한 메뉴의 종류(한식, 중식 ...)는 피함 ----
        used_kinds = {category_of(m) for m in liked}
        used_kinds |= {category_of(MENU_BY_ID[n]) for n in req.recommended if n in MENU_BY_ID}
        pool = filter_required([m for m in MENUS if m["name"] not in excluded], req)
        far = [m for m in pool if m["broad"] and category_of(m) not in used_kinds]
        # 다른 종류가 다 떨어지면, 아무 메뉴 중 점수 높은 것
        candidate = (rank(far) or rank(pool) or [None])[0]

    if candidate is None:
        return {"menu": None, "notice": "더 추천할 메뉴가 없어요. 처음부터 다시 해 보세요!"}
    return {"menu": to_output(candidate), "notice": None}


# =============================================================================
# 5) [test 3.1] 🎰 룰렛
# =============================================================================

ROULETTE_SIZE = 10          # 룰렛 칸 수 (휴대폰에서도 메뉴 이름이 읽히는 정도)


def roulette(req, personal=None):
    """룰렛 칸에 들어갈 메뉴들과 당첨 메뉴를 정합니다.

    겉보기엔 "운명의 룰렛"이지만, 칸에 들어가는 메뉴는 시작 화면 입력(식사 시간, 기분, 인원, 필수 재료)과
    로그인 사용자의 개인 취향에 맞춰 고릅니다 → 아무거나 나와도 "오, 괜찮은데?" 가 되도록.

    두 가지 쓰임:
      ① 시작 화면 룰렛      : req.candidates 가 비어 있음 → 서버가 10개를 고름 (종류는 다양하게)
      ② 결과 화면 룰렛      : req.candidates = 내가 고른 메뉴들 → 그 메뉴들로만 칸을 만듦
    당첨은 칸들 중에서 "똑같은 확률"로 뽑음 (random.choice) → 룰렛은 공정해야 하니까
      · 칸에 들어가는 메뉴는 이미 나에게 맞춘 것이라, 당첨은 운에 맡겨도 괜찮음
      · req.avoid : [🎲 다시 돌리기] 때 바로 전 당첨 메뉴는 피함 (같은 게 또 나오면 재미없으니까)

    당첨을 서버가 "먼저" 정하고 화면은 그 칸에 멈추도록 돌림 → 화면과 결과가 절대 어긋나지 않음
    """
    if req.candidates:
        menus = [MENU_BY_ID[n] for n in req.candidates if n in MENU_BY_ID][:ROULETTE_SIZE]
    else:
        weights = build_tag_weights(req, personal)
        pool = filter_required(MENUS, req)
        broad = [m for m in pool if m["broad"]]
        # 큰 분류 메뉴 중에서 다양하게 10개. 필수 재료 때문에 모자라면 세부 메뉴도
        menus = pick_diverse(broad, weights, req, ROULETTE_SIZE)
        if len(menus) < ROULETTE_SIZE:
            rest = [m for m in pool if m not in menus]
            menus += pick_diverse(rest, weights, req, ROULETTE_SIZE - len(menus), already=menus)
        # 점수 순서대로 두면 좋은 메뉴가 한쪽에 몰려 보이니까 칸 순서는 섞음
        random.shuffle(menus)

    if len(menus) < 2:
        return {"menus": [to_output(m) for m in menus], "winner": 0 if menus else -1,
                "notice": "룰렛을 돌리려면 메뉴가 2개 이상 필요해요." + (
                    f" '{req.keyword}'에 맞는 메뉴가 적어요." if req.keyword else "")}

    # 당첨 칸 번호 고르기 (바로 전 당첨 메뉴는 빼고)
    choices = [i for i, m in enumerate(menus) if m["name"] != req.avoid] or list(range(len(menus)))
    winner = random.choice(choices)
    notice = keywords.plan(req.keyword)[2] if (req.keyword and not req.candidates) else None
    return {"menus": [to_output(m) for m in menus], "winner": winner, "notice": notice}
