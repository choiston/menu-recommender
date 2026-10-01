# =============================================================================
# main.py - 메뉴 추천 백엔드 서버 (FastAPI)          버전: test 3.2
#
# [추천 - 로그인 안 해도 사용 가능, 로그인하면 개인 취향 반영]
#   POST /api/round    : 다음 라운드 메뉴 5개 받기 (깊이 들어가기 / 다른 방향 보기)  → recommender.py
#   POST /api/decide   : 고른 메뉴 중 하나 고르기 "오늘은 이거예요!"               → recommender.py
#   POST /api/onemore  : [🤔 One More Think!] 고른 메뉴 밖에서 하나 더 추천        → recommender.py
#   POST /api/comment  : 추천 한 줄 코멘트 (AI가 작성, 실패하면 템플릿 문장)     → ai_comment.py
#   POST /api/roulette : [test 3.1] 🎰 룰렛 칸 + 당첨 칸 (서버가 먼저 정함)         → recommender.py
#
# [test 3.0 선택 로그인]                                                         → auth.py
#   POST   /api/auth/signup : 회원가입 (개인정보 수집·이용 동의 필수)
#   POST   /api/auth/login  : 로그인 → 토큰 발급
#   POST   /api/auth/logout : 로그아웃 (토큰 삭제)
#   GET    /api/auth/me     : 지금 로그인한 사람 확인
#   DELETE /api/auth/me     : 회원 탈퇴 (계정 + 기록 모두 삭제)
#
# [test 3.0 내 기록 - 로그인 필수]                                                → records.py
#   POST /api/decisions   : "✅ 이걸로 먹을래요" 기록 저장
#   GET  /api/me/records  : 📒 내 기록 (결정 목록 + 통계)
#   GET  /api/me/insight  : 📒 AI가 본 내 취향 (문장)
#
#   GET  /health       : 서버 살아 있는지 확인
#
# [서버가 켜질 때] DB 준비(표 만들기, 시작 데이터 넣기, 메뉴 읽기) → AI 워밍업
#
# [이전 버전의 주소 - 지금 화면에선 안 쓰지만 남겨 둠]
#   POST /api/chat  : AI(Ollama) 채팅. 나중에 AI 기능을 넣게 되면 다시 쓸 수 있어서 남겨 둠
#
# 이전 버전의 흐름 (/api/chat):
#   브라우저(app.js) --POST /api/chat--> 이 서버 --POST /api/chat--> Ollama(LLM)
#   브라우저(app.js) <----- 추천 답변 ----- 이 서버 <----- 생성된 답변 ----- Ollama
#
# 즉 이 서버는 "중간 다리" 역할을 합니다.
#   1) 브라우저가 보낸 대화 내용을 받고
#   2) 앞에 "너는 메뉴 추천 도우미야" 라는 지시문(시스템 프롬프트)을 붙여서
#   3) Ollama에 전달하고, 받은 답변을 다시 브라우저에 돌려줍니다.
#
# 실행 방법: python main.py 가 아니라 아래처럼 uvicorn(웹 서버 프로그램)으로 실행합니다.
#   uvicorn main:app --port 8000
#   ("main" 파일 안의 "app" 객체를 서버로 띄우라는 뜻)
# Docker로 실행할 때는 backend/Dockerfile 의 CMD 줄이 이 명령을 대신 실행해 줍니다.
# =============================================================================

# ---- 파이썬 기본(표준) 라이브러리 ----
import asyncio                      # 비동기 작업을 "뒤에서" 따로 실행할 때 사용 (AI 워밍업)
import os                           # 환경변수(os.getenv)를 읽기 위해 사용
from typing import List, Optional   # 타입 힌트용: List[ChatMessage] = "ChatMessage 들의 리스트"
                                    #             Optional[str] = "문자열 또는 None(값 없음)"

# ---- 외부 라이브러리 (requirements.txt 에 적혀 있고 pip로 설치됨) ----
import httpx                                        # 다른 서버(Ollama)에 HTTP 요청을 보내는 라이브러리 (requests의 비동기 버전이라고 생각하면 됨)
from fastapi import Depends, FastAPI, Header, HTTPException   # Depends: 로그인 확인 같은 공통 작업을 끼워 넣는 장치
from fastapi.middleware.cors import CORSMiddleware  # CORS 설정용 (아래에서 설명)
from pydantic import BaseModel                      # 요청/응답 데이터의 "모양"을 정의하고 자동 검사해 주는 도구

