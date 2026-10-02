# =============================================================================
# frontend/Dockerfile - 프론트엔드 컨테이너 이미지를 만드는 "레시피"
# HTML/CSS/JS 는 브라우저가 실행하므로, 서버는 파일을 그대로 전달만 하면 됩니다.
# [test 3.3] 인터넷 공개용으로 파이썬 내장 서버 대신 전문 웹 서버 nginx 를 사용합니다.
#            nginx 는 화면 파일 제공 + /api 요청을 백엔드로 전달(리버스 프록시)까지 맡습니다.
# [test 3.4] nginx.conf 를 "견본(template)"으로 넣어서 .env 의 PROXY_SECRET 을 채워 넣게 함
# =============================================================================

# nginx 가 설치된 가벼운(alpine) 리눅스 이미지에서 시작
FROM nginx:1.27-alpine

# 견본 설정: 컨테이너가 켜질 때 nginx 이미지가 ${PROXY_SECRET} 등을 채워서 /etc/nginx/conf.d/default.conf 로 만듦
COPY nginx.conf /etc/nginx/templates/default.conf.template
# 두 입구(80, 81)가 함께 쓰는 설정 조각
COPY menu-common.conf menu-proxy.conf /etc/nginx/

# 화면 파일만 복사 (Dockerfile, nginx 설정은 굳이 공개할 필요 없음)
# [test 3.4] privacy.html (개인정보 처리방침) 추가
COPY index.html style.css app.js title.png privacy.html /usr/share/nginx/html/

# 80번(바깥용), 81번(이 Mac 확인용) 포트를 사용한다는 표시 (실제 연결은 docker-compose.yml 의 ports)
EXPOSE 80 81
