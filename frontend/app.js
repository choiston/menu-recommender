// =============================================================================
// app.js - 화면의 동작(로직)                                   버전: test 2.1
//
// 흐름:
//   ① 시작 화면  : 식사 시간(자동 선택) / 기분 / 인원수 / 재료 → [메뉴 보기]
//   ② 라운드 화면: 끌리는 메뉴 클릭 → [다음] → 고른 메뉴의 "관련 메뉴"로 깊이 들어감
//                  예) 국밥 → 돼지국밥, 순대국밥, 소머리국밥 ... → 순대국밥 → 순대, 순대볶음 ...
//                  - 여러 개 고르면 각각의 관련 메뉴가 섞여서 나옴
//                  - 아무것도 안 고르고 [다음] 또는 [다른 방향 보기] → 다른 종류의 메뉴
//                  - [◀ 이전] 으로 앞 라운드에 돌아갈 수 있음
//                  - 라운드 제한 없음. 원할 때 [결과 보기]
//   ③ 결과 화면  : 🤖 오늘은 이거예요! → 고른 메뉴 중 처음 입력에 가장 잘 맞는 하나 (+ AI 한 줄 코멘트)
//                  🤔 원 모어 띵크   → 누를 때마다 다른 음식 추천이 아래로 쌓임 (처음엔 가깝게, 점점 멀리)
//                  각 카드에 칼로리 / 주재료 / 맛있게 먹는 법
//
// 필수 재료를 적으면 그 재료가 들어간 메뉴만 나옵니다. (test 2.1: "당기는 재료" → "필수 재료")
//
// 역할 분담:
//   - 이 파일(브라우저) : 화면 바꾸기, 고른 기록 들고 있기, 결과 화면 만들기
//   - 서버(main.py → recommender.py) : 기록을 받아서 다음 메뉴 고르기
//   서버는 아무것도 기억하지 않으므로, 기록(state)은 전부 브라우저가 들고 있다가 매번 보냅니다.
//
// 성향 분석 결과는 화면에 보여 주지 않습니다. ("분석당하는 느낌"을 주지 않기 위해)
// =============================================================================

// 백엔드 주소. docker-compose.yml 에서 백엔드 컨테이너를 내 PC의 8001번 포트에 연결해 둠
const API_BASE = "http://localhost:8001";

// =============================================================================
// 상태(state) : 지금 앱이 기억하고 있는 모든 것을 한 객체에 모아 둠
// test 2.0 부터 메뉴 id 는 메뉴 이름(문자열)입니다. 예) "순대국밥"
// =============================================================================
const state = {
  // ---- 독립변수 (시작 화면에서 고름) ----
  meal: null,       // "아침" / "점심" / "저녁" / "야식"
  mood: null,       // 선택 안 하면 null
  people: null,     // 선택 안 하면 null
  ingredient: "",   // 재료 입력값

  // ---- 진행 기록 ----
  round: 0,         // 현재 라운드 번호
  basket: [],       // 지금까지 고른 메뉴들 (서버가 준 메뉴 객체, 고른 순서대로) = 결과 화면에 나올 것
  shown: [],        // 지금까지 화면에 보여 준 모든 메뉴 id
  current: [],      // 지금 화면에 떠 있는 메뉴 객체들

  // Set(집합): 중복 없이 값을 모아 두는 자료형. 이번 라운드에서 클릭(✓)한 메뉴 id
  selected: new Set(),

  // [◀ 이전] 을 위한 기록 보관함 (스택)
  // [다음] 을 누를 때마다 "그 순간의 상태 사진(스냅샷)" 을 맨 위에 쌓고,
  // [이전] 을 누르면 맨 위의 사진을 꺼내서 그대로 되돌립니다.
  history: [],

  // ---- 결과 화면 ----
  finalPicks: [],   // 결과 화면에 들어올 때의 "내가 고른 메뉴" 전체 (고른 순서)
  recommended: [],  // 원 모어 띵크로 이미 추천받은 메뉴 id (다시 안 나오게)
};

// =============================================================================
// HTML 요소 가져오기
// =============================================================================
// $ 라는 이름의 짧은 함수를 만들어 둠 (매번 document.getElementById 를 길게 안 쓰려고)
const $ = (id) => document.getElementById(id);

const screens = {
  start: $("screen-start"),
  round: $("screen-round"),
  result: $("screen-result"),
};

// =============================================================================
// 도우미 함수들
// =============================================================================

