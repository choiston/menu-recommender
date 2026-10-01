# =============================================================================
# ai_comment.py - AI(Ollama)가 문장을 쓰는 곳                        버전: test 3.0
#
# ① write_comment : 결과 화면의 "오늘은 이거예요!" / "One More Think!" 카드 아래 한 줄 코멘트
# ② write_insight : [test 3.0] 📒 내 기록 화면의 "AI가 본 내 취향" 문장 (로그인 사용자)
#   예) "피곤한 점심, 들깨 듬뿍 뼈해장국으로 든든하게 채워 보세요"
#
# 역할 나누기 (기획에서 정한 것):
#   - 메뉴를 "고르는" 일   → recommender.py (점수 계산, 즉시)
#   - 문장을 "쓰는" 일     → 이 파일 (AI, 10~40초)
#   → AI가 엉뚱한 메뉴를 고를 위험이 없고, 메뉴는 화면에 먼저 바로 보입니다.
#
# 안전장치:
#   AI가 너무 느리거나(시간 초과), 꺼져 있거나, 이상한 문장을 쓰면
#   "정해진 문장 틀(템플릿)"로 대신 만들어서 돌려줍니다. → AI가 실패해도 앱은 깨지지 않음
# =============================================================================

import os
import re          # 정규 표현식(regular expression): 글자 패턴을 찾는 도구. 여기선 "한글이 있는지" 검사에 사용

import httpx       # Ollama 서버에 HTTP 요청을 보내는 라이브러리

from menus import MENU_BY_ID

# Ollama 접속 정보 (main.py 와 같은 환경변수 사용)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_URL = f"{OLLAMA_HOST}/api/chat"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")

# AI 답을 최대 몇 초까지 기다릴지. 넘으면 템플릿 문장으로 대신함
# (GPU 없이 CPU로 돌리면 처음 한 번은 모델을 메모리에 올리느라 특히 느림)
AI_TIMEOUT = float(os.getenv("AI_COMMENT_TIMEOUT", "40"))

# 화면에 보여 줄 문장의 최대 길이 (너무 길면 자름)
MAX_LEN = 60

# ---- AI에게 주는 규칙 (시스템 프롬프트) ----
# 기획에서 정한 원칙을 AI에게 그대로 지시합니다.
#   - 사람을 판단하는 말 금지 ("당신은 ~한 사람이에요" X) → 분석당하는 느낌을 주지 않기
#   - 사용자가 입력한 상황(식사 시간, 기분, 인원)과 메뉴 정보만 이야기하기
#   - 짧게 (작은 AI는 길게 쓸수록 한국어가 어색해짐)
SYSTEM_PROMPT = (
    "너는 음식 추천 앱에서 메뉴 카드 아래에 들어갈 한 줄 코멘트를 쓰는 작가야.\n"
    "규칙:\n"
    "1. 자연스러운 한국어 한 문장, 40자 이내.\n"
    "2. 주어진 상황(식사 시간, 기분, 인원)과 메뉴의 특징, 재료만 이야기해.\n"
    "3. 사람의 성격이나 상태를 판단하지 마. '당신은 ~한 사람' 같은 말 금지.\n"
    "4. 칼로리, 가격, 건강 효과 같은 사실은 지어내지 마.\n"
    "5. 따옴표, 설명, 번호 없이 문장만 출력해. 이모지는 최대 1개."
)

# ---- 템플릿 문장용 단어표 ----
MOOD_PHRASE = {"피곤": "피곤한", "스트레스": "스트레스 받는", "우울": "울적한", "좋음": "기분 좋은", "보통": ""}
PEOPLE_PHRASE = {"혼자": "혼자 먹는", "2명": "둘이 먹는", "3~4명": "여럿이 먹는", "5명 이상": "다 같이 먹는"}
# 메뉴 태그 → 꾸며 주는 말 (앞에 있을수록 우선)
TAG_ADJ = [("매움", "얼큰한"), ("차가움", "시원한"), ("국물", "뜨끈한"), ("든든", "든든한"),
           ("달달", "달콤한"), ("담백", "담백한"), ("기름짐", "고소한"), ("특별함", "특별한")]


