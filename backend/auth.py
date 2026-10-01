# =============================================================================
# auth.py - 선택 로그인 (회원가입, 로그인, 로그아웃, 탈퇴)                   버전: test 3.0
#
# 로그인은 "선택"입니다. 로그인하지 않아도 앱은 그대로 쓸 수 있고,
# 로그인하면 "✅ 이걸로 먹을래요" 기록이 쌓여서 📒 내 기록과 취향 반영 추천을 받을 수 있어요.
#
# 동작 원리 (토큰 방식)
#   1) 로그인 성공 → 서버가 긴 무작위 문자열(토큰)을 만들어 브라우저에 줌
#   2) 브라우저는 토큰을 보관했다가, 요청할 때마다 머리글(헤더)에 붙여 보냄
#        Authorization: Bearer <토큰>
#   3) 서버는 토큰을 보고 "누구인지" 확인 (DB의 sessions 표와 비교)
#
# 보안 기본기 (개인정보보호)
#   - 비밀번호는 원문을 절대 저장하지 않고 bcrypt 로 암호화한 값만 저장
#   - 토큰도 원문 대신 sha256 해시로 저장 → DB가 유출돼도 토큰을 그대로 쓸 수 없음
#   - 가입할 때 개인정보 수집·이용 동의를 받아야만 가입 가능
#   - 탈퇴하면 계정과 기록을 모두 삭제 (ON DELETE CASCADE)
# =============================================================================

import hashlib                       # sha256 해시 (토큰 저장용)
import re                            # 정규 표현식 (이메일 형식 검사)
import secrets                       # 예측할 수 없는 안전한 무작위 값 (토큰 만들기). random 모듈은 보안용으로 쓰면 안 됨
from datetime import datetime, timedelta, timezone

import bcrypt                        # 비밀번호 암호화 라이브러리 (일부러 느리게 만들어서 무작위 대입 공격을 어렵게 함)
from fastapi import Header, HTTPException

import db

SESSION_DAYS = 30                    # 로그인 유지 기간
MIN_PASSWORD = 8                     # 비밀번호 최소 길이
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")   # 아주 기본적인 이메일 모양: 글자@글자.글자


def hash_token(token):
    """토큰 → sha256 해시 문자열 (DB에는 이것만 저장)"""
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(conn, user_id):
    """새 로그인 토큰을 만들어 DB에 저장하고, 원문 토큰을 돌려줍니다 (원문은 브라우저에만 감)"""
    token = secrets.token_urlsafe(32)    # 약 43글자의 무작위 문자열
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
        (hash_token(token), user_id, expires),
    )
    return token


def signup(email, nickname, password, agree):
    """회원가입. 성공하면 {"token", "nickname"} 을 돌려줌. 실패하면 HTTPException(400/409)"""
    email = (email or "").strip().lower()      # 이메일은 대소문자 구분 없이 저장
    nickname = (nickname or "").strip()

    # ---- 입력 검사 ----
    if not agree:
        raise HTTPException(400, "개인정보 수집·이용에 동의해야 가입할 수 있어요.")
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "이메일 형식이 올바르지 않아요.")
    if not 1 <= len(nickname) <= 20:
        raise HTTPException(400, "닉네임은 1~20자로 적어 주세요.")
    if len(password or "") < MIN_PASSWORD:
        raise HTTPException(400, f"비밀번호는 {MIN_PASSWORD}자 이상이어야 해요.")

    # bcrypt.hashpw(비밀번호, 소금) : 소금(salt) = 사람마다 다른 무작위 값. 같은 비밀번호여도 결과가 달라짐
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    with db.connect() as conn:
        exists = conn.execute("SELECT 1 FROM users WHERE email = %s", (email,)).fetchone()
        if exists:
            # 409 Conflict : 이미 있는 것과 충돌
            raise HTTPException(409, "이미 가입된 이메일이에요. 로그인해 주세요.")
        row = conn.execute(
            "INSERT INTO users (email, nickname, password_hash, agreed_at) VALUES (%s, %s, %s, now()) RETURNING id",
            (email, nickname, pw_hash),
        ).fetchone()
        token = new_session(conn, row["id"])
    return {"token": token, "nickname": nickname}


def login(email, password):
    """로그인. 성공하면 {"token", "nickname"}. 실패하면 HTTPException(401)"""
    email = (email or "").strip().lower()
    with db.connect() as conn:
        user = conn.execute(
            "SELECT id, nickname, password_hash FROM users WHERE email = %s", (email,)
        ).fetchone()
        # 이메일이 없는 경우와 비밀번호가 틀린 경우를 "같은 메시지"로 → 어떤 이메일이 가입됐는지 알려 주지 않기 위해
        if not user or not bcrypt.checkpw((password or "").encode(), user["password_hash"].encode()):
            raise HTTPException(401, "이메일 또는 비밀번호가 맞지 않아요.")
        token = new_session(conn, user["id"])
    return {"token": token, "nickname": user["nickname"]}


def logout(token):
    """로그아웃: 이 토큰을 DB에서 지움 → 더 이상 쓸 수 없음"""
    with db.connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = %s", (hash_token(token),))


def delete_account(user_id):
    """회원 탈퇴: 사용자를 지우면 sessions, decisions 도 ON DELETE CASCADE 로 함께 삭제됨"""
    with db.connect() as conn:
        conn.execute("DELETE FROM users WHERE id = %s", (user_id,))


def token_from_header(authorization):
    """"Bearer abc123" → "abc123". 형식이 아니면 None"""
    if authorization and authorization.startswith("Bearer "):
        return authorization[len("Bearer "):].strip()
    return None


def user_from_token(token):
    """토큰으로 사용자를 찾음. 없거나 만료됐으면 None"""
    if not token:
        return None
    with db.connect() as conn:
        return conn.execute(
            """
            SELECT u.id, u.email, u.nickname
            FROM sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = %s AND s.expires_at > now()
            """,
            (hash_token(token),),
        ).fetchone()


# ---- FastAPI "의존성(Depends)" 함수 ----
# 엔드포인트 함수의 매개변수에 user = Depends(optional_user) 처럼 쓰면,
# FastAPI 가 요청마다 이 함수를 먼저 실행해서 결과를 넣어 줍니다. (로그인 확인 코드를 반복해서 쓰지 않아도 됨)
# Header(None) : 요청 머리글의 "Authorization" 값을 꺼내 줌 (없으면 None)

def optional_user(authorization: str = Header(None)):
    """로그인했으면 사용자 정보, 안 했으면 None (로그인이 "선택"인 주소용)"""
    return user_from_token(token_from_header(authorization))


def required_user(authorization: str = Header(None)):
    """로그인 필수인 주소용. 로그인 안 했으면 401 에러"""
    user = user_from_token(token_from_header(authorization))
    if not user:
        # 401 Unauthorized : 누구인지 확인되지 않음 (로그인 필요)
        raise HTTPException(401, "로그인이 필요해요.")
    return user