# ---- 우리가 만든 파일 (같은 backend 폴더) ----
import ai_comment    # AI(Ollama)가 문장을 쓰는 곳 (추천 코멘트, 내 취향)
import auth          # [test 3.0] 선택 로그인
import menus         # [test 3.0] DB에서 메뉴 읽기
import recommender   # 추천 계산 로직
import records       # [test 3.0] 선택 기록, 내 기록, 개인 취향

# 앱 버전. /health 응답과 API 문서(/docs)에 표시됩니다.
APP_VERSION = "test 3.2"


# =============================================================================
# 설정값
# =============================================================================

# os.getenv("이름", "기본값") : 환경변수가 있으면 그 값을, 없으면 기본값을 사용합니다.
# - Docker로 실행하면 docker-compose.yml 에서 OLLAMA_HOST=http://ollama:11434 를 넣어 줍니다.
#   (컨테이너끼리는 서비스 이름 "ollama" 로 서로를 찾을 수 있기 때문)
# - 내 PC에서 직접 실행하면 환경변수가 없으므로 기본값 localhost 를 씁니다.
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# f-string: 문자열 앞에 f 를 붙이면 {변수} 자리에 변수 값이 들어갑니다.
# 결과 예) "http://ollama:11434/api/chat"  ← Ollama의 채팅 API 주소
OLLAMA_URL = f"{OLLAMA_HOST}/api/chat"

# 사용할 LLM 모델 이름. 이 모델은 미리 `ollama pull llama3.1` 로 받아 두어야 합니다.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")

# 시스템 프롬프트: AI에게 "너의 역할은 이거야" 라고 알려 주는 지시문.
# 사용자에게는 보이지 않고, 매 요청마다 대화 맨 앞에 붙여서 보냅니다.
# 괄호 ( ) 안에 문자열을 나란히 쓰면 파이썬이 자동으로 하나로 이어 붙여 줍니다.
SYSTEM_PROMPT = (
    "당신은 친절한 식단/메뉴 추천 도우미입니다. "
    "사용자의 기분, 선호 재료, 알레르기, 날씨, 인원수, 예산 등을 고려해 "
    "구체적인 음식 메뉴를 2~3개 추천하고, 각각 추천 이유를 한두 문장으로 설명하세요. "
    "정보가 부족하면 먼저 필요한 것을 되물어보세요. 한국어로 답변하세요."
)


# =============================================================================
# FastAPI 앱 생성
# =============================================================================

# app 객체가 곧 "서버"입니다. uvicorn main:app 의 app 이 바로 이것.
# title 은 http://localhost:8001/docs 에 자동으로 생기는 API 문서 페이지의 제목입니다.
app = FastAPI(title="Menu Recommender", version=APP_VERSION)


# ---- 서버가 켜질 때 한 번 실행 ----
# @app.on_event("startup") : 서버 시작 시점에 실행할 함수를 등록
# asyncio.create_task(...) : 워밍업을 "뒤에서" 실행 → 기다리지 않고 서버는 바로 요청을 받기 시작함
#   (await 로 기다리면 모델이 다 올라갈 때까지 1분 가까이 서버가 안 켜짐)
@app.on_event("startup")
async def on_startup():
    # ① [test 3.0] DB 준비: 표 만들기 → 비어 있으면 menus.json 넣기 → 메뉴를 메모리로 읽기
    #    asyncio.to_thread : 시간이 걸리는 일반 함수(DB 작업)를 별도 일꾼(스레드)에서 실행하고 끝날 때까지 기다림
    inserted, loaded = await asyncio.to_thread(menus.init)
    print(f"[DB] 메뉴 {loaded}개 준비 완료 (이번에 새로 넣은 메뉴: {inserted}개)")
    # ② AI 워밍업은 기다리지 않고 뒤에서
    asyncio.create_task(ai_comment.warm_up())

# ---- CORS 설정 ----
# 브라우저는 보안 때문에 "다른 주소"의 서버로 요청을 막습니다. (같은 출처 정책)
# 우리 프론트엔드는 localhost:5500, 백엔드는 localhost:8001 → 포트가 다르면 "다른 주소"로 취급!
# 그래서 백엔드가 "다른 주소에서 와도 괜찮아" 라고 허락해 줘야 브라우저가 요청을 보낼 수 있습니다.
# "*" 는 "전부 허용" 이라는 뜻. 공부/개발용으로는 편하지만, 실제 서비스에서는
# 허용할 주소만 콕 집어 적는 것이 안전합니다. (예: ["http://localhost:5500"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 어떤 주소(출처)에서 오는 요청이든 허용
    allow_methods=["*"],   # GET, POST 등 모든 HTTP 메서드 허용
    allow_headers=["*"],   # 모든 요청 헤더 허용 (예: Content-Type)
)


