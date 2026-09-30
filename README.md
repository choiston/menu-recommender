# AI 메뉴 추천 (menu-recommender)

Ollama(Llama) 모델을 사용해 대화형으로 음식 메뉴를 추천해주는 웹앱입니다.
Ollama + FastAPI 백엔드 + 프론트엔드 모두 Docker 컨테이너로 실행합니다.

## 실행 방법

```
docker compose up -d --build
```

최초 실행 후, 컨테이너 안의 Ollama에 모델을 받아둡니다 (한 번만 하면 됨).

```
docker exec -it menu-ollama ollama pull llama3.1
```

> 더 작은 모델(llama3.2:3b)도 시도해봤지만 한국어 응답 품질이 많이 떨어져(단어 깨짐, 외국어 혼입) llama3.1(8B)을 기본값으로 사용합니다. GPU가 없는 환경이라 응답에 첫 요청은 수 분, 이후에는 모델이 메모리에 로드된 상태라 20초 내외가 걸립니다.

브라우저에서 `http://localhost:5500` 접속 후 채팅으로 메뉴를 물어보면 됩니다.

## 구조

```
menu-recommender/
├── docker-compose.yml     # ollama + backend + frontend 3개 컨테이너
├── backend/
│   ├── main.py            # FastAPI 서버, /api/chat 에서 Ollama 호출
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   └── Dockerfile
└── README.md
```

## 컨테이너 구성

- `menu-ollama` : Ollama 서버 (포트 11434), 모델은 `ollama_data` 볼륨에 저장되어 재시작해도 유지됨
- `menu-backend` : FastAPI 서버 (호스트 포트 8001 → 컨테이너 8000), 컨테이너 내부에서 `http://ollama:11434`로 Ollama 호출. 8000번은 `investment_backend` 컨테이너가 이미 사용 중이라 8001로 매핑했습니다.
- `menu-frontend` : 정적 파일 서버 (포트 5500)

## 유용한 명령어

```
docker compose logs -f backend   # 백엔드 로그 확인
docker compose down              # 전체 종료
docker compose up -d --build     # 코드 수정 후 재빌드/재시작
```

## 모델 변경

`docker-compose.yml`의 `backend` 서비스 `OLLAMA_MODEL` 환경변수를 원하는 Ollama 모델명으로 바꾸고,
`docker exec -it menu-ollama ollama pull <모델명>`으로 받은 뒤 재시작하면 됩니다.