def template_comment(menu, req, kind):
    """AI 없이 정해진 틀로 문장을 만듭니다. (AI 실패 시 대신 쓰는 안전장치)

    예) "피곤한 점심, 얼큰한 뼈해장국 어때요?"
    """
    # 상황 부분: 기분 > 인원 순으로 하나 + 식사 시간   예) "피곤한 점심"
    situation = MOOD_PHRASE.get(req.mood or "", "") or PEOPLE_PHRASE.get(req.people or "", "")
    meal = req.meal or "오늘"
    head = f"{situation} {meal}".strip()

    # 메뉴 꾸밈말: 태그 중 우선순위가 가장 높은 것 하나
    # next(...) : 조건에 맞는 첫 번째 값을 꺼냄, 없으면 "" (빈 문자열)
    adj = next((word for tag, word in TAG_ADJ if tag in menu["tags"]), "")

    if kind == "onemore":
        return f"이번엔 {adj} {menu['name']}은(는) 어때요?".replace("  ", " ")
    return f"{head}, {adj} {menu['name']} 어때요?".replace("  ", " ")


def clean(text):
    """AI가 쓴 문장을 다듬고 검사합니다. 쓸 수 없는 문장이면 None 을 돌려줌"""
    if not text:
        return None
    # 여러 줄로 썼으면 첫 줄만, 앞뒤 공백과 따옴표 제거
    line = text.strip().splitlines()[0].strip().strip("\"'“”‘’「」")
    # 한글이 한 글자도 없으면(영어로 답했거나 깨짐) 사용하지 않음
    # [가-힣] : 한글 글자 하나를 뜻하는 정규 표현식 패턴
    if not re.search(r"[가-힣]", line):
        return None
    # "당신은 ~" 처럼 사람을 판단하는 문장이면 사용하지 않음 (규칙을 어긴 경우 걸러냄)
    if "당신은" in line or "당신이" in line:
        return None
    # 너무 길면 자르고 말줄임표
    if len(line) > MAX_LEN:
        line = line[:MAX_LEN].rstrip() + "…"
    return line