# =============================================================================
# 데이터 모양 정의 (Pydantic 모델)
# BaseModel 을 상속하면, 들어온 JSON이 이 모양과 맞는지 FastAPI가 자동으로 검사합니다.
# 모양이 틀리면 우리 코드가 실행되기도 전에 422 에러를 돌려줍니다.
# =============================================================================

class ChatMessage(BaseModel):
    """대화 메시지 1개. 예) {"role": "user", "content": "점심 추천해줘"}"""
    role: str      # 누가 말했는지: "user"(사용자) / "assistant"(AI) / "system"(지시문)
    content: str   # 실제 메시지 내용


class ChatRequest(BaseModel):
    """브라우저 → 서버로 오는 요청 본문. 지금까지의 대화 전체를 리스트로 보냅니다.
    예) {"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
    """
    messages: List[ChatMessage]


class ChatResponse(BaseModel):
    """서버 → 브라우저로 돌려주는 응답. 예) {"reply": "김치찌개를 추천해요..."}"""
    reply: str


class RecommendRequest(BaseModel):
    """[test 2.0] 브라우저 → 서버: 추천에 필요한 모든 정보.

    서버는 아무것도 기억하지 않습니다(stateless). 대신 브라우저가 매번 "지금까지의 기록 전체"를
    보내 줍니다. 그래서 서버를 재시작해도, 사용자가 여러 명이어도 문제가 없습니다.

    = None / = [] 은 기본값: 브라우저가 안 보내도 에러 없이 이 값으로 채워짐 (선택 입력)
    """
    # ---- 독립변수: 사용자 입력 ----
    meal: Optional[str] = None        # 식사 시간: "아침" / "점심" / "저녁" / "야식"
    mood: Optional[str] = None        # 기분: "피곤" / "스트레스" / "우울" / "좋음" / "보통" (선택)
    people: Optional[str] = None      # 인원수: "혼자" / "2명" / "3~4명" / "5명 이상" (선택)
    keyword: Optional[str] = None     # [test 3.2] 키워드 (선택). "매운 국물", "일식", "돼지고기" 등 → keywords.py 가 이해해서 걸러냄

    # ---- 독립변수: 자동 수집 (브라우저의 시계 기준) ----
    # 서버(Docker 컨테이너)의 시계는 세계 표준시(UTC)라서 한국과 9시간 차이가 날 수 있음
    # → 사용자 기기의 날짜를 받아서 씀
    month: int = 1                    # 월 (1~12) → 계절 계산
    weekday: int = 0                  # 요일 (0=일요일 ~ 6=토요일)

    # ---- 클릭 기록 (test 2.0 부터 메뉴 id = 메뉴 이름 문자열) ----
    liked: List[str] = []             # 지금까지 고른 모든 메뉴 (= 결과 화면에 나올 "내가 고른 메뉴")
    shown: List[str] = []             # 지금까지 화면에 보여 줬던 모든 메뉴
    current: List[str] = []           # 바로 지금 화면에 떠 있는 메뉴 ([다른 방향 보기] 때 피할 종류 계산용)
    picked: List[str] = []            # 이번 라운드에서 고른 메뉴 → 이 메뉴들의 관련 메뉴로 깊이 들어감
    mode: str = "drill"               # "drill"(깊이 들어가기) / "explore"(다른 방향 보기)
    recommended: List[str] = []       # [One More Think!] 로 이미 추천한 메뉴 (다시 추천하지 않으려고)
    explored_kinds: List[str] = []    # [test 3.0] [다른 방향 보기]로 이미 보여 준 종류 (한식, 멕시칸 ...) → 안 가 본 종류부터
    candidates: List[str] = []        # [test 3.1] 룰렛 칸에 넣을 메뉴 (비어 있으면 서버가 10개를 고름)
    avoid: Optional[str] = None       # [test 3.1] 룰렛 [다시 돌리기] 때 피할 메뉴 (바로 전 당첨 메뉴)