/** 화면 3개 중 name 에 해당하는 것만 보이고 나머지는 숨김 */
function showScreen(name) {
  // Object.entries(객체) : {키: 값} 을 [[키, 값], ...] 배열로 바꿔 줌
  for (const [key, el] of Object.entries(screens)) {
    el.hidden = key !== name;
  }
  hideError();
}

/** 현재 시각으로 식사 시간을 추측 (시작 화면에서 미리 선택해 두기 위함) */
function guessMeal() {
  const hour = new Date().getHours(); // 0~23시 (사용자 기기의 시계)
  if (hour >= 5 && hour < 10) return "아침";
  if (hour >= 10 && hour < 15) return "점심";
  if (hour >= 15 && hour < 21) return "저녁";
  return "야식";
}

/** 지금까지 고른 메뉴 id 목록 */
function basketIds() {
  return state.basket.map((m) => m.id);
}

/**
 * 서버에 보낼 데이터 만들기 (main.py 의 RecommendRequest 모양과 똑같아야 함)
 * @param {string[]} picked - 이번 라운드에서 고른 메뉴 id (이 메뉴들의 관련 메뉴로 들어감)
 * @param {string} mode - "drill"(깊이 들어가기) / "explore"(다른 방향)
 */
function buildRequest(picked = [], mode = "drill") {
  const now = new Date();
  return {
    meal: state.meal,
    mood: state.mood,
    people: state.people,
    ingredient: state.ingredient,
    month: now.getMonth() + 1, // getMonth() 는 0~11 이라서 +1 → 1~12
    weekday: now.getDay(),     // 0=일요일 ~ 6=토요일
    liked: basketIds(),
    shown: state.shown,
    current: state.current.map((m) => m.id),
    picked: picked,
    mode: mode,
  };
}

/** 서버에 POST 요청을 보내고 JSON 응답을 돌려받는 공통 함수 */
async function post(path, body) {
  const res = await fetch(API_BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body), // JS 객체 → JSON 문자열
  });
  if (!res.ok) {
    throw new Error(`서버 오류 (${res.status})`);
  }
  return res.json(); // JSON 문자열 → JS 객체
}

function showError(message) {
  $("error").textContent = message;
  $("error").hidden = false;
}

function hideError() {
  $("error").hidden = true;
}

/**
 * 지금 상태를 사진 찍듯 복사해 둠 (스냅샷)
 * [...배열] 로 "복사본"을 만들어 저장해야, 나중에 원본이 바뀌어도 사진은 그대로 남음 (얕은 복사)
 */
function takeSnapshot() {
  return {
    round: state.round,
    basket: [...state.basket],
    shown: [...state.shown],
    current: [...state.current],
    selected: [...state.selected], // Set → 배열로 복사
  };
}

/** 스냅샷으로 상태를 되돌림 */
function restoreSnapshot(snap) {
  state.round = snap.round;
  state.basket = snap.basket;
  state.shown = snap.shown;
  state.current = snap.current;
  state.selected = new Set(snap.selected); // 배열 → 다시 Set 으로
}

/** 이번 라운드에서 선택(✓)한 메뉴 객체들 */
function currentPicks() {
  // filter : 조건이 true 인 것만 남김
  return state.current.filter((m) => state.selected.has(m.id));
}

// =============================================================================
// 화면 그리기
// =============================================================================

/** 라운드 화면의 메뉴 카드 하나 (그림 + 이름만, 클릭하면 ✓ 토글) */
function createRoundCard(menu) {
  const card = document.createElement("button");
  card.type = "button";
  card.className = "menu-card";

  // textContent 로 넣는 이유: innerHTML 은 글자 속 HTML 이 실행될 수 있어 위험(XSS)
  const emoji = document.createElement("span");
  emoji.className = "emoji";
  emoji.textContent = menu.emoji;

  const name = document.createElement("span");
  name.className = "name";
  name.textContent = menu.name;

  card.append(emoji, name);

  // [이전] 으로 돌아왔을 때는 그때 선택했던 메뉴가 ✓ 상태로 보이게
  if (state.selected.has(menu.id)) card.classList.add("selected");

  card.addEventListener("click", () => {
    // 클릭할 때마다 선택 ↔ 해제 (토글)
    if (state.selected.has(menu.id)) {
      state.selected.delete(menu.id);
    } else {
      state.selected.add(menu.id);
    }
    // classList.toggle(이름, 조건) : 조건이 true 면 클래스 추가, false 면 제거 → CSS 로 ✓ 표시
    card.classList.toggle("selected", state.selected.has(menu.id));
    hideError();
  });
  return card;
}

