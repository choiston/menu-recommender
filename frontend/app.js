// =============================================================================
// app.js - 화면의 동작(로직)                                   버전: test 3.4
//
// 흐름:
//   ① 시작 화면  : 식사 시간(자동 선택) / 기분 / 인원수 / 필수 재료 → [메뉴 보기]
//                  또는 [🎰 고민 말고 룰렛 돌리기!] → 🎉 오늘의 픽! (test 3.1)
//   ② 라운드 화면: 끌리는 메뉴 클릭 → [다음 ▶] → 고른 메뉴의 "관련 메뉴"로 깊이 들어감
//                  - 🔀 다른 방향 보기 : 아직 안 가 본 종류 5개 (가 본 종류는 explored_kinds 로 기억)
//                  - [◀ 이전] : 앞 라운드 복원 (1라운드에서는 숨김), [↺ 처음으로] : 시작 화면
//                  - [🤖 골라 줘!] : 고르기 끝 → 결과 화면
//   ③ 결과 화면  : 🤖 오늘은 이거예요! / 🤔 One More Think! / 📌 내가 고른 메뉴 (모두 카드)
//                  카드마다 [✅ 이걸로 먹을래요]
//   ④ 마무리 화면: 맛있게 드세요! (로그인했으면 📒 내 기록에 저장)
//   ⑤ 로그인 화면: 선택 로그인 (안 해도 ①~④ 전부 사용 가능)
//   ⑥ 내 기록    : 결정 목록, 통계, AI가 본 내 취향
//
// 서버는 추천 계산을 할 때 아무것도 기억하지 않으므로(stateless), 진행 기록은 브라우저가 들고 있다가 매번 보냅니다.
// 로그인 상태는 "토큰"으로 증명합니다. 토큰은 브라우저(localStorage)에 보관하고 요청마다 머리글에 붙여 보냅니다.
// =============================================================================

// [test 3.3] 화면과 API를 같은 주소(nginx)에서 제공하므로 "." = "지금 화면이 열린 폴더" 기준으로 요청
//            예) https://xxx.synology.me/menu/  → https://xxx.synology.me/menu/api/round
//                https://menu.example.com/       → https://menu.example.com/api/round
//            localhost 를 적으면 다른 사람 컴퓨터에서는 안 됨!
const API_BASE = ".";
const TOKEN_KEY = "menu-token";       // localStorage 에 토큰을 저장할 때 쓰는 이름
const NICK_KEY = "menu-nickname";

// =============================================================================
// 상태(state) : 앱이 기억하는 모든 것
// =============================================================================
const state = {
  // ---- 독립변수 (시작 화면) ----
  meal: null, mood: null, people: null, keyword: "",   // [test 3.2] 키워드 (예: "매운 국물")

  // ---- 라운드 진행 기록 ----
  round: 0,
  basket: [],          // 지금까지 고른 메뉴 객체들 (고른 순서)
  shown: [],           // 지금까지 보여 준 메뉴 id
  current: [],         // 지금 화면의 메뉴 객체들
  selected: new Set(), // 이번 라운드에서 ✓ 한 메뉴 id
  exploredKinds: [],   // [test 3.0] 다른 방향 보기로 이미 보여 준 종류 (한식, 멕시칸 ...)
  history: [],         // [◀ 이전] 용 스냅샷 스택

  // ---- 결과 화면 ----
  finalPicks: [],      // 결과 화면 기준 "내가 고른 메뉴" 전체
  aiPick: null,        // 🤖 오늘은 이거예요! 로 추천된 메뉴
  recommended: [],     // One More Think! 로 이미 추천받은 메뉴 id

  // ---- [test 3.0] 로그인 ----
  token: null,         // 로그인 토큰 (없으면 로그인 안 한 상태)
  nickname: null,
  authMode: "login",   // 로그인 화면의 탭: "login" / "signup"
  returnTo: "start",   // 로그인/내 기록 화면에서 돌아갈 화면
  pendingDecision: null, // 로그인 안 한 채 "이걸로 먹을래요"를 누른 결정 → 로그인하면 저장
  doneReturn: "result",  // 마무리 화면의 [◀ 다시 고를래요] 가 돌아갈 화면 (룰렛에서 왔으면 시작 화면)

  // ---- [test 3.1] 룰렛 ----
  roulette: {
    source: "start",     // 어느 룰렛인가: "start"(시작 화면) / "picks"(결과 화면의 고른 메뉴 룰렛)
    lastWinner: null,    // 바로 전 당첨 메뉴 id → [다시 돌리기] 때 피함
    current: null,       // 지금 당첨 카드에 보이는 메뉴
    spinning: false,     // 돌아가는 중이면 버튼을 다시 못 누르게
  },
};

// =============================================================================
// 도우미
// =============================================================================
const $ = (id) => document.getElementById(id);

const screens = {
  start: $("screen-start"), round: $("screen-round"), result: $("screen-result"),
  done: $("screen-done"), auth: $("screen-auth"), records: $("screen-records"),
};
let currentScreen = "start";

/** 화면 하나만 보이게 */
function showScreen(name) {
  for (const [key, el] of Object.entries(screens)) el.hidden = key !== name;
  currentScreen = name;
  hideError();
  // 화면을 바꾸면 맨 위부터 보이게 (scrollTo 가 없는 환경도 있어서 확인 후 실행)
  if (screens[name].scrollTo) screens[name].scrollTo(0, 0);
}