# ---- [test 3.0] 로그인 / 기록 ----
class SignupRequest(BaseModel):
    email: str
    nickname: str
    password: str
    agree: bool = False               # 개인정보 수집·이용 동의 (False 면 가입 불가)


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    token: str                        # 로그인 토큰 (브라우저가 보관했다가 요청마다 보냄)
    nickname: str


class DecisionRequest(BaseModel):
    """"✅ 이걸로 먹을래요" 를 눌렀을 때 저장할 것"""
    menu: str                         # 최종으로 고른 메뉴
    source: str = "decide"            # "decide"(오늘은 이거예요·내가 고른 메뉴) / "onemore"(One More Think!) / "roulette"(🎰 룰렛, test 3.1)
    ai_pick: Optional[str] = None     # 그때 "오늘은 이거예요!" 로 추천됐던 메뉴
    meal: Optional[str] = None
    mood: Optional[str] = None
    people: Optional[str] = None
    keyword: Optional[str] = None
    picks: List[str] = []             # 라운드에서 고른 메뉴들


class CommentRequest(BaseModel):
    """[test 2.1] 브라우저 → 서버: 추천 한 줄 코멘트를 써 달라는 요청"""
    menu: str                         # 코멘트를 쓸 메뉴 이름
    kind: str = "decide"              # "decide"(오늘은 이거예요) / "onemore"(원 모어 띵크)
    meal: Optional[str] = None
    mood: Optional[str] = None
    people: Optional[str] = None
    keyword: Optional[str] = None     # DB에는 decisions.ingredient 칸에 저장 (칸 이름은 test 3.0 그대로)
    picks: List[str] = []             # 사용자가 고른 메뉴들 (AI에게 상황 설명용)


class CommentResponse(BaseModel):
    text: str                         # 코멘트 문장
    source: str                       # "ai"(AI가 씀) / "template"(AI 실패 → 정해진 틀)


class MenuOut(BaseModel):
    """서버 → 브라우저: 메뉴 1개 (결과 화면에 쓸 정보까지 포함)"""
    id: str
    name: str
    emoji: str
    category: str                     # [test 3.0] 종류 (한식, 멕시칸 ...)
    tags: List[str]
    kcal: int                         # 1인분 대략 칼로리 (추정치)
    ingredients: List[str]            # 주재료
    tips: List[str]                   # 맛있게 먹는 법


class RecommendResponse(BaseModel):
    """서버 → 브라우저: 추천 결과"""
    menus: List[MenuOut]              # 보여 줄 메뉴들
    mode: str                         # 어떤 방식으로 골랐는지: start / drill / explore (개발 확인용)
    # 지금까지 파악한 성향 태그 (예: ["국물", "매움"]).
    # 화면에는 보여 주지 않습니다(분석당하는 느낌을 주지 않으려고). 개발할 때 /docs 에서 확인하는 용도.
    profile: List[str]
    notice: Optional[str] = None      # 필수 재료 메뉴가 모자랄 때 안내 문구


class RouletteResponse(BaseModel):
    """[test 3.1] 서버 → 브라우저: 룰렛 칸과 당첨 칸"""
    menus: List[MenuOut]              # 룰렛 칸에 들어갈 메뉴들 (칸 순서대로)
    winner: int                       # 당첨 칸 번호 (0부터). 화면은 이 칸에 멈추도록 돌림. 칸이 없으면 -1
    notice: Optional[str] = None


class PickResponse(BaseModel):
    """서버 → 브라우저: 메뉴 하나 (decide / onemore 결과)"""
    menu: Optional[MenuOut] = None    # 추천 메뉴 (더 없으면 None)
    notice: Optional[str] = None      # 안내 문구 (예: "더 추천할 메뉴가 없어요")


# =============================================================================
# API 엔드포인트 (주소별로 어떤 함수를 실행할지 연결)
# @app.get("/주소")  → 그 주소로 GET 요청이 오면 아래 함수 실행
# @app.post("/주소") → 그 주소로 POST 요청이 오면 아래 함수 실행
# =============================================================================

@app.get("/health")
async def health():
    """서버가 살아 있는지 확인하는 용도의 주소 (헬스 체크).
    브라우저에서 http://localhost:8001/health 를 열면 {"status":"ok"} 가 보입니다.
    """
    # 파이썬 딕셔너리를 return 하면 FastAPI가 자동으로 JSON으로 바꿔서 보내 줍니다.
    return {"status": "ok", "version": APP_VERSION}


def personal_of(user):
    """[test 3.0] 로그인했으면 개인 취향 점수, 아니면 None"""
    return records.personal_weights(user["id"]) if user else None


