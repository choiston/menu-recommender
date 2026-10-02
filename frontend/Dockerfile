# =============================================================================
# frontend/Dockerfile - 프론트엔드 컨테이너 이미지를 만드는 "레시피"
# HTML/CSS/JS 는 브라우저가 실행하므로, 서버는 파일을 그대로 전달만 하면 됩니다.
# [test 3.3] 인터넷 공개용으로 파이썬 내장 서버 대신 전문 웹 서버 nginx 를 사용합니다.
#            nginx 는 화면 파일 제공 + /api 요청을 백엔드로 전달(리버스 프록시)까지 맡습니다.
# =============================================================================

# nginx 가 설치된 가벼운(alpine) 리눅스 이미지에서 시작
FROM nginx:1.27-alpine

# 우리 설정(nginx.conf)으로 기본 설정을 바꿔 끼움
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 화면 파일만 복사 (Dockerfile, nginx.conf 는 굳이 공개할 필요 없음)
COPY index.html style.css app.js title.png /usr/share/nginx/html/

# 80번 포트를 사용한다는 표시 (실제 연결은 docker-compose.yml 의 ports)
EXPOSE 80
