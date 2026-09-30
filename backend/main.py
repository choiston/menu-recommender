import os
from typing import List

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_URL = f"{OLLAMA_HOST}/api/chat"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")

SYSTEM_PROMPT = (
    "당신은 친절한 식단/메뉴 추천 도우미입니다. "
    "사용자의 기분, 선호 재료, 알레르기, 날씨, 인원수, 예산 등을 고려해 "
    "구체적인 음식 메뉴를 2~3개 추천하고, 각각 추천 이유를 한두 문장으로 설명하세요. "
    "정보가 부족하면 먼저 필요한 것을 되물어보세요. 한국어로 답변하세요."
)

app = FastAPI(title="Menu Recommender")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]


class ChatResponse(BaseModel):
    reply: str


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    ollama_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    ollama_messages += [{"role": m.role, "content": m.content} for m in req.messages]

    payload = {
        "model": OLLAMA_MODEL,
        "messages": ollama_messages,
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(OLLAMA_URL, json=payload)
            resp.raise_for_status()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Ollama에 연결할 수 없습니다. 'ollama serve'가 실행 중인지 확인하세요.",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="응답 생성이 너무 오래 걸립니다. 잠시 후 다시 시도해주세요.",
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Ollama 오류: {e.response.text}")

    data = resp.json()
    reply = data.get("message", {}).get("content", "")
    return ChatResponse(reply=reply)