# ---- 라운드 진행 ----
# async 가 없는 일반 def 인 이유: 계산이 빨리 끝나서 기다릴 일(await)이 없기 때문
# user = Depends(auth.optional_user) : 요청마다 "로그인했나?"를 먼저 확인해서 넣어 줌 (안 했으면 None)
@app.post("/api/round", response_model=RecommendResponse)
def recommend_round(req: RecommendRequest, user=Depends(auth.optional_user)):
    """다음 라운드에 보여 줄 메뉴 5개를 돌려줍니다. (첫 화면도 이 주소로 받음)"""
    return recommender.next_round(req, personal_of(user))


# ---- 결과 화면 ----
@app.post("/api/decide", response_model=PickResponse)
def recommend_decide(req: RecommendRequest, user=Depends(auth.optional_user)):
    """고른 메뉴(req.liked) 중 처음 입력에 가장 잘 맞는 하나 → "오늘은 이거예요!" """
    return recommender.decide(req, personal_of(user))


@app.post("/api/onemore", response_model=PickResponse)
def recommend_one_more(req: RecommendRequest, user=Depends(auth.optional_user)):
    """[🤔 One More Think!] 고른 메뉴 밖에서 하나 더 추천 (처음엔 가깝게, 누를수록 멀리)"""
    return recommender.one_more(req, personal_of(user))


# ---- [test 3.1] 🎰 룰렛 ----
@app.post("/api/roulette", response_model=RouletteResponse)
def recommend_roulette(req: RecommendRequest, user=Depends(auth.optional_user)):
    """룰렛 칸(나에게 맞춘 메뉴 10개 또는 내가 고른 메뉴들) + 당첨 칸 번호"""
    return recommender.roulette(req, personal_of(user))


# ---- [test 3.0] 선택 로그인 ----
@app.post("/api/auth/signup", response_model=AuthResponse)
def auth_signup(req: SignupRequest):
    return auth.signup(req.email, req.nickname, req.password, req.agree)


@app.post("/api/auth/login", response_model=AuthResponse)
def auth_login(req: LoginRequest):
    return auth.login(req.email, req.password)


@app.post("/api/auth/logout")
def auth_logout(authorization: str = Header(None)):
    token = auth.token_from_header(authorization)
    if token:
        auth.logout(token)
    return {"ok": True}


@app.get("/api/auth/me")
def auth_me(user=Depends(auth.required_user)):
    return {"nickname": user["nickname"], "email": user["email"]}


@app.delete("/api/auth/me")
def auth_delete_me(user=Depends(auth.required_user)):
    """회원 탈퇴: 계정과 모든 기록 삭제 (개인정보보호: 원하면 언제든 지울 수 있어야 함)"""
    auth.delete_account(user["id"])
    return {"ok": True}


# ---- [test 3.0] 내 기록 (로그인 필수) ----
@app.post("/api/decisions")
def save_decision(req: DecisionRequest, user=Depends(auth.required_user)):
    """"✅ 이걸로 먹을래요" 기록 저장"""
    records.save_decision(user["id"], req)
    return {"ok": True}


@app.get("/api/me/records")
def my_records(user=Depends(auth.required_user)):
    """📒 내 기록: 결정 목록 + 통계"""
    return {"nickname": user["nickname"], **records.get_records(user["id"])}
    # **딕셔너리 : 딕셔너리를 펼쳐서 합침 → {"nickname": ..., "total": ..., "items": ...}


@app.get("/api/me/insight", response_model=CommentResponse)
async def my_insight(user=Depends(auth.required_user)):
    """📒 AI가 본 내 취향 (통계는 코드가 계산, 문장은 AI가 작성)"""
    stats = await asyncio.to_thread(records.insight_stats, user["id"])
    return await ai_comment.write_insight(stats)


# async def 인 이유: AI(Ollama) 답을 기다리는 동안(10~40초) 서버가 다른 요청도 처리할 수 있게
@app.post("/api/comment", response_model=CommentResponse)
async def recommend_comment(req: CommentRequest):
    """추천 메뉴 한 줄 코멘트. AI가 쓰고, 실패하면 정해진 틀의 문장으로 대신함"""
    return await ai_comment.write_comment(req)


