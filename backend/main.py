# =============================================================================
# main.py - 메뉴 추천 백엔드 서버 (FastAPI)
#
# 전체 흐름:
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
import os                 # 환경변수(os.getenv)를 읽기 위해 사용
from typing import List   # 타입 힌트용: List[ChatMessage] = "ChatMessage 들의 리스트"

# ---- 외부 라이브러리 (requirements.txt 에 적혀 있고 pip로 설치됨) ----
import httpx                                        # 다른 서버(Ollama)에 HTTP 요청을 보내는 라이브러리 (requests의 비동기 버전이라고 생각하면 됨)
from fastapi import FastAPI, HTTPException          # FastAPI: 웹 API 서버를 만드는 프레임워크 / HTTPException: 에러 응답을 보낼 때 사용
from fastapi.middleware.cors import CORSMiddleware  # CORS 설정용 (아래에서 설명)
from pydantic import BaseModel                      # 요청/응답 데이터의 "모양"을 정의하고 자동 검사해 주는 도구


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
app = FastAPI(title="Menu Recommender")

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
    return {"status": "ok"}


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
