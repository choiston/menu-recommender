# =============================================================================
# keywords.py - 키워드 검색 (사용자가 적은 말을 이해해서 메뉴 찾기)          버전: test 3.2
#
# test 3.1 까지는 "필수 재료"라서 메뉴의 "재료 이름"만 찾았어요. → "국물", "매운", "일식" 같은 말은 못 찾음
# test 3.2 부터는 "키워드"라서 아래를 모두 찾아요.
#   - 종류      : "일식", "중국 음식" → 중식
#   - 특징표    : "매운 것", "국물", "안주" → 매움 / 국물 / 안주 태그
#   - 메뉴 이름 : "국밥" → 국밥, 순대국밥, 돼지국밥 ...
#   - 주재료    : "돼지고기", "새우"
#
# 동작 순서 (예: "매운 국물")
#   ① 단어로 나누기            "매운", "국물"
#   ② 비슷한 말 사전으로 이해   "매운" → [특징] 매움, "국물" → [특징] 국물
#   ③ 메뉴 찾기               둘 다 맞는 메뉴(AND) → 없으면 하나라도 맞는 메뉴(OR) → 그래도 없으면 전체 + 안내
#
# 결과가 0개라서 화면이 멈춘 것처럼 보이던 문제(test 3.1)를 막으려고,
# 아무것도 안 맞으면 "전체에서 보여 드려요" 안내와 함께 일반 추천으로 진행합니다.
# =============================================================================

import re
from functools import lru_cache   # 같은 키워드를 여러 번 해석하지 않도록 결과를 기억해 두는 도구 (캐시)

from menus import MENUS

# ---- 비슷한 말 사전 ----
# (종류 또는 특징, 그 뜻으로 알아들을 말들)
# 사람들은 "매움"이라고 쓰지 않고 "매운", "매콤한", "얼큰한"이라고 써요 → 여러 표현을 하나의 뜻으로 모음
KIND_ALIASES = {
    "한식": ["한식", "한국"],
    "중식": ["중식", "중국", "중화", "짱깨"],
    "일식": ["일식", "일본"],
    "양식": ["양식", "서양"],
    "분식": ["분식"],
    "아시안": ["아시안", "동남아", "베트남", "태국"],
    "패스트푸드": ["패스트푸드", "패스트", "정크"],
    "멕시칸": ["멕시칸", "멕시코"],
    "인도·중동": ["인도", "중동"],
    "브런치·카페": ["브런치", "카페", "디저트"],
}
TAG_ALIASES = {
    "매움": ["매운", "매콤", "맵", "얼큰", "칼칼", "화끈"],
    "국물": ["국물", "찌개", "전골", "국", "탕"],
    "차가움": ["시원", "차가운", "차갑", "찬 ", "냉"],
    "따뜻함": ["따뜻", "따끈", "뜨끈", "뜨거운"],
    "든든": ["든든", "배부른", "푸짐", "배고파", "배고픈"],
    "가벼움": ["가벼운", "가볍", "간단", "다이어트", "라이트"],
    "달달": ["달달", "달콤", "단것", "단거", "달다"],
    "담백": ["담백", "순한", "깔끔", "슴슴"],
    "기름짐": ["기름진", "기름", "느끼", "튀김", "바삭"],
    "고기": ["고기", "육류", "육식"],
    "면": ["면", "국수", "누들", "면요리"],
    "밥": ["밥", "덮밥", "밥류"],
    "빵": ["빵"],
    "안주": ["안주", "술", "맥주", "소주", "막걸리"],
    "간편식": ["간편", "빨리", "후딱", "포장"],
    "특별함": ["특별", "기념", "데이트", "외식"],
    "나눠먹기": ["여럿", "같이", "파티", "회식"],
}

# 뜻이 없는 말 (빼고 생각함): "매운 것", "국물 요리", "면 먹고 싶어" 의 "것", "요리", "먹고 싶어"
STOPWORDS = ["먹고싶어", "먹고싶다", "먹고", "싶어", "싶다", "음식", "요리", "메뉴", "종류",
             "것", "거", "걸", "류", "좀", "한", "있는", "들어간", "으로", "로"]


def _aliases():
    """(별명, 종류) 목록을 "긴 별명부터" 정렬. 짧은 말이 먼저 잘못 걸리지 않게
    예) "중국"을 먼저 처리해야 "국" → 국물 로 잘못 알아듣지 않음
    """
    pairs = [(a, ("kind", k)) for k, al in KIND_ALIASES.items() for a in al]
    pairs += [(a.strip(), ("tag", t)) for t, al in TAG_ALIASES.items() for a in al]
    return sorted(pairs, key=lambda p: len(p[0]), reverse=True)