# ---- [이전 버전] AI 채팅 ----
# test 1.0 부터 화면에서는 사용하지 않습니다. 나중에 AI 기능(예: 데이터에 없는 메뉴의 관련 메뉴 찾기)에 다시 쓸 수 있어서 남겨 둠.
# response_model=ChatResponse : 응답이 ChatResponse 모양인지 검사하고, /docs 문서에도 표시됩니다.
@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """메뉴 추천 채팅의 핵심 함수.

    req: 브라우저가 보낸 JSON이 자동으로 ChatRequest 객체로 변환되어 들어옵니다.

    async def 란?
      Ollama가 답변을 만드는 동안(수십 초) 서버가 멈춰 있지 않고
      다른 요청도 처리할 수 있게 해 주는 "비동기 함수" 입니다.
      async 함수 안에서는 오래 걸리는 작업 앞에 await 를 붙입니다.
    """

    # ---- 1단계: Ollama에 보낼 메시지 목록 만들기 ----
    # 맨 앞에 시스템 프롬프트(역할 지시문)를 넣고,
    ollama_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    # 그 뒤에 브라우저가 보낸 대화를 순서대로 이어 붙입니다.
    # [ ... for m in req.messages ] 는 "리스트 컴프리헨션": 반복문으로 새 리스트를 한 줄에 만드는 문법.
    # ChatMessage 객체를 Ollama가 이해하는 일반 딕셔너리로 바꾸는 중입니다.
    ollama_messages += [{"role": m.role, "content": m.content} for m in req.messages]

    # ---- 2단계: Ollama API에 보낼 요청 본문(payload) ----
    payload = {
        "model": OLLAMA_MODEL,         # 어떤 모델로 답변을 만들지
        "messages": ollama_messages,   # 대화 내용 (시스템 프롬프트 + 사용자 대화)
        "stream": False,               # False: 답변이 다 만들어진 뒤 한 번에 받기
                                       # (True면 글자가 생성되는 대로 조금씩 받음 → ChatGPT처럼 타이핑 효과)
    }

    # ---- 3단계: Ollama 호출 + 에러 처리 ----
    # try 안에서 에러가 나면 맞는 except 로 넘어갑니다.
    try:
        # async with : 다 쓰고 나면 연결을 자동으로 정리(close)해 줍니다.
        # timeout=300.0 : 최대 300초(5분)까지 기다림. GPU 없이 CPU로 돌리면 첫 답변이 아주 느리기 때문.
        async with httpx.AsyncClient(timeout=300.0) as client:
            # await : 응답이 올 때까지 기다림 (기다리는 동안 서버는 다른 일 가능)
            # json=payload : 딕셔너리를 JSON으로 바꿔서 전송
            resp = await client.post(OLLAMA_URL, json=payload)
            # 응답 상태 코드가 400~599(실패)이면 HTTPStatusError 예외를 일으킴
            resp.raise_for_status()

    # Ollama 서버 자체에 접속이 안 될 때 (Ollama가 꺼져 있음)
    except httpx.ConnectError:
        # HTTPException 을 raise 하면 FastAPI가 브라우저에 에러 응답을 보냅니다.
        # 503 = Service Unavailable (지금 서비스를 쓸 수 없음)
        raise HTTPException(
            status_code=503,
            detail="Ollama에 연결할 수 없습니다. 'ollama serve'가 실행 중인지 확인하세요.",
        )
    # 300초 안에 답이 안 왔을 때
    except httpx.TimeoutException:
        # 504 = Gateway Timeout (중간 서버가 기다리다 시간 초과)
        raise HTTPException(
            status_code=504,
            detail="응답 생성이 너무 오래 걸립니다. 잠시 후 다시 시도해주세요.",
        )
    # 접속은 됐지만 Ollama가 에러를 돌려줬을 때 (예: 모델을 pull 하지 않아서 "model not found")
    except httpx.HTTPStatusError as e:
        # 502 = Bad Gateway (중간 서버가 뒤쪽 서버에게서 잘못된 응답을 받음)
        raise HTTPException(status_code=502, detail=f"Ollama 오류: {e.response.text}")

    # ---- 4단계: Ollama 응답에서 답변 텍스트만 꺼내기 ----
    # Ollama 응답 모양: {"message": {"role": "assistant", "content": "답변 내용"}, ...}
    data = resp.json()
    # .get("키", 기본값) : 키가 없어도 에러 대신 기본값을 돌려줌 → 안전하게 꺼내기
    reply = data.get("message", {}).get("content", "")
    # ChatResponse 모양으로 감싸서 반환 → 브라우저는 {"reply": "..."} 를 받게 됨
    return ChatResponse(reply=reply)
