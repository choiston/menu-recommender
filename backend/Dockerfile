# =============================================================================
# backend/Dockerfile - 백엔드(FastAPI) 컨테이너 이미지를 만드는 "레시피"
# 위에서부터 한 줄씩 실행되며, 각 줄이 이미지의 한 층(layer)이 됩니다.
# docker compose up --build 하면 이 파일대로 이미지를 만듭니다.
# =============================================================================

# 출발점(베이스 이미지): 파이썬 3.11 이 설치된 가벼운(slim) 리눅스
FROM python:3.11-slim

# 컨테이너 안의 작업 폴더를 /app 으로 정함 (없으면 만들고, 이후 명령은 여기서 실행됨 = cd /app)
WORKDIR /app

# requirements.txt 만 "먼저" 복사해서 라이브러리를 설치합니다.
# 이유: Docker는 바뀌지 않은 단계를 캐시(재사용)합니다.
#       main.py 만 고쳤을 때는 pip install 단계를 건너뛰어서 빌드가 훨씬 빨라집니다.
COPY requirements.txt .
# --no-cache-dir : pip 다운로드 캐시를 남기지 않아 이미지 용량을 줄임
RUN pip install --no-cache-dir -r requirements.txt

# 실제 서버 코드 복사. *.py = 확장자가 .py 인 파일 전부 (와일드카드)
# test 1.0 부터 파일이 3개(main.py, recommender.py, menus.py)라서 하나씩 적지 않고 한 번에 복사
COPY *.py .

# "이 컨테이너는 8000번 포트를 사용해요" 라는 문서용 표시.
# 실제로 내 PC와 연결하는 건 docker-compose.yml 의 ports 설정입니다.
EXPOSE 8000

# 컨테이너가 시작될 때 실행할 명령
#   uvicorn main:app   → main.py 안의 app 객체를 웹 서버로 실행
#   --host 0.0.0.0     → 컨테이너 바깥(내 PC)에서도 접속 가능하게 함
#                        (127.0.0.1 로 하면 컨테이너 내부에서만 접속 가능해서 브라우저가 못 들어옴)
#   --port 8000        → 8000번 포트에서 대기
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
