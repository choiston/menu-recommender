-- =============================================================================
-- schema.sql - PostgreSQL 데이터베이스 표(테이블) 설계도                버전: test 3.0
--
-- SQL(에스큐엘) = 데이터베이스에게 명령하는 언어. "--" 로 시작하는 줄은 주석입니다.
-- 서버(db.py)가 켜질 때 이 파일을 실행합니다.
-- IF NOT EXISTS : 표가 이미 있으면 건너뜀 → 여러 번 실행해도 데이터가 지워지지 않음
--
-- 표 구성
--   [메뉴 지식 = 우리 자산]  categories, menus, menu_tags, menu_meals, menu_ingredients, menu_tips, menu_relations
--   [사용자 (선택 로그인)]   users, sessions
--   [선택 기록]             decisions   ← 로그인한 사람이 "✅ 이걸로 먹을래요" 를 누른 기록만
--
-- 왜 표를 여러 개로 나누나? (정규화)
--   메뉴 하나에 태그가 여러 개, 재료가 여러 개, 팁이 여러 개 있습니다.
--   "한 칸에는 값 하나" 원칙을 지키려고 여러 개인 것은 따로 표를 만들고 menu_id 로 연결합니다.
--   → "돼지고기가 들어간 메뉴" 같은 검색이 쉽고, 같은 정보가 여러 곳에 중복되지 않습니다.
-- =============================================================================

-- ---- 메뉴 종류 (한식, 중식, 멕시칸 ...) ----
CREATE TABLE IF NOT EXISTS categories (
    id    SERIAL PRIMARY KEY,         -- SERIAL : 1, 2, 3 ... 자동으로 늘어나는 번호 / PRIMARY KEY : 이 표에서 한 줄을 구별하는 고유 값
    name  TEXT NOT NULL UNIQUE        -- NOT NULL : 비워 둘 수 없음 / UNIQUE : 같은 이름이 두 번 들어갈 수 없음
);

-- ---- 메뉴 ----
CREATE TABLE IF NOT EXISTS menus (
    id           SERIAL PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    emoji        TEXT NOT NULL,
    category_id  INTEGER NOT NULL REFERENCES categories(id),   -- REFERENCES : 다른 표의 id 를 가리킴 (외래 키). 없는 종류 번호는 못 넣음
    broad        BOOLEAN NOT NULL DEFAULT FALSE,               -- 큰 분류 메뉴인지 (1라운드, 다른 방향 보기에 나옴)
    kcal         INTEGER,                                      -- 1인분 칼로리
    kcal_source  TEXT NOT NULL DEFAULT '추정치',               -- 칼로리 출처: '추정치' / '식약처' 등 → 정보마다 출처를 기록
    info_source  TEXT NOT NULL DEFAULT 'AI 작성',              -- 관련 메뉴·팁 출처
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()            -- TIMESTAMPTZ : 시간대 포함 날짜시간 / now() : 지금 시각
);

-- ---- 메뉴의 특징표 (국물, 매움, 안주 ...) : 메뉴 하나에 여러 줄 ----
CREATE TABLE IF NOT EXISTS menu_tags (
    menu_id  INTEGER NOT NULL REFERENCES menus(id) ON DELETE CASCADE,   -- ON DELETE CASCADE : 메뉴가 지워지면 이 줄도 같이 지워짐
    tag      TEXT NOT NULL,
    PRIMARY KEY (menu_id, tag)                                           -- 두 칸을 합쳐서 고유 → 같은 메뉴에 같은 태그 두 번 불가
);

-- ---- 어울리는 식사 시간 ----
CREATE TABLE IF NOT EXISTS menu_meals (
    menu_id  INTEGER NOT NULL REFERENCES menus(id) ON DELETE CASCADE,
    meal     TEXT NOT NULL,
    PRIMARY KEY (menu_id, meal)
);

-- ---- 주재료 (position = 화면에 보여 줄 순서) ----
CREATE TABLE IF NOT EXISTS menu_ingredients (
    menu_id     INTEGER NOT NULL REFERENCES menus(id) ON DELETE CASCADE,
    ingredient  TEXT NOT NULL,
    position    INTEGER NOT NULL,
    PRIMARY KEY (menu_id, ingredient)
);

-- ---- 맛있게 먹는 법 ----
CREATE TABLE IF NOT EXISTS menu_tips (
    id        SERIAL PRIMARY KEY,
    menu_id   INTEGER NOT NULL REFERENCES menus(id) ON DELETE CASCADE,
    tip       TEXT NOT NULL,
    position  INTEGER NOT NULL,
    source    TEXT NOT NULL DEFAULT 'AI 작성'
);

-- ---- 관련 메뉴 연결 (그래프의 "선") ----
CREATE TABLE IF NOT EXISTS menu_relations (
    menu_id     INTEGER NOT NULL REFERENCES menus(id) ON DELETE CASCADE,
    related_id  INTEGER NOT NULL REFERENCES menus(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    PRIMARY KEY (menu_id, related_id)
);

-- ---- 사용자 (선택 로그인) : 꼭 필요한 것만 받음 (최소 수집) ----
CREATE TABLE IF NOT EXISTS users (
    id             SERIAL PRIMARY KEY,
    email          TEXT NOT NULL UNIQUE,
    nickname       TEXT NOT NULL,
    password_hash  TEXT NOT NULL,          -- 비밀번호 원문은 절대 저장하지 않음. bcrypt 로 암호화한 값만
    agreed_at      TIMESTAMPTZ NOT NULL,   -- 개인정보 수집·이용에 동의한 시각 (동의 없이는 가입 불가)
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---- 로그인 상태 (토큰) ----
-- 로그인하면 긴 무작위 문자열(토큰)을 브라우저에 주고, 브라우저는 요청마다 이 토큰을 보내서 "나예요"를 증명함
-- 토큰도 원문 대신 해시(sha256)로 저장 → DB가 유출돼도 토큰을 그대로 쓸 수 없음
CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL      -- 이 시각이 지나면 다시 로그인해야 함 (30일)
);

-- ---- 선택 기록 : 로그인한 사람이 "✅ 이걸로 먹을래요" 를 누른 것 ----
-- 회원 탈퇴하면 ON DELETE CASCADE 로 기록도 모두 함께 삭제됨
CREATE TABLE IF NOT EXISTS decisions (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    menu_id     INTEGER NOT NULL REFERENCES menus(id),
    source      TEXT NOT NULL,            -- 'decide'(🤖 오늘은 이거예요 그대로) / 'onemore'(One More Think! 로 받은 추천)
    ai_pick     TEXT,                     -- 그때 AI가 추천했던 메뉴 이름 → AI 추천이 맞았는지 나중에 비교
    meal        TEXT,                     -- 그때의 입력값 (독립변수)
    mood        TEXT,
    people      TEXT,
    ingredient  TEXT,
    picks       TEXT[] NOT NULL DEFAULT '{}',   -- TEXT[] : 글자 목록(배열). 라운드에서 고른 메뉴들
    decided_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 인덱스 : 책의 색인처럼, "이 사용자의 기록"을 빨리 찾게 해 줌
CREATE INDEX IF NOT EXISTS idx_decisions_user ON decisions(user_id, decided_at DESC);