async def warm_up():
    """서버가 켜질 때 AI 모델을 미리 메모리에 올려 둡니다 (워밍업).

    CPU로 돌리면 모델을 처음 불러오는 데 30~60초가 걸려서, 첫 사용자의 코멘트가 항상 시간 초과가 납니다.
    서버 시작과 동시에 아주 짧은 요청을 한 번 보내 두면, 사용자가 올 때쯤엔 이미 준비돼 있습니다.
    실패해도(Ollama 가 꺼져 있어도) 상관없습니다. 그냥 넘어갑니다.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": "안녕"}],
        "stream": False,
        "options": {"num_predict": 1},   # 딱 1토큰만 → 모델만 올리고 바로 끝
        "keep_alive": "30m",
    }
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            await client.post(OLLAMA_URL, json=payload)
    except httpx.HTTPError:
        pass


async def write_comment(req):
    """추천 한 줄 코멘트를 만듭니다.

    req: main.py 의 CommentRequest (menu, kind, meal, mood, people, ingredient, picks)
    반환: {"text": 문장, "source": "ai" 또는 "template"}
    """
    menu = MENU_BY_ID.get(req.menu)
    if not menu:
        return {"text": "", "source": "template"}

    # ---- AI에게 보낼 질문 만들기 ----
    situation = (
        f"식사 시간: {req.meal or '모름'}, 기분: {req.mood or '말 안 함'}, "
        f"인원: {req.people or '말 안 함'}, 필수 재료: {req.ingredient or '없음'}"
    )
    if req.kind == "onemore":
        task = f"사용자가 고른 메뉴({', '.join(req.picks)}) 말고, 새로 추천하는 메뉴야. 한번 먹어 보고 싶게 써 줘."
    else:
        task = f"사용자가 고른 메뉴({', '.join(req.picks)}) 중에서 지금 상황에 가장 잘 맞아서 고른 메뉴야."
    user_prompt = (
        f"상황: {situation}\n"
        f"추천 메뉴: {menu['name']} (특징: {', '.join(menu['tags'])} / 주재료: {', '.join(menu['ingredients'])})\n"
        f"{task}\n"
        "코멘트:"
    )

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        # options: AI의 글쓰기 설정
        #   num_predict : 최대 몇 토큰(대략 글자 조각)까지 쓸지 → 짧게 제한해서 빨라짐
        #   temperature : 0에 가까울수록 무난하고 일정, 1에 가까울수록 다양하고 창의적
        "options": {"num_predict": 60, "temperature": 0.6},
        # keep_alive : 답한 뒤에도 모델을 메모리에 30분 동안 올려 둠 → 다음 요청이 빨라짐
        "keep_alive": "30m",
    }

    try:
        async with httpx.AsyncClient(timeout=AI_TIMEOUT) as client:
            resp = await client.post(OLLAMA_URL, json=payload)
            resp.raise_for_status()
        text = clean(resp.json().get("message", {}).get("content", ""))
        if text:
            return {"text": text, "source": "ai"}
    except (httpx.HTTPError, ValueError):
        # httpx.HTTPError : 연결 실패, 시간 초과, 4xx/5xx 응답 등 HTTP 관련 에러를 모두 포함하는 부모 에러
        # ValueError      : 응답이 JSON 이 아닐 때
        pass  # 아무것도 하지 않고 아래 템플릿으로 넘어감

    # AI가 실패했거나, 규칙에 맞지 않는 문장을 썼으면 → 템플릿 문장
    return {"text": template_comment(menu, req, req.kind), "source": "template"}


# =============================================================================
# [test 3.0] 📒 내 기록 - "AI가 본 내 취향" 문장
# =============================================================================

INSIGHT_SYSTEM_PROMPT = (
    "너는 음식 추천 앱에서 사용자의 식사 기록을 보고 취향을 요약해 주는 작가야.\n"
    "규칙:\n"
    "1. 자연스러운 한국어 두 문장, 합쳐서 90자 이내.\n"
    "2. 주어진 통계(많이 고른 메뉴, 종류, 특징, 시간대)에 있는 사실만 써. 숫자나 메뉴를 지어내지 마.\n"
    "3. 성격이나 건강을 판단하지 마. 음식 취향 이야기만 해.\n"
    "4. 마지막 문장은 다음에 시도해 볼 만한 방향을 가볍게 제안해.\n"
    "5. 따옴표, 번호, 설명 없이 문장만 출력해."
)
INSIGHT_MAX_LEN = 120


def template_insight(stats):
    """AI 없이 정해진 틀로 취향 문장을 만듦 (AI 실패 시 대신 사용)"""
    if stats["total"] < 3:
        return "기록이 3개 이상 쌓이면 취향을 알려 드릴게요. 마음에 드는 메뉴에서 ✅ 이걸로 먹을래요를 눌러 주세요."
    kind = stats["top_kinds"][0] if stats["top_kinds"] else "여러 종류"
    menu = stats["top_menus"][0] if stats["top_menus"] else ""
    text = f"지금까지 {stats['total']}번 결정했고, {kind}을(를) 가장 많이 고르셨어요."
    if menu:
        text += f" 가장 자주 고른 메뉴는 {menu}예요."
    return text


async def write_insight(stats):
    """📒 내 기록의 취향 문장. stats = records.insight_stats() 가 계산한 사실들

    반환: {"text": 문장, "source": "ai" / "template"}
    """
    if stats["total"] < 3:
        return {"text": template_insight(stats), "source": "template"}

    user_prompt = (
        f"결정 횟수: {stats['total']}번\n"
        f"많이 고른 메뉴: {', '.join(stats['top_menus'])}\n"
        f"많이 고른 종류: {', '.join(stats['top_kinds'])}\n"
        f"자주 나온 특징: {', '.join(stats['top_tags']) or '없음'}\n"
        f"주로 먹은 시간대: {', '.join(stats['top_meals']) or '없음'}\n"
        "취향 요약:"
    )
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": INSIGHT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"num_predict": 120, "temperature": 0.5},
        "keep_alive": "30m",
    }
    try:
        async with httpx.AsyncClient(timeout=AI_TIMEOUT) as client:
            resp = await client.post(OLLAMA_URL, json=payload)
            resp.raise_for_status()
        text = resp.json().get("message", {}).get("content", "").strip()
        # 줄바꿈은 띄어쓰기로 합치고, 따옴표 제거
        text = " ".join(text.split()).strip("\"'“”")
        # 검사: 한글이 있고, 너무 길지 않을 때만 사용
        if re.search(r"[가-힣]", text) and "당신은" not in text:
            if len(text) > INSIGHT_MAX_LEN:
                text = text[:INSIGHT_MAX_LEN].rstrip() + "…"
            return {"text": text, "source": "ai"}
    except (httpx.HTTPError, ValueError):
        pass
    return {"text": template_insight(stats), "source": "template"}