ALIASES = _aliases()


@lru_cache(maxsize=256)
def parse(text):
    """키워드 글자 → 뜻(조건) 목록.  예) "매운 국물, 돼지고기" → (("tag","매움"), ("tag","국물"), ("text","돼지고기"))

    반환을 튜플로 하는 이유: lru_cache 로 기억하려면 바꿀 수 없는 값(튜플)이어야 함
    """
    terms = []
    for word in re.split(r"[\s,]+", text or ""):    # 띄어쓰기, 쉼표로 나눔
        if not word:
            continue
        # ⓪ 단어 자체가 사전의 말이면 그 뜻으로 ("면", "국물", "일식")
        exact = next((meaning for alias, meaning in ALIASES if alias == word), None)
        if exact:
            if exact not in terms:
                terms.append(exact)
            continue
        # ⓪ 단어가 메뉴 이름 안에 그대로 있으면 이름으로 찾기 ("국밥" 을 "국(국물) + 밥" 으로 잘못 쪼개지 않게)
        if len(word) >= 2 and any(word in m["name"] for m in MENUS):
            if ("text", word) not in terms:
                terms.append(("text", word))
            continue
        rest = word
        # ① 사전에 있는 말을 찾을 때마다 그 부분을 지우고 뜻을 기록 ("매운국물" 처럼 붙여 써도 둘 다 찾음)
        for alias, meaning in ALIASES:
            if alias in rest:
                if meaning not in terms:
                    terms.append(meaning)
                rest = rest.replace(alias, " ")
        # ② 뜻 없는 말 지우기
        for stop in STOPWORDS:
            rest = rest.replace(stop, " ")
        # ③ 남은 글자(2글자 이상)는 메뉴 이름이나 재료에서 그대로 찾음  예) "돼지고기", "새우", "국밥"
        for leftover in rest.split():
            if len(leftover) >= 2 and ("text", leftover) not in terms:
                terms.append(("text", leftover))
    return tuple(terms)


def matches(menu, term):
    """메뉴 하나가 조건 하나에 맞는지"""
    kind, value = term
    if kind == "kind":
        return menu["tags"][0] == value              # 종류는 tags 의 맨 앞
    if kind == "tag":
        return value in menu["tags"]
    # text : 메뉴 이름에 들어 있거나, 주재료와 서로 포함 관계 ("고기" ↔ "돼지고기")
    if value in menu["name"]:
        return True
    return any(value in ing or ing in value for ing in menu["ingredients"])


@lru_cache(maxsize=256)
def plan(text):
    """키워드를 어떻게 적용할지 정합니다. (전체 메뉴 기준으로 한 번만 정해야 화면마다 기준이 흔들리지 않음)

    반환: (mode, terms, notice)
      mode = "none" : 키워드 없음 → 걸러내지 않음
             "and"  : 모든 조건에 맞는 메뉴만
             "or"   : 하나라도 맞는 메뉴만 (모두 맞는 메뉴가 없을 때)
             "all"  : 아무것도 안 맞음 → 걸러내지 않고 안내만
    """
    terms = parse(text)
    if not text or not terms:
        return ("none", terms, f"'{text}'을(를) 이해하지 못해서 전체에서 보여 드려요." if text and text.strip() else None)
    if any(all(matches(m, t) for t in terms) for m in MENUS):
        return ("and", terms, None)
    if len(terms) > 1 and any(any(matches(m, t) for t in terms) for m in MENUS):
        return ("or", terms, f"'{text}'에 모두 맞는 메뉴가 없어서, 하나라도 맞는 메뉴로 보여 드려요.")
    return ("all", terms, f"'{text}'에 맞는 메뉴가 없어서 전체에서 보여 드려요.")


def keep(menu, text):
    """이 메뉴가 키워드 조건을 통과하는지 (걸러내기용)"""
    mode, terms, _ = plan(text)
    if mode == "and":
        return all(matches(menu, t) for t in terms)
    if mode == "or":
        return any(matches(menu, t) for t in terms)
    return True   # none / all : 걸러내지 않음


def hits(menu, text):
    """메뉴가 맞춘 조건 개수 (OR 모드에서 더 많이 맞는 메뉴를 앞에 두려고 점수에 사용)"""
    _, terms, _ = plan(text)
    return sum(1 for t in terms if matches(menu, t))


def describe(text):
    """키워드를 어떻게 이해했는지 사람이 읽을 수 있게.  예) "매움 · 국물 · '돼지고기'" (개발 확인용)"""
    names = {"kind": "", "tag": "", "text": "'"}
    return " · ".join(f"{names[k]}{v}{names[k]}" for k, v in parse(text))