/**
 * 라운드 화면 그리기
 * @param {object[]} menus - 보여 줄 메뉴들
 * @param {string|null} notice - 서버가 보낸 안내 문구 (필수 재료 메뉴가 모자랄 때). 없으면 null
 */
function renderRound(menus, notice = null) {
  state.current = menus;

  // 안내 문구가 있으면 보여 주고, 없으면 숨김
  $("round-notice").hidden = !notice;
  $("round-notice").textContent = notice || "";

  // 새로 보여 주는 메뉴 id 를 "보여 준 목록"에 추가 (중복 없이)
  for (const menu of menus) {
    if (!state.shown.includes(menu.id)) state.shown.push(menu.id);
  }

  $("round-label").textContent = `라운드 ${state.round}`;
  // 1라운드에선 돌아갈 라운드가 없으니 "처음으로" (시작 화면), 그 뒤로는 "이전"
  $("prev-btn").textContent = state.round === 1 ? "◀ 처음으로" : "◀ 이전";

  // 지금까지 고른 메뉴를 화살표로 이어서 보여 줌. 예) "고른 메뉴: 국밥 → 순대국밥"
  // (사용자가 직접 고른 것을 보여 주는 것이라 "분석"이 아님 → 내가 어디까지 왔는지 길잡이)
  const basket = $("basket");
  basket.hidden = state.basket.length === 0;
  basket.textContent = "고른 메뉴: " + state.basket.map((m) => m.name).join(" → ");

  const list = $("menu-list");
  list.replaceChildren(); // 기존 카드를 모두 지움
  for (const menu of menus) {
    list.appendChild(createRoundCard(menu));
  }
  showScreen("round");
}

/**
 * 결과 화면의 카드 하나 (그림, 이름, AI 코멘트, 칼로리, 주재료, 맛있게 먹는 법)
 * 요소를 하나씩 만들어 붙이는 방식 (createElement + textContent) → 안전함
 * @param {object} menu - 메뉴
 * @param {string} kind - "decide"(오늘은 이거예요, 강조) / "onemore"(원 모어 띵크)
 */
function createResultCard(menu, kind) {
  const card = document.createElement("article"); // article : 독립된 하나의 내용 덩어리를 뜻하는 태그
  card.className = "result-card" + (kind === "decide" ? " best" : "");

  // 원 모어 띵크 카드에는 "이건 어때요?" 꼬리표
  if (kind === "onemore") {
    const label = document.createElement("p");
    label.className = "card-label";
    label.textContent = "🤔 이건 어때요?";
    card.appendChild(label);
  }

  // 제목 줄: 🍲 순대국밥
  const title = document.createElement("h3");
  title.textContent = `${menu.emoji} ${menu.name}`;

  // AI 한 줄 코멘트 자리. 처음엔 "고민 중…" → 서버 답이 오면 fillComment 가 글자를 바꿈
  const comment = document.createElement("p");
  comment.className = "comment loading";
  comment.textContent = "🤖 AI가 한마디 고민 중…";

  // 정보 줄: 🔥 약 650 kcal · 🥩 순대, 돼지머리고기, 부추
  const kcal = document.createElement("p");
  kcal.className = "info";
  // toLocaleString() : 숫자에 천 단위 쉼표를 붙여 줌 (1000 → "1,000")
  kcal.textContent = `🔥 약 ${menu.kcal.toLocaleString()} kcal (1인분)`;

  const ingredients = document.createElement("p");
  ingredients.className = "info";
  ingredients.textContent = `🥩 주재료: ${menu.ingredients.join(", ")}`;

  // 맛있게 먹는 법: <ul> 목록
  const tipsTitle = document.createElement("p");
  tipsTitle.className = "tips-title";
  tipsTitle.textContent = "💡 맛있게 먹는 법";

  const tips = document.createElement("ul"); // ul = 순서 없는 목록, li = 목록의 한 항목
  tips.className = "tips";
  for (const tip of menu.tips) {
    const li = document.createElement("li");
    li.textContent = tip;
    tips.appendChild(li);
  }

  card.append(title, comment, kcal, ingredients, tipsTitle, tips);

  // 카드는 바로 보여 주고, 코멘트는 "뒤에서" 따로 받아 옴 (await 하지 않음)
  // → AI가 10~40초 걸려도 메뉴 정보는 즉시 보임
  fillComment(comment, menu, kind);
  return card;
}

/**
 * AI 한 줄 코멘트를 받아서 카드에 채움
 * 서버(/api/comment)가 AI로 쓰고, AI가 실패하면 정해진 틀의 문장을 대신 보내 줌
 */