// [test 3.2] 안내/에러 문구는 "방금 누른 버튼 바로 아래"에 보여 줌
// 예전에는 앱 맨 아래에 떠서, 화면이 길면 안 보이고 "버튼이 동작을 안 한다"고 느껴졌음
let lastButton = null;
// capture: true → 버튼 자신의 click 처리보다 "먼저" 실행되어, 어떤 버튼을 눌렀는지 미리 기억해 둠
document.addEventListener("click", (e) => {
  const btn = e.target.closest("button");
  if (btn) lastButton = btn;
}, { capture: true });

function showError(message) {
  const el = $("error");
  el.textContent = message;
  el.hidden = false;
  // 누른 버튼이 지금 보이는 화면 안에 있으면 그 바로 아래로 옮김 (after : 요소 바로 뒤에 넣기)
  // 버튼이 가로로 나란히 있는 묶음(.actions) 안이면, 묶음 아래로
  const anchor = lastButton && (lastButton.closest(".actions") || lastButton);
  if (anchor && anchor.offsetParent !== null) anchor.after(el);
  else $("screen-" + currentScreen).appendChild(el);
  if (el.scrollIntoView) el.scrollIntoView({ behavior: "smooth", block: "nearest" });   // 화면 안에 보이도록
}
function hideError() { $("error").hidden = true; }

