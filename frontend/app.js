// =============================================================================
// app.js - 화면의 동작(로직)                                   버전: test 3.0
//
// 흐름:
//   ① 시작 화면  : 식사 시간(자동 선택) / 기분 / 인원수 / 필수 재료 → [메뉴 보기]
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

const API_BASE = "http://localhost:8001";
const TOKEN_KEY = "menu-token";       // localStorage 에 토큰을 저장할 때 쓰는 이름
const NICK_KEY = "menu-nickname";

// =============================================================================
// 상태(state) : 앱이 기억하는 모든 것
// =============================================================================
const state = {
  // ---- 독립변수 (시작 화면) ----
  meal: null, mood: null, people: null, ingredient: "",

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

function showError(message) { $("error").textContent = message; $("error").hidden = false; }
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
    const error = new Error(err.detail || `서버 오류 (${res.status})`);
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
    meal: state.meal, mood: state.mood, people: state.people, ingredient: state.ingredient,
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
      if (e.target.closest(".eat-btn")) return;
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
        ingredient: state.ingredient, picks: state.finalPicks.map((m) => m.name),
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
  showScreen("result");
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
  state.ingredient = $("ingredient").value.trim();
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
async function decideToEat(menu, source) {
  const decision = {
    menu: menu.id, source, ai_pick: state.aiPick ? state.aiPick.id : null,
    meal: state.meal, mood: state.mood, people: state.people, ingredient: state.ingredient,
    picks: state.finalPicks.map((m) => m.id),
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
    how.textContent = it.source === "onemore" ? "🤔 One More" : "🤖 추천";
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

$("done-back-btn").addEventListener("click", () => showScreen("result"));
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