async function fillComment(el, menu, kind) {
  try {
    const data = await post("/api/comment", {
      menu: menu.id,
      kind: kind,
      meal: state.meal,
      mood: state.mood,
      people: state.people,
      ingredient: state.ingredient,
      picks: state.finalPicks.map((m) => m.name),
    });
    el.textContent = `💬 ${data.text}`;
  } catch (err) {
    el.textContent = ""; // 서버 오류면 코멘트 없이 둠 (메뉴 정보는 이미 보이니까 괜찮음)
  }
  el.classList.remove("loading");
}

/** 결과 화면 그리기: AI가 고른 메뉴 하나 + 내가 고른 메뉴 요약 */
function renderResult(menu) {
  $("decision").replaceChildren(createResultCard(menu, "decide"));
  $("onemore-list").replaceChildren(); // 원 모어 띵크 카드는 새로 시작
  $("onemore-btn").disabled = false;
  $("picked-summary").textContent =
    "📌 내가 고른 메뉴: " + state.finalPicks.map((m) => m.name).join(" → ");
  showScreen("result");
}

// =============================================================================
// 버튼 동작
// =============================================================================

/** 시작 화면의 버튼 묶음(chips)이 "하나만 선택" 되도록 설정 */
function setupChips() {
  for (const group of document.querySelectorAll(".chips")) {
    const key = group.dataset.group; // data-group="meal" → "meal" (state 의 어떤 칸인지)

    group.addEventListener("click", (e) => {
      // 이벤트 위임: 묶음(부모)에 한 번만 등록해 두고, 실제로 눌린 버튼은 e.target 으로 찾음
      const btn = e.target.closest("button");
      if (!btn) return;

      const value = btn.dataset.value;
      // 이미 선택된 걸 또 누르면 선택 해제. 단, 식사 시간(meal)은 꼭 하나 필요하므로 해제하지 않음
      const unselect = state[key] === value && key !== "meal";
      state[key] = unselect ? null : value;

      for (const b of group.querySelectorAll("button")) {
        b.classList.toggle("active", b.dataset.value === state[key]);
      }
    });
  }
}

/** 식사 시간 버튼을 현재 시각에 맞게 미리 선택해 둠 */
function preselectMeal() {
  state.meal = guessMeal();
  const btn = document.querySelector(`[data-group="meal"] [data-value="${state.meal}"]`);
  if (btn) btn.classList.add("active");
}

/** [메뉴 보기] : 첫 라운드 시작 (기록을 모두 새로 시작) */
async function startRounds() {
  state.ingredient = $("ingredient").value.trim();
  state.round = 1;
  state.basket = [];
  state.shown = [];
  state.current = [];
  state.selected = new Set();
  state.history = [];

  try {
    const data = await post("/api/round", buildRequest());
    // 필수 재료가 들어간 메뉴가 하나도 없으면 시작 화면에 머물면서 안내
    if (data.menus.length === 0) {
      showError(data.notice || "조건에 맞는 메뉴가 없어요.");
      return;
    }
    renderRound(data.menus, data.notice);
  } catch (err) {
    showError(`메뉴를 불러오지 못했어요: ${err.message} (백엔드가 켜져 있는지 확인하세요)`);
  }
}

/**
 * 다음 라운드로 이동
 * @param {string} mode - "drill" : [다음] (고른 메뉴의 관련 메뉴로)
 *                        "explore" : [다른 방향 보기] (다른 종류의 메뉴로)
 * 아무것도 안 고르고 [다음]을 누르면 서버가 알아서 "explore" 로 처리함
 */
async function goNext(mode) {
  // [이전] 으로 돌아올 수 있도록, 바뀌기 전 상태를 사진 찍어 둠
  const snapshot = takeSnapshot();

  // 이번에 고른 메뉴를 "고른 메뉴" 바구니에 추가 (이미 있으면 건너뜀)
  const picks = currentPicks();
  for (const menu of picks) {
    if (!basketIds().includes(menu.id)) state.basket.push(menu);
  }

  try {
    const data = await post("/api/round", buildRequest(picks.map((m) => m.id), mode));
    // 더 보여 줄 메뉴가 없으면(필수 재료 메뉴를 다 봤을 때) 지금 화면에 머물면서 안내
    if (data.menus.length === 0) {
      restoreSnapshot(snapshot);
      showError(data.notice || "더 보여 줄 메뉴가 없어요. [결과 보기]를 눌러 주세요.");
      return;
    }
    // 성공했을 때만 기록을 확정
    state.history.push(snapshot);
    state.round += 1;
    state.selected = new Set(); // 새 라운드는 선택 없이 시작
    renderRound(data.menus, data.notice);
  } catch (err) {
    restoreSnapshot(snapshot); // 실패했으면 누르기 전 상태로 되돌림
    showError(`다음 메뉴를 불러오지 못했어요: ${err.message}`);
  }
}

