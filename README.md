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

---

## 📅 업데이트 기록

> 최신 내용이 위에 옵니다. 무엇을, 왜 바꿨는지 함께 적습니다.

### 2026-10-01
- **모든 소스 파일에 학습용 주석 추가**
  - 대상: `main.py`, `app.js`, `index.html`, `style.css`, `docker-compose.yml`, `Dockerfile` 2개, `requirements.txt`
  - 코드 동작은 그대로이고 주석만 추가했어요. 각 줄이 무엇을 하는지, 왜 그렇게 하는지를 적었어요.
  - 주석을 추가한 뒤 다시 빌드해서 실제로 동작하는지 확인했어요. 채팅 질문에 정상 응답(HTTP 200)이 왔고, 답변까지 약 47초 걸렸어요.
- **README에 `업데이트 기록`, `배운 개념 정리`, `문제 해결 기록` 섹션 추가**

### 2026-09-30
- **첫 커밋**: 프로젝트 전체(파일 9개)를 Git에 처음 저장했어요.
- **Git 사용자 정보(이름/이메일) 설정**: 이 설정이 없어서 커밋이 되지 않던 문제를 해결했어요. 아래 [문제 해결 기록](#-문제-해결-기록) 참고.

---

## 📚 배운 개념 정리

> 이 프로젝트를 만들면서 나온 개념들입니다. 오른쪽 열을 보고 코드에서 직접 찾아보세요.

### 전체 구조

```
[브라우저] ──(5500)──> frontend 컨테이너   : index.html / style.css / app.js 파일만 전달
    │
    └──(8001)──> backend 컨테이너 (main.py) ──(11434)──> ollama 컨테이너 (llama3.1)
                 ↑ 시스템 프롬프트를 붙여서 전달        ↑ 실제로 답변을 생성
```

### 백엔드 (Python / FastAPI)

| 개념 | 한 줄 설명 | 코드 위치 |
|---|---|---|
| FastAPI | 파이썬으로 웹 API 서버를 쉽게 만드는 프레임워크 | `main.py` `app = FastAPI(...)` |
| uvicorn | FastAPI 앱을 실제로 실행하는 웹 서버 프로그램. `python main.py`가 아니라 `uvicorn main:app`으로 실행 | `backend/Dockerfile` CMD |
| 엔드포인트 | `@app.get("/주소")`처럼 주소와 함수를 연결한 것 | `/health`, `/api/chat` |
| Pydantic `BaseModel` | 주고받는 JSON의 모양을 정의하고, 모양이 틀리면 자동으로 422 에러를 냄 | `ChatMessage`, `ChatRequest` |
| `async` / `await` | 오래 걸리는 작업(LLM 응답)을 기다리는 동안에도 서버가 다른 요청을 처리할 수 있게 함 | `async def chat`, `await client.post` |
| 환경변수 `os.getenv` | 코드를 고치지 않고 실행 환경에 따라 설정값을 바꾸는 방법 | `OLLAMA_HOST`, `OLLAMA_MODEL` |
| 시스템 프롬프트 | AI에게 역할을 알려 주는 숨은 지시문. 매 요청마다 대화 맨 앞에 붙여서 보냄 | `SYSTEM_PROMPT` |
| CORS | 포트가 다르면 브라우저가 요청을 막음. 백엔드가 허용해 줘야 요청이 통과함 | `CORSMiddleware` |
| HTTP 상태 코드 | 200 성공 · 400 요청 형식 오류 · 422 데이터 모양 오류 · 502 / 503 / 504 뒤쪽 서버 문제 | `HTTPException` |

### 프론트엔드 (HTML / CSS / JavaScript)

| 개념 | 한 줄 설명 | 코드 위치 |
|---|---|---|
| HTML / CSS / JS 역할 분담 | 뼈대(HTML) / 꾸미기(CSS) / 동작(JS) | `frontend/` 폴더 |
| `getElementById` | id로 HTML 요소를 찾아오는 함수 | `app.js` 위쪽 |
| 이벤트 리스너 | 어떤 일(submit 등)이 생기면 실행할 함수를 등록해 두는 방법 | `formEl.addEventListener` |
| `e.preventDefault()` | form을 제출할 때 페이지가 새로고침되는 기본 동작을 막음 | `app.js` submit 함수 |
| `fetch` | 브라우저에서 서버로 HTTP 요청을 보내는 함수 | `app.js` |
| 대화 기록(history) | LLM은 이전 대화를 기억하지 못함 → 매번 대화 전체를 보내야 함 | `const history = []` |
| `textContent` vs `innerHTML` | `innerHTML`은 받은 글자 속 HTML을 실행할 수 있어 위험(XSS). `textContent`가 안전함 | `addBubble` |
| CSS 변수 `var(--이름)` | 색을 한 곳에 모아 두고 재사용하는 방법 | `style.css` `:root` |
| 미디어 쿼리 `@media` | 다크 모드나 화면 크기에 따라 다른 스타일을 적용 | `style.css` |
| Flexbox | `display: flex`로 요소를 가로·세로로 정렬하고 배치 | `.app`, `.chat`, `.chat-form` |

### Docker

| 개념 | 한 줄 설명 | 코드 위치 |
|---|---|---|
| 이미지 / 컨테이너 | 이미지 = 실행 환경 설계도, 컨테이너 = 그 설계도로 실행 중인 프로그램 | |
| Dockerfile | 이미지를 만드는 레시피. 한 줄이 한 층(layer)이 됨 | `backend/Dockerfile` |
| 빌드 캐시 | 바뀌지 않은 단계는 다시 실행하지 않음 → `requirements.txt`를 먼저 복사하는 이유 | `backend/Dockerfile` |
| docker compose | 여러 컨테이너를 파일 하나로 한 번에 실행·관리 | `docker-compose.yml` |
| 포트 매핑 `"8001:8000"` | 내 PC의 8001번으로 들어온 요청을 컨테이너의 8000번으로 연결 | `docker-compose.yml` |
| 볼륨 | 컨테이너를 지워도 데이터(다운로드한 모델)가 남는 저장 공간 | `ollama_data` |
| 서비스 이름으로 접속 | 컨테이너끼리는 `localhost`가 아니라 `http://ollama:11434`처럼 서비스 이름으로 접속 | `OLLAMA_HOST` |
| `--host 0.0.0.0` | 컨테이너 바깥에서도 접속할 수 있게 열어 줌 | `backend/Dockerfile` CMD |

### Git

| 개념 | 한 줄 설명 |
|---|---|
| 스테이징 → 커밋 | `git add`로 커밋할 파일을 고르고(스테이징), `git commit`으로 저장 |
| `user.name` / `user.email` | 커밋 작성자 정보. 이 정보가 없으면 커밋할 수 없음 |
| `--global` | 이 PC의 모든 저장소에 적용. 빼면 현재 저장소에만 적용 |

---

## 🛠 문제 해결 기록

> 증상 → 원인 → 해결 순서로 적습니다. 같은 문제가 또 생기면 여기부터 보세요.

### 1. 커밋이 안 됨 (`Author identity unknown`)
- **원인**: Git에 작성자 이름과 이메일이 설정돼 있지 않았음
- **해결**:
  ```
  git config --global user.name "이름"
  git config --global user.email "이메일"
  ```

### 2. PowerShell에서 `git` 명령을 찾을 수 없음
- **원인**: Git이 Windows PATH에 등록돼 있지 않아, Git Bash에서만 실행됨
- **해결**: Git Bash를 사용하거나, Git 설치 폴더의 `bin`을 시스템 환경변수 PATH에 추가

### 3. `python main.py`로 실행했더니 서버가 뜨지 않음
- **원인**: `main.py`는 서버 객체(`app`)를 정의만 하고, 직접 실행하는 코드는 없음
- **해결**: `uvicorn main:app --port 8000`으로 실행하거나 `docker compose up -d --build` 사용
- **참고**: `main.py`나 `docker compose up`을 실행해도 **LLM 모델은 자동으로 받아지지 않음**. 모델은 `ollama pull`로 직접 받아야 함

### 4. Git Bash의 curl로 한글 질문을 보내면 `400 There was an error parsing the body`
- **원인**: Windows Git Bash에서 curl 인자로 한글을 넘길 때 인코딩이 깨짐. 서버 문제가 아님
- **해결**: 브라우저(http://localhost:5500)에서 테스트하거나, 컨테이너 안에서 파이썬으로 요청을 보냄
  ```
  docker exec menu-backend python -c "import httpx; print(httpx.post('http://localhost:8000/api/chat', json={'messages':[{'role':'user','content':'점심 추천'}]}, timeout=300).json())"
  ```