/** localStorage 읽기/쓰기. 사생활 보호 모드 등에서는 막혀 있을 수 있어서 try/catch 로 감쌈 */
function storeGet(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
function storeSet(key, value) {
  try { value === null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch (e) { /* 무시 */ }
}

/**
 * 서버 요청 공통 함수
 * - 로그인했으면 "Authorization: Bearer 토큰" 머리글을 자동으로 붙임
 * - 실패하면 서버가 보낸 안내(detail)를 담아 에러를 던짐
 */
async function api(path, { method = "GET", body } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (state.token) headers["Authorization"] = `Bearer ${state.token}`;

  const res = await fetch(API_BASE + path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    // 401 = 토큰이 만료됐거나 잘못됨 → 로그인 정보를 지워서 "로그인 안 한 상태"로 돌림
    if (res.status === 401 && state.token) setSession(null, null);
    // [test 3.4] 429 = 너무 자주 요청함 (nginx 의 요청 횟수 제한) / 403 = 정해진 입구로 들어오지 않음
    const friendly = {
      429: "요청이 너무 많아요. 잠깐 쉬었다가 다시 해 주세요.",
      403: "이 주소로는 들어올 수 없어요. 서비스 주소로 접속해 주세요.",
    }[res.status];
    const error = new Error(err.detail || friendly || `서버 오류 (${res.status})`);
    error.status = res.status;
    throw error;
  }
  return res.json();
}

function guessMeal() {
  const hour = new Date().getHours();
  if (hour >= 5 && hour < 10) return "아침";
  if (hour >= 10 && hour < 15) return "점심";
  if (hour >= 15 && hour < 21) return "저녁";
  return "야식";
}

const basketIds = () => state.basket.map((m) => m.id);

/** 서버에 보낼 추천 요청 (main.py 의 RecommendRequest 모양과 같아야 함) */
function buildRequest(picked = [], mode = "drill") {
  const now = new Date();
  return {
    meal: state.meal, mood: state.mood, people: state.people, keyword: state.keyword,
    month: now.getMonth() + 1, weekday: now.getDay(),
    liked: basketIds(),
    shown: state.shown,
    current: state.current.map((m) => m.id),
    picked, mode,
    explored_kinds: state.exploredKinds,
  };
}

/** [이전] 용 스냅샷: [...배열] 로 복사본을 만들어야 나중에 원본이 바뀌어도 사진은 그대로 */
function takeSnapshot() {
  return {
    round: state.round, basket: [...state.basket], shown: [...state.shown], current: [...state.current],
    selected: [...state.selected], exploredKinds: [...state.exploredKinds],
  };
}
function restoreSnapshot(s) {
  state.round = s.round; state.basket = s.basket; state.shown = s.shown; state.current = s.current;
  state.selected = new Set(s.selected); state.exploredKinds = s.exploredKinds;
}

const currentPicks = () => state.current.filter((m) => state.selected.has(m.id));

// =============================================================================
// [test 3.0] 로그인 상태
// =============================================================================

/** 로그인 정보 저장 (null 이면 로그아웃 상태로) + 머리글 다시 그리기 */
function setSession(token, nickname) {
  state.token = token;
  state.nickname = nickname;
  storeSet(TOKEN_KEY, token);
  storeSet(NICK_KEY, nickname);
  renderUserArea();
}

/** 머리글 오른쪽: 로그인 안 했으면 [로그인], 했으면 [📒 내 기록] [로그아웃] */
function renderUserArea() {
  const area = $("user-area");
  area.replaceChildren();
  const btn = (text, onClick) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "link-btn small"; b.textContent = text;
    b.addEventListener("click", onClick);
    return b;
  };
  if (state.token) {
    const name = document.createElement("span");
    name.className = "nick";
    name.textContent = `${state.nickname}님`;
    area.append(name, btn("📒 내 기록", () => openRecords()), btn("로그아웃", logout));
  } else {
    area.append(btn("🔑 로그인", () => openAuth("login")));
  }
}

async function logout() {
  try { await api("/api/auth/logout", { method: "POST" }); } catch (e) { /* 이미 만료된 토큰이어도 괜찮음 */ }
  setSession(null, null);
  if (currentScreen === "records") showScreen("start");
}

// =============================================================================
// 카드 그리기
// =============================================================================

/** 라운드 화면 카드 (그림 + 이름, 클릭하면 ✓ 토글) */
function createRoundCard(menu) {
  const card = document.createElement("button");
  card.type = "button";
  card.className = "menu-card";
  const emoji = document.createElement("span");
  emoji.className = "emoji";
  emoji.textContent = menu.emoji;
  const name = document.createElement("span");
  name.className = "name";
  name.textContent = menu.name;
  card.append(emoji, name);
  if (state.selected.has(menu.id)) card.classList.add("selected");
  card.addEventListener("click", () => {
    if (state.selected.has(menu.id)) state.selected.delete(menu.id);
    else state.selected.add(menu.id);
    card.classList.toggle("selected", state.selected.has(menu.id));
    hideError();
  });
  return card;
}

/**
 * 결과 카드 (그림, 이름, AI 코멘트, 칼로리, 주재료, 맛있게 먹는 법, [✅ 이걸로 먹을래요])
 * @param {object} menu
 * @param {string} kind - "decide"(오늘은 이거예요) / "onemore"(One More Think!) / "picked"(내가 고른 메뉴) / "done"(마무리)
 */
function createResultCard(menu, kind) {
  const card = document.createElement("article");
  card.className = "result-card" + (kind === "decide" ? " best" : "") + (kind === "picked" ? " compact" : "");

  if (kind === "onemore") {
    const label = document.createElement("p");
    label.className = "card-label";
    label.textContent = "🤔 이건 어때요?";
    card.appendChild(label);
  }

  const title = document.createElement("h3");
  title.textContent = `${menu.emoji} ${menu.name}`;
  card.appendChild(title);

  // AI 코멘트: "오늘은 이거예요"와 "One More Think!" 카드에만 (내가 고른 메뉴는 이미 내가 고른 거라 생략)
  if (kind === "decide" || kind === "onemore") {
    const comment = document.createElement("p");
    comment.className = "comment loading";
    comment.textContent = "🤖 AI가 한마디 고민 중…";
    card.appendChild(comment);
    fillComment(comment, menu, kind);   // 뒤에서 채움 (await 하지 않음)
  }

  const kcal = document.createElement("p");
  kcal.className = "info";
  kcal.textContent = `🔥 약 ${menu.kcal.toLocaleString()} kcal (1인분)`;
  const ingredients = document.createElement("p");
  ingredients.className = "info";
  ingredients.textContent = `🥩 주재료: ${menu.ingredients.join(", ")}`;
  const tipsTitle = document.createElement("p");
  tipsTitle.className = "tips-title";
  tipsTitle.textContent = "💡 맛있게 먹는 법";
  const tips = document.createElement("ul");
  tips.className = "tips";
  for (const tip of menu.tips) {
    const li = document.createElement("li");
    li.textContent = tip;
    tips.appendChild(li);
  }
  // 정보 묶음(칼로리, 주재료, 먹는 법, 이걸로 먹을래요)을 하나의 상자(details)에 담음
  const details = document.createElement("div");
  details.className = "details";
  details.append(kcal, ingredients, tipsTitle, tips);

  // 🗺️ 카카오맵에서 찾기 : 메뉴 이름으로 검색 (위치는 카카오맵이 알아서, 우리 앱은 위치를 받지 않음)
  const map = document.createElement("a");
  map.className = "map-btn";
  map.textContent = "🗺️ 카카오맵에서 찾기";
  map.href = `https://map.kakao.com/link/search/${encodeURIComponent(menu.name)}`;
  map.target = "_blank";      // 새 탭에서 열기
  map.rel = "noopener";       // 새 탭이 이 페이지를 건드리지 못하게
  details.appendChild(map);

  // [test 3.0] ✅ 이걸로 먹을래요 : 최종 결정 (마무리 화면 카드에는 없음)
  if (kind !== "done") {
    const eat = document.createElement("button");
    eat.type = "button";
    eat.className = "eat-btn";
    eat.textContent = "✅ 이걸로 먹을래요";
    // 어느 카드에서 골랐는지: 내가 고른 메뉴 카드도 "decide" 계열로 기록 (AI 추천과 비교용)
    eat.addEventListener("click", () => decideToEat(menu, kind === "onemore" ? "onemore" : "decide"));
    details.appendChild(eat);
  }
  card.appendChild(details);

  // [test 3.0] One More Think! 카드는 처음엔 접어 두고(이름 + AI 코멘트만), 누르면 정보가 바로 밑에 펼쳐짐
  // → 추천이 여러 개 쌓여도 화면이 길어지지 않고, 궁금한 것만 열어 볼 수 있음
  if (kind === "onemore") {
    details.hidden = true;
    card.classList.add("collapsible");
    const more = document.createElement("p");
    more.className = "more-hint";
    more.textContent = "▼ 눌러서 정보 보기";
    // insertBefore(새것, 기준) : 기준 요소 바로 앞에 넣기 → 정보 상자 위에 안내 문구
    card.insertBefore(more, details);
    card.addEventListener("click", (e) => {
      // [이걸로 먹을래요] 버튼을 누른 경우는 접기/펼치기 하지 않음
      if (e.target.closest(".eat-btn, .map-btn")) return;   // 버튼·링크를 누른 경우는 접기/펼치기 안 함
      details.hidden = !details.hidden;
      more.textContent = details.hidden ? "▼ 눌러서 정보 보기" : "▲ 접기";
    });
  }
  return card;
}

/** AI 한 줄 코멘트 채우기 */
async function fillComment(el, menu, kind) {
  try {
    const data = await api("/api/comment", {
      method: "POST",
      body: {
        menu: menu.id, kind, meal: state.meal, mood: state.mood, people: state.people,
        keyword: state.keyword, picks: state.finalPicks.map((m) => m.name),
      },
    });
    el.textContent = `💬 ${data.text}`;
  } catch (err) {
    el.textContent = "";
  }
  el.classList.remove("loading");
}

// =============================================================================
// 화면 그리기
// =============================================================================

function renderRound(menus, notice = null) {
  state.current = menus;
  $("round-notice").hidden = !notice;
  $("round-notice").textContent = notice || "";
  for (const menu of menus) {
    if (!state.shown.includes(menu.id)) state.shown.push(menu.id);
  }
  $("round-label").textContent = `라운드 ${state.round}`;
  // [test 3.0] 1라운드에서는 [이전] 버튼을 숨김 (시작 화면으로 가는 건 [↺ 처음으로]의 역할)
  $("prev-btn").hidden = state.round === 1;

  const basket = $("basket");
  basket.hidden = state.basket.length === 0;
  basket.textContent = "고른 메뉴: " + state.basket.map((m) => m.name).join(" → ");

  const list = $("menu-list");
  list.replaceChildren();
  for (const menu of menus) list.appendChild(createRoundCard(menu));
  showScreen("round");
}

/** 결과 화면: 오늘은 이거예요 + (One More Think! 자리) + 내가 고른 메뉴 카드 */
function renderResult(menu) {
  state.aiPick = menu;
  $("decision").replaceChildren(createResultCard(menu, "decide"));
  $("onemore-list").replaceChildren();
  $("onemore-btn").disabled = false;

  // [test 3.0] 📌 내가 고른 메뉴: 화면 아래쪽에 카드로. "오늘은 이거예요"와 같은 메뉴는 위에 이미 있으니 빼고 보여 줌
  const others = state.finalPicks.filter((m) => m.id !== menu.id);
  $("picked-summary").textContent =
    state.finalPicks.map((m) => m.name).join(" → ") +
    (others.length === 0 ? "  (위 추천과 같은 메뉴예요)" : "");
  const list = $("picked-list");
  list.replaceChildren();
  // 나중에 고른 메뉴(더 깊이 들어간 메뉴)가 위로
  for (const m of [...others].reverse()) list.appendChild(createResultCard(m, "picked"));
  // [test 3.1] 고른 메뉴가 2개 이상이면 "고른 메뉴로 룰렛" 버튼을 보여 줌
  $("picked-roulette-btn").hidden = state.finalPicks.length < 2;
  showScreen("result");
}

// =============================================================================
// [test 3.1] 🎰 룰렛
//
// 원판 그리기 : CSS conic-gradient(원뿔 모양 그라데이션) 로 원을 N칸으로 나눠 색칠
//              conic-gradient 는 "12시 방향(0deg)에서 시계 방향"으로 색을 칠함
// 돌리기      : transform: rotate(각도) 를 바꾸고, CSS transition 으로 4초 동안 부드럽게 (점점 느려지며 멈춤)
// 결과        : 당첨 칸은 서버가 "먼저" 정함 → 바늘(12시)이 그 칸 가운데 근처에 멈추도록 각도를 계산
// =============================================================================

const SPIN_MS = 4000;   // 도는 시간 (style.css 의 transition 시간과 같아야 함)
const WHEEL_COLORS = ["#ff6b6b", "#ffa94d", "#ffd43b", "#69db7c", "#38d9a9",
                      "#4dabf7", "#748ffc", "#b197fc", "#f783ac", "#ff8787"];

/**
 * 룰렛 원판 하나를 만들어 holder 안에 넣고, 조작 함수들을 돌려줌
 * (시작 화면과 결과 화면 팝업에서 같은 코드를 재사용하려고 "만드는 함수"로 작성)
 */
function createWheel(holder) {
  holder.replaceChildren();
  const wrap = document.createElement("div");
  wrap.className = "wheel-wrap";
  const pointer = document.createElement("div");   // 12시 방향 바늘
  pointer.className = "wheel-pointer";
  pointer.textContent = "▼";
  const disc = document.createElement("div");      // 도는 원판
  disc.className = "wheel";
  const hub = document.createElement("div");       // 가운데 동그라미
  hub.className = "wheel-hub";
  hub.textContent = "🎲";
  wrap.append(pointer, disc, hub);
  holder.appendChild(wrap);

  let rotation = 0;     // 지금까지 돈 총 각도 (계속 더해 감 → 매번 같은 방향으로 여러 바퀴)
  let menus = [];

  /** 칸 색칠 + 메뉴 이름 붙이기 */
  function draw() {
    const n = menus.length || 10;          // 아직 메뉴가 없으면 "?" 10칸
    const slice = 360 / n;                 // 한 칸의 각도
    // "색 시작각 끝각" 을 칸 수만큼 이어 붙임 → 예) "#ff6b6b 0deg 36deg, #ffa94d 36deg 72deg, ..."
    const stops = Array.from({ length: n }, (_, i) =>
      `${WHEEL_COLORS[i % WHEEL_COLORS.length]} ${i * slice}deg ${(i + 1) * slice}deg`).join(", ");
    disc.style.background = `conic-gradient(${stops})`;

    disc.replaceChildren();
    for (let i = 0; i < n; i++) {
      // 이름표: 원판 가운데에서 칸 가운데 방향으로 회전시킨 막대 끝에 글자를 둠
      // 칸 가운데 각도 = (i + 0.5) × slice (12시 기준). CSS 회전은 3시 방향이 0 이라서 90 을 빼 줌
      const label = document.createElement("div");
      label.className = "wheel-label";
      label.style.transform = `rotate(${(i + 0.5) * slice - 90}deg)`;
      const span = document.createElement("span");
      span.textContent = menus[i] ? menus[i].name : "?";
      label.appendChild(span);
      disc.appendChild(label);
    }
  }

  /**
   * winner 번 칸이 바늘(12시)에 오도록 돌림. 다 돌면 끝나는 Promise 를 돌려줌 → await 로 기다릴 수 있음
   * Promise : "나중에 끝나는 일"을 나타내는 객체. resolve() 를 부르면 기다리던 쪽(await)이 다음 줄로 넘어감
   */
  function spin(winner) {
    return new Promise((resolve) => {
      const slice = 360 / menus.length;
      const center = (winner + 0.5) * slice;                 // 당첨 칸 가운데 각도 (12시 기준)
      const jitter = (Math.random() - 0.5) * slice * 0.6;    // 칸 안에서 살짝 비껴 멈추게 (자연스러움)
      // 원판을 R 만큼 돌리면 각도 a 의 칸은 a + R 위치로 감 → a + R 이 0(12시)이 되려면 R = 360 - a
      const target = (360 - center + jitter + 360) % 360;
      const now = ((rotation % 360) + 360) % 360;            // 지금 원판이 놓인 각도 (0~360)
      let delta = target - now;
      if (delta < 0) delta += 360;
      rotation += 360 * 5 + delta;                           // 5바퀴 + 남은 각도
      disc.style.transform = `rotate(${rotation}deg)`;

      // 애니메이션이 끝나면 resolve. transitionend 가 안 오는 환경도 있어서 시간으로도 한 번 더 확인
      let finished = false;
      const done = () => { if (!finished) { finished = true; resolve(); } };
      disc.addEventListener("transitionend", done, { once: true });   // once: 한 번만 듣고 자동 해제
      setTimeout(done, SPIN_MS + 300);
    });
  }

  draw();
  return {
    setMenus(list) { menus = list; draw(); },
    spin,
    getMenus() { return menus; },
  };
}

let startWheel = null;     // 시작 화면 원판
let overlayWheel = null;   // 결과 화면 "고른 메뉴로 룰렛" 원판 (팝업 안)

/** 룰렛 버튼들을 돌아가는 동안 잠금 */
function setRouletteBusy(busy) {
  state.roulette.spinning = busy;
  for (const id of ["roulette-btn", "pick-again", "picked-roulette-btn"]) $(id).disabled = busy;
}

/**
 * 룰렛 한 번 돌리기
 * @param {object} wheel - createWheel 이 돌려준 원판
 * @param {string[]} candidates - 칸에 넣을 메뉴 id (빈 배열이면 서버가 나에게 맞춰 10개를 고름)
 */
async function spinRoulette(wheel, candidates) {
  if (state.roulette.spinning) return;
  setRouletteBusy(true);
  hideError();
  try {
    const data = await api("/api/roulette", {
      method: "POST",
      body: { ...buildRequest(), candidates, avoid: state.roulette.lastWinner },
    });
    if (data.winner < 0 || data.menus.length < 2) {
      showError(data.notice || "룰렛을 돌릴 메뉴가 부족해요.");
      return;
    }
    wheel.setMenus(data.menus);
    await wheel.spin(data.winner);           // 다 돌 때까지 기다림
    const menu = data.menus[data.winner];
    state.roulette.lastWinner = menu.id;
    showPickCard(menu);
    // [test 3.2] 키워드 안내가 있으면 당첨 카드에 표시 (예: "코끼리에 맞는 메뉴가 없어서 전체에서 보여 드려요")
    $("pick-notice").hidden = !data.notice;
    $("pick-notice").textContent = data.notice || "";
  } catch (err) {
    showError(`룰렛을 돌리지 못했어요: ${err.message}`);
  } finally {
    setRouletteBusy(false);
  }
}

/** 시작 화면 [🎰 고민 말고 룰렛 돌리기!] : 지금 입력으로 새 10칸을 받아서 돌림 */
function startRoulette() {
  state.keyword = $("keyword").value.trim();
  state.roulette.source = "start";
  state.roulette.lastWinner = null;          // 새 룰렛이니까 피할 메뉴 없음
  spinRoulette(startWheel, []);
}

/** 결과 화면 [🎰 고른 메뉴로 룰렛 돌리기] : 내가 고른 메뉴들로만 칸을 만들어 팝업에서 돌림 */
function pickedRoulette() {
  state.roulette.source = "picks";
  state.roulette.lastWinner = null;
  openOverlay("wheel");
  overlayWheel.setMenus(state.finalPicks);   // 돌리기 전에 고른 메뉴를 먼저 보여 줌
  spinRoulette(overlayWheel, state.finalPicks.map((m) => m.id));
}

/** 팝업 열기: mode = "wheel"(원판 보이기) / "card"(당첨 카드 보이기) */
function openOverlay(mode) {
  $("overlay").hidden = false;
  $("overlay-wheel").hidden = mode !== "wheel";
  $("pick-card").hidden = mode !== "card";
}
function closeOverlay() { $("overlay").hidden = true; }

/** 🎉 오늘의 픽! 당첨 카드 */
function showPickCard(menu) {
  state.roulette.current = menu;
  $("pick-emoji").textContent = menu.emoji;
  $("pick-name").textContent = menu.name;
  $("pick-kind").textContent = menu.category;
  // 정보: 칼로리, 주재료, 먹는 법 (요소를 하나씩 만들어 안전하게)
  const info = $("pick-info");
  info.replaceChildren();
  const line = (text) => {
    const p = document.createElement("p");
    p.textContent = text;
    info.appendChild(p);
  };
  line(`🔥 약 ${menu.kcal.toLocaleString()} kcal (1인분)`);
  line(`🥩 주재료: ${menu.ingredients.join(", ")}`);
  for (const tip of menu.tips) line(`💡 ${tip}`);
  // 카카오맵 검색 주소. encodeURIComponent : 한글을 주소에 넣을 수 있는 형태(%EC%88%9C...)로 바꿈
  $("pick-map").href = `https://map.kakao.com/link/search/${encodeURIComponent(menu.name)}`;
  openOverlay("card");
}

/** 당첨 카드 [🎲 다시 돌리기] : 같은 칸으로, 바로 전 당첨 메뉴는 피해서 다시 */
function rouletteAgain() {
  if (state.roulette.source === "picks") {
    openOverlay("wheel");
    spinRoulette(overlayWheel, overlayWheel.getMenus().map((m) => m.id));
  } else {
    closeOverlay();
    spinRoulette(startWheel, startWheel.getMenus().map((m) => m.id));
  }
}

/** 당첨 카드 [✅ 이걸로 먹을래요] */
function rouletteEat() {
  closeOverlay();
  const fromStart = state.roulette.source === "start";
  decideToEat(state.roulette.current, "roulette", {
    picks: fromStart ? [] : state.finalPicks.map((m) => m.id),
    aiPick: null,
    returnTo: fromStart ? "start" : "result",
  });
}

// =============================================================================
// 버튼 동작 - 시작 / 라운드
// =============================================================================

function setupChips() {
  for (const group of document.querySelectorAll(".chips")) {
    const key = group.dataset.group;
    group.addEventListener("click", (e) => {
      const btn = e.target.closest("button");
      if (!btn) return;
      const value = btn.dataset.value;
      const unselect = state[key] === value && key !== "meal";
      state[key] = unselect ? null : value;
      for (const b of group.querySelectorAll("button")) {
        b.classList.toggle("active", b.dataset.value === state[key]);
      }
    });
  }
}

function preselectMeal() {
  state.meal = guessMeal();
  const btn = document.querySelector(`[data-group="meal"] [data-value="${state.meal}"]`);
  if (btn) btn.classList.add("active");
}

async function startRounds() {
  state.keyword = $("keyword").value.trim();
  Object.assign(state, {          // Object.assign : 여러 값을 한 번에 덮어쓰기
    round: 1, basket: [], shown: [], current: [], selected: new Set(), history: [], exploredKinds: [],
  });
  try {
    const data = await api("/api/round", { method: "POST", body: buildRequest() });
    if (data.menus.length === 0) return showError(data.notice || "조건에 맞는 메뉴가 없어요.");
    renderRound(data.menus, data.notice);
  } catch (err) {
    showError(`메뉴를 불러오지 못했어요: ${err.message} (백엔드가 켜져 있는지 확인하세요)`);
  }
}

/** 다음 라운드: mode = "drill"([다음]) / "explore"([다른 방향 보기]) */
async function goNext(mode) {
  const snapshot = takeSnapshot();
  const picks = currentPicks();
  for (const menu of picks) {
    if (!basketIds().includes(menu.id)) state.basket.push(menu);
  }
  try {
    const data = await api("/api/round", { method: "POST", body: buildRequest(picks.map((m) => m.id), mode) });
    if (data.menus.length === 0) {
      restoreSnapshot(snapshot);
      return showError(data.notice || "더 보여 줄 메뉴가 없어요. [🤖 골라 줘!]를 눌러 주세요.");
    }
    // [test 3.0] 다른 방향으로 보여 준 종류를 기억 → 다음 다른 방향에서는 안 가 본 종류부터
    if (data.mode === "explore") {
      for (const m of data.menus) {
        if (!state.exploredKinds.includes(m.category)) state.exploredKinds.push(m.category);
      }
    }
    state.history.push(snapshot);
    state.round += 1;
    state.selected = new Set();
    renderRound(data.menus, data.notice);
  } catch (err) {
    restoreSnapshot(snapshot);
    showError(`다음 메뉴를 불러오지 못했어요: ${err.message}`);
  }
}

/** [◀ 이전]: 앞 라운드로 (1라운드에서는 버튼이 숨겨져 있음) */
function prevRound() {
  if (state.history.length === 0) return;   // 혹시 눌려도 시작 화면으로는 가지 않음
  restoreSnapshot(state.history.pop());
  renderRound(state.current);
}

// =============================================================================
// 버튼 동작 - 결과
// =============================================================================

/** [🤖 골라 줘!] */
async function showFinal() {
  const all = [...state.basket];
  for (const menu of currentPicks()) {
    if (!all.some((m) => m.id === menu.id)) all.push(menu);
  }
  if (all.length === 0) return showError("선택한 메뉴가 없어요. 끌리는 메뉴를 눌러 주세요.");

  state.finalPicks = all;
  state.recommended = [];
  try {
    const data = await api("/api/decide", { method: "POST", body: { ...buildRequest(), liked: all.map((m) => m.id) } });
    renderResult(data.menu);
  } catch (err) {
    showError(`결과를 불러오지 못했어요: ${err.message}`);
  }
}

/** [🤔 One More Think!] */
async function oneMore() {
  const btn = $("onemore-btn");
  btn.disabled = true;
  try {
    const data = await api("/api/onemore", {
      method: "POST",
      body: { ...buildRequest(), liked: state.finalPicks.map((m) => m.id), recommended: state.recommended },
    });
    if (!data.menu) return showError(data.notice || "더 추천할 메뉴가 없어요.");
    state.recommended.push(data.menu.id);
    const card = createResultCard(data.menu, "onemore");
    $("onemore-list").appendChild(card);
    if (card.scrollIntoView) card.scrollIntoView({ behavior: "smooth", block: "start" });
    btn.disabled = false;
  } catch (err) {
    showError(`추천을 불러오지 못했어요: ${err.message}`);
    btn.disabled = false;
  }
}

/**
 * [test 3.0] [✅ 이걸로 먹을래요] : 최종 결정 → 마무리 화면
 * 로그인했으면 기록 저장, 안 했으면 저장하지 않고 "로그인하면 남길 수 있어요" 안내
 */
async function decideToEat(menu, source, opts = {}) {
  // opts : 룰렛처럼 결과 화면이 아닌 곳에서 부를 때 바꿀 값들 (picks, aiPick, returnTo)
  // ?? : 왼쪽 값이 null/undefined 일 때만 오른쪽 값을 씀 (빈 배열 [] 은 그대로 씀)
  state.doneReturn = opts.returnTo ?? "result";
  const decision = {
    menu: menu.id, source,
    ai_pick: opts.aiPick !== undefined ? opts.aiPick : (state.aiPick ? state.aiPick.id : null),
    meal: state.meal, mood: state.mood, people: state.people, keyword: state.keyword,
    picks: opts.picks ?? state.finalPicks.map((m) => m.id),
  };

  $("done-emoji").textContent = menu.emoji;
  $("done-title").textContent = menu.name;
  $("done-card").replaceChildren(createResultCard(menu, "done"));
  $("done-login-btn").hidden = true;
  $("done-records-btn").hidden = true;
  showScreen("done");

  if (state.token) {
    await saveDecision(decision);
  } else {
    // 로그인 안 했으면 저장하지 않음 (약속). 대신 "로그인하면 이 기록을 남길 수 있어요"
    state.pendingDecision = decision;
    $("done-save").textContent = "로그인하지 않아서 기록은 남기지 않았어요.";
    $("done-login-btn").hidden = false;
  }
}

async function saveDecision(decision) {
  try {
    await api("/api/decisions", { method: "POST", body: decision });
    state.pendingDecision = null;
    $("done-save").textContent = "📒 내 기록에 저장했어요. 다음 추천부터 내 취향이 반영돼요.";
    $("done-login-btn").hidden = true;
    $("done-records-btn").hidden = false;
  } catch (err) {
    $("done-save").textContent = `기록을 저장하지 못했어요: ${err.message}`;
  }
}

// =============================================================================
// [test 3.0] 로그인 화면
// =============================================================================

function openAuth(mode) {
  if (currentScreen !== "auth") state.returnTo = currentScreen;
  setAuthMode(mode);
  showScreen("auth");
}

/** 로그인 / 회원가입 탭 전환 */
function setAuthMode(mode) {
  state.authMode = mode;
  const signup = mode === "signup";
  $("tab-login").classList.toggle("active", !signup);
  $("tab-signup").classList.toggle("active", signup);
  $("nickname-row").hidden = !signup;
  $("consent-box").hidden = !signup;
  $("auth-submit").textContent = signup ? "가입하기" : "로그인";
  // 비밀번호 자동완성 힌트: 가입할 땐 "새 비밀번호"
  $("auth-password").autocomplete = signup ? "new-password" : "current-password";
  hideError();
}

async function submitAuth(e) {
  e.preventDefault();   // form 제출 시 페이지 새로고침 막기
  const signup = state.authMode === "signup";
  const body = { email: $("auth-email").value, password: $("auth-password").value };
  if (signup) {
    body.nickname = $("auth-nickname").value;
    body.agree = $("auth-agree").checked;
    if (!body.agree) return showError("개인정보 수집·이용에 동의해야 가입할 수 있어요.");
  }
  try {
    const data = await api(signup ? "/api/auth/signup" : "/api/auth/login", { method: "POST", body });
    setSession(data.token, data.nickname);
    $("auth-password").value = "";   // 비밀번호는 화면에 남기지 않음
    showScreen(state.returnTo);
    // 마무리 화면에서 로그인하러 왔다면, 그때의 결정을 이제 저장
    if (state.returnTo === "done" && state.pendingDecision) await saveDecision(state.pendingDecision);
  } catch (err) {
    showError(err.message);
  }
}

// =============================================================================
// [test 3.0] 📒 내 기록 화면
// =============================================================================

async function openRecords() {
  if (!state.token) return openAuth("login");
  if (currentScreen !== "records") state.returnTo = currentScreen;
  showScreen("records");
  $("records-insight").textContent = "AI가 기록을 살펴보는 중…";
  $("records-insight").classList.add("loading");

  try {
    const data = await api("/api/me/records");
    renderRecords(data);
  } catch (err) {
    return showError(`기록을 불러오지 못했어요: ${err.message}`);
  }
  // AI 취향 문장은 오래 걸릴 수 있어서 따로 (목록은 먼저 보임)
  try {
    const ins = await api("/api/me/insight");
    $("records-insight").textContent = ins.text;
  } catch (err) {
    $("records-insight").textContent = "";
  }
  $("records-insight").classList.remove("loading");
}

function renderRecords(data) {
  $("records-title").textContent = `📒 ${data.nickname}님의 기록`;

  // 통계 숫자 카드
  const stat = (n, label) => {
    const d = document.createElement("div");
    d.className = "stat";
    const b = document.createElement("b");
    b.textContent = n;
    const s = document.createElement("span");
    s.textContent = label;
    d.append(b, s);
    return d;
  };
  $("records-stats").replaceChildren(
    stat(`${data.total}번`, "결정한 메뉴"),
    stat(data.total ? `${data.ai_hit_rate}%` : "-", "🤖 추천을 그대로 고름"),
  );

  // 많이 고른 메뉴 / 종류 / 시간대
  const box = (title, items, fmt) => {
    const d = document.createElement("div");
    d.className = "top-box";
    const h = document.createElement("p");
    h.className = "tips-title";
    h.textContent = title;
    const p = document.createElement("p");
    p.className = "info";
    p.textContent = items.length ? items.map(fmt).join(" · ") : "아직 없어요";
    d.append(h, p);
    return d;
  };
  $("records-tops").replaceChildren(
    box("🥇 많이 고른 메뉴", data.top_menus, (m) => `${m.emoji} ${m.name} ${m.count}번`),
    box("🍱 많이 고른 종류", data.top_kinds, (k) => `${k.name} ${k.count}번`),
    box("⏰ 주로 먹은 시간", data.top_meals, (k) => `${k.name} ${k.count}번`),
  );

  // 결정 목록
  const list = $("records-list");
  list.replaceChildren();
  if (data.items.length === 0) {
    const p = document.createElement("p");
    p.className = "hint";
    p.textContent = "아직 기록이 없어요. 메뉴를 고르고 [✅ 이걸로 먹을래요]를 눌러 보세요.";
    list.appendChild(p);
  }
  for (const it of data.items) {
    const row = document.createElement("div");
    row.className = "record-row";
    const when = document.createElement("span");
    when.className = "when";
    // new Date(문자열).toLocaleDateString : 서버 시간(UTC)을 내 기기의 날짜 형식으로 바꿔 보여 줌
    const d = new Date(it.decided_at);
    when.textContent = `${d.getMonth() + 1}/${d.getDate()} ${it.meal || ""}`;
    const what = document.createElement("span");
    what.className = "what";
    what.textContent = `${it.emoji} ${it.menu}`;
    const how = document.createElement("span");
    how.className = "how";
    how.textContent = { onemore: "🤔 One More", roulette: "🎰 룰렛" }[it.source] || "🤖 추천";
    row.append(when, what, how);
    list.appendChild(row);
  }
}

async function deleteAccount() {
  // confirm : 확인/취소 창. 되돌릴 수 없는 일은 한 번 더 물어봄
  if (!window.confirm("정말 탈퇴할까요? 계정과 모든 기록이 바로 삭제되고 되돌릴 수 없어요.")) return;
  try {
    await api("/api/auth/me", { method: "DELETE" });
    setSession(null, null);
    showScreen("start");
  } catch (err) {
    showError(`탈퇴하지 못했어요: ${err.message}`);
  }
}

// =============================================================================
// 시작
// =============================================================================
setupChips();
preselectMeal();
// 저장된 로그인 정보가 있으면 불러오기 (토큰이 만료됐으면 첫 요청에서 401 → 자동으로 로그아웃 상태가 됨)
setSession(storeGet(TOKEN_KEY), storeGet(NICK_KEY));

$("start-btn").addEventListener("click", startRounds);
$("next-btn").addEventListener("click", () => goNext("drill"));
$("explore-btn").addEventListener("click", () => goNext("explore"));
$("prev-btn").addEventListener("click", prevRound);
$("home-btn").addEventListener("click", () => showScreen("start"));
$("result-btn").addEventListener("click", showFinal);
$("onemore-btn").addEventListener("click", oneMore);
$("result-prev-btn").addEventListener("click", () => showScreen("round"));
$("restart-btn").addEventListener("click", () => showScreen("start"));

$("done-back-btn").addEventListener("click", () => showScreen(state.doneReturn));
$("done-home-btn").addEventListener("click", () => showScreen("start"));
$("done-login-btn").addEventListener("click", () => openAuth("login"));
$("done-records-btn").addEventListener("click", openRecords);

$("tab-login").addEventListener("click", () => setAuthMode("login"));
$("tab-signup").addEventListener("click", () => setAuthMode("signup"));
$("auth-form").addEventListener("submit", submitAuth);
$("auth-back-btn").addEventListener("click", () => showScreen(state.returnTo));

$("records-back-btn").addEventListener("click", () => showScreen(state.returnTo === "records" ? "start" : state.returnTo));
$("records-home-btn").addEventListener("click", () => showScreen("start"));
$("delete-account-btn").addEventListener("click", deleteAccount);

// [test 3.1] 🎰 룰렛
startWheel = createWheel($("start-wheel"));
overlayWheel = createWheel($("overlay-wheel"));
$("roulette-btn").addEventListener("click", startRoulette);
$("picked-roulette-btn").addEventListener("click", pickedRoulette);
$("pick-again").addEventListener("click", rouletteAgain);
$("pick-eat").addEventListener("click", rouletteEat);
$("pick-close").addEventListener("click", closeOverlay);