/** [◀ 이전] : 앞 라운드로 되돌아감. 1라운드에선 시작 화면으로 */
function prevRound() {
  if (state.history.length === 0) {
    showScreen("start");
    return;
  }
  // pop() : 스택의 맨 위(가장 최근) 사진을 꺼냄
  restoreSnapshot(state.history.pop());
  renderRound(state.current);
}

/**
 * [결과 보기] : 지금까지 고른 메뉴 + 지금 화면에서 고른 메뉴 중에서
 *               서버가 처음 입력에 가장 잘 맞는 하나를 골라 "오늘은 이거예요!" 로 보여 줌
 * 라운드 기록(state.basket 등)은 바꾸지 않음 → 결과 화면에서 [이전]을 누르면 라운드 화면이 그대로 남아 있음
 */
async function showFinal() {
  const all = [...state.basket];
  for (const menu of currentPicks()) {
    if (!all.some((m) => m.id === menu.id)) all.push(menu); // some : 하나라도 조건에 맞으면 true
  }

  if (all.length === 0) {
    showError("선택한 메뉴가 없어요. 끌리는 메뉴를 눌러 주세요.");
    return;
  }

  state.finalPicks = all;
  state.recommended = []; // 원 모어 띵크 기록은 결과 화면에 들어올 때마다 새로 시작

  try {
    // liked 에 "결과 화면 기준 고른 메뉴 전체"를 넣어서 보냄
    const data = await post("/api/decide", { ...buildRequest(), liked: all.map((m) => m.id) });
    // { ...객체, 키: 값 } : 펼침 연산자로 복사하면서 liked 만 덮어씀
    renderResult(data.menu);
  } catch (err) {
    showError(`결과를 불러오지 못했어요: ${err.message}`);
  }
}

/**
 * [🤔 원 모어 띵크] : 고른 메뉴 밖에서 다른 음식을 하나 더 추천받아 아래에 쌓음
 * 처음 1~2번은 고른 메뉴와 가까운 메뉴, 그다음부터는 다른 종류의 메뉴 (서버가 결정)
 */
async function oneMore() {
  const btn = $("onemore-btn");
  btn.disabled = true; // 답이 오기 전에 여러 번 누르는 것 방지
  try {
    const data = await post("/api/onemore", {
      ...buildRequest(),
      liked: state.finalPicks.map((m) => m.id),
      recommended: state.recommended,
    });
    if (!data.menu) {
      showError(data.notice || "더 추천할 메뉴가 없어요.");
      return; // 버튼은 비활성화된 채로 둠 (더 없으니까)
    }
    state.recommended.push(data.menu.id);
    const card = createResultCard(data.menu, "onemore");
    $("onemore-list").appendChild(card);
    // scrollIntoView : 새 카드가 보이도록 화면을 부드럽게 스크롤
    // (오래된 브라우저나 테스트 환경엔 없을 수 있어서, 있을 때만 실행)
    if (card.scrollIntoView) card.scrollIntoView({ behavior: "smooth", block: "start" });
    btn.disabled = false;
  } catch (err) {
    showError(`추천을 불러오지 못했어요: ${err.message}`);
    btn.disabled = false;
  }
}

// =============================================================================
// 시작 : 페이지가 열리면 실행되는 부분
// =============================================================================
setupChips();
preselectMeal();

$("start-btn").addEventListener("click", startRounds);
// 화살표 함수로 감싸는 이유: goNext 에 "drill" / "explore" 값을 넘겨 주기 위해
$("next-btn").addEventListener("click", () => goNext("drill"));
$("explore-btn").addEventListener("click", () => goNext("explore"));
$("prev-btn").addEventListener("click", prevRound);
$("result-btn").addEventListener("click", showFinal);
$("onemore-btn").addEventListener("click", oneMore);
// 결과 화면의 [이전] : 마지막 라운드 화면으로 그대로 돌아감 (선택 상태 유지)
$("result-prev-btn").addEventListener("click", () => showScreen("round"));
// 처음부터 다시: 시작 화면으로. 시작 화면에서 고른 값은 그대로 남겨 둠
$("restart-btn").addEventListener("click", () => showScreen("start"));
