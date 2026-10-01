// =============================================================================
// app.js - 화면의 동작(로직)                                   버전: test 1.0
//
// 흐름:
//   ① 시작 화면  : 식사 시간(자동 선택) / 기분 / 인원수 / 재료 → [메뉴 보기]
//   ② 라운드 화면: 메뉴 5개 중 끌리는 것 클릭 → [다음] → 안 누른 메뉴는 빠지고 새 메뉴로 채워짐
//                  [◀ 이전] 으로 앞 라운드에 돌아갈 수 있음 (최대 4라운드, 중간에 [결과 보기] 가능)
//   ③ 결과 화면  : 내가 고른 메뉴들 (오래 남아 있던 순서)
//
// 역할 분담:
//   - 이 파일(브라우저) : 화면 바꾸기, 클릭 기록 들고 있기, 결과 화면 만들기
//   - 서버(main.py → recommender.py) : 기록을 받아서 성향 계산, 다음 메뉴 고르기
//   서버는 아무것도 기억하지 않으므로, 기록(state)은 전부 브라우저가 들고 있다가 매번 보냅니다.
//
// 성향 분석 결과는 화면에 보여 주지 않습니다. ("분석당하는 느낌"을 주지 않기 위해)
// 분석은 뒤에서 "다음에 어떤 메뉴를 보여 줄지" 고르는 데만 쓰입니다.
// =============================================================================

// 백엔드 주소. docker-compose.yml 에서 백엔드 컨테이너를 내 PC의 8001번 포트에 연결해 둠
const API_BASE = "http://localhost:8001";

// 최대 라운드 수. 이 라운드에서 [다음]을 누르면 결과 화면으로 넘어감
const MAX_ROUNDS = 4;

// =============================================================================
// 상태(state) : 지금 앱이 기억하고 있는 모든 것을 한 객체에 모아 둠
// 화면은 이 상태를 "그려 주는 것" 일 뿐이라고 생각하면 이해하기 쉽습니다.
// =============================================================================
const state = {
  // ---- 독립변수 (시작 화면에서 고름) ----
  meal: null,       // "아침" / "점심" / "저녁" / "야식"
  mood: null,       // 선택 안 하면 null
  people: null,     // 선택 안 하면 null
  ingredient: "",   // 재료 입력값

  // ---- 진행 기록 ----
  round: 0,         // 현재 라운드 번호
  liked: [],        // 지금까지 끌려서 클릭한 메뉴 id 목록
  shown: [],        // 지금까지 화면에 보여 준 모든 메뉴 id 목록
  current: [],      // 지금 화면에 떠 있는 메뉴들 (서버가 준 메뉴 객체 그대로)

  // Set(집합): 중복 없이 값을 모아 두는 자료형. add / delete / has 로 쉽게 넣고 빼고 확인 가능
  // 이번 라운드에서 클릭(✓)한 메뉴 id
  selected: new Set(),

  // 메뉴별로 "몇 번의 [다음]을 살아남았나" 를 세는 표.  예) { 1: 3, 9: 1 } → 1번 메뉴는 3라운드 동안 남아 있었음
  // 결과 화면에서 오래 남은 메뉴를 위로 올릴 때 사용
  keptCount: {},

  // [◀ 이전] 을 위한 기록 보관함 (스택)
  // [다음] 을 누를 때마다 "그 순간의 상태 사진(스냅샷)" 을 맨 위에 쌓고,
  // [이전] 을 누르면 맨 위의 사진을 꺼내서 그대로 되돌립니다.
  // 스택 = 나중에 넣은 것을 먼저 꺼내는 자료 구조 (접시 쌓기와 같음). push 로 넣고 pop 으로 꺼냄
  history: [],
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
  // Object.entries(객체) : {키: 값} 을 [[키, 값], ...] 배열로 바꿔 줌 → 반복문 돌리기 좋음
  for (const [key, el] of Object.entries(screens)) {
    el.hidden = key !== name; // hidden = true 면 숨김
  }
  hideError();
}

/** 현재 시각으로 식사 시간을 추측 (시작 화면에서 미리 선택해 두기 위함) */
function guessMeal() {
  const hour = new Date().getHours(); // 0~23시 (사용자 기기의 시계)
  if (hour >= 5 && hour < 10) return "아침";
  if (hour >= 10 && hour < 15) return "점심";
  if (hour >= 15 && hour < 21) return "저녁";
  return "야식"; // 21시 ~ 다음 날 5시
}

/** 서버에 보낼 데이터 만들기 (main.py 의 RecommendRequest 모양과 똑같아야 함) */
function buildRequest(keep = []) {
  const now = new Date();
  return {
    meal: state.meal,
    mood: state.mood,
    people: state.people,
    ingredient: state.ingredient,
    month: now.getMonth() + 1, // getMonth() 는 0~11 이라서 +1 → 1~12
    weekday: now.getDay(),     // 0=일요일 ~ 6=토요일
    liked: state.liked,
    shown: state.shown,
    keep: keep,
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
    // 서버가 실패 응답을 보낸 경우 → throw 로 에러를 일으켜 호출한 쪽의 catch 로 넘김
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
 * 그냥 state.liked 를 넣으면 "같은 배열"을 가리키게 되어, 나중에 state.liked 가 바뀌면 사진도 같이 바뀝니다.
 * 그래서 [...배열], {...객체} 로 "복사본"을 만들어 저장합니다. (얕은 복사)
 */
function takeSnapshot() {
  return {
    round: state.round,
    current: [...state.current],
    selected: [...state.selected], // Set → 배열로 복사
    liked: [...state.liked],
    shown: [...state.shown],
    keptCount: { ...state.keptCount },
  };
}

/** 스냅샷으로 상태를 되돌림 */
function restoreSnapshot(snap) {
  state.round = snap.round;
  state.current = snap.current;
  state.selected = new Set(snap.selected); // 배열 → 다시 Set 으로
  state.liked = snap.liked;
  state.shown = snap.shown;
  state.keptCount = snap.keptCount;
}

/**
 * 메뉴 카드 하나를 만듦 (그림 + 이름만. 분석 문구는 보여 주지 않음)
 * @param {object} menu - 서버가 준 메뉴 { id, name, emoji, tags }
 * @param {boolean} clickable - true 면 클릭해서 선택(✓) 가능 (라운드 화면), false 면 보기만 (결과 화면)
 */
function createCard(menu, clickable) {
  // 라운드 화면에선 누를 수 있어야 하므로 button, 결과 화면에선 div
  const card = document.createElement(clickable ? "button" : "div");
  card.className = "menu-card";
  if (clickable) card.type = "button";

  // textContent 로 넣는 이유: innerHTML 은 글자 속 HTML 이 실행될 수 있어 위험(XSS)
  const emoji = document.createElement("span");
  emoji.className = "emoji";
  emoji.textContent = menu.emoji;

  const name = document.createElement("span");
  name.className = "name";
  name.textContent = menu.name;

  // append : 여러 요소를 한 번에 자식으로 붙임
  card.append(emoji, name);

  if (clickable) {
    // 이미 선택된 메뉴(이전 라운드에서 남긴 것 / [이전]으로 돌아온 것)는 ✓ 상태로 시작
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
      hideError(); // "선택해 주세요" 안내가 떠 있었다면 지움
    });
  }
  return card;
}

// =============================================================================
// 화면 그리기
// =============================================================================

/** 라운드 화면에 메뉴 카드들을 그림 */
function renderRound(menus) {
  state.current = menus;

  // 새로 보여 주는 메뉴 id 를 "보여 준 목록"에 추가 (중복 없이)
  for (const menu of menus) {
    if (!state.shown.includes(menu.id)) state.shown.push(menu.id);
  }

  $("round-label").textContent = `라운드 ${state.round} / ${MAX_ROUNDS}`;
  // 1라운드에선 돌아갈 라운드가 없으니 "처음으로" (시작 화면), 그 뒤로는 "이전"
  $("prev-btn").textContent = state.round === 1 ? "◀ 처음으로" : "◀ 이전";
  // 마지막 라운드에선 [다음] 대신 [결과 보기 ▶] 로 글자를 바꿔 줌
  $("next-btn").textContent = state.round >= MAX_ROUNDS ? "결과 보기 ▶" : "다음 ▶";

  const list = $("menu-list");
  list.replaceChildren(); // 기존 카드를 모두 지움
  for (const menu of menus) {
    list.appendChild(createCard(menu, true));
  }
  showScreen("round");
}

/** 결과 화면: 내가 고른 메뉴들을 오래 남아 있던 순서로 보여 줌 */
function renderResult(menus) {
  $("result-title").textContent = `내가 고른 메뉴 ${menus.length}개`;
  const list = $("result-list");
  list.replaceChildren();
  // forEach((값, 순서번호) => ...) : 순서번호(index)도 함께 받을 수 있음 → 1위 표시에 사용
  menus.forEach((menu, index) => {
    const card = createCard(menu, false);
    if (index === 0) card.classList.add("best"); // 가장 오래 남은 메뉴는 강조
    list.appendChild(card);
  });
  showScreen("result");
}

// =============================================================================
// 버튼 동작
// =============================================================================

/** 시작 화면의 버튼 묶음(chips)이 "하나만 선택" 되도록 설정 */
function setupChips() {
  // querySelectorAll(CSS선택자) : 조건에 맞는 요소를 모두 찾음
  // ".chips" = class="chips" 인 요소들 (식사 시간 / 기분 / 인원수 묶음)
  for (const group of document.querySelectorAll(".chips")) {
    const key = group.dataset.group; // data-group="meal" → "meal" (state 의 어떤 칸인지)

    group.addEventListener("click", (e) => {
      // 이벤트 위임: 묶음(부모)에 한 번만 등록해 두고, 실제로 눌린 버튼은 e.target 으로 찾음
      // closest("button") : 버튼 안의 글자를 눌러도 버튼 자신을 찾아 줌
      const btn = e.target.closest("button");
      if (!btn) return;

      const value = btn.dataset.value;
      // 이미 선택된 걸 또 누르면 선택 해제 (선택 항목이니까 안 고를 수도 있게)
      // 단, 식사 시간(meal)은 꼭 하나 필요하므로 해제하지 않음
      const unselect = state[key] === value && key !== "meal";
      state[key] = unselect ? null : value;

      // 묶음 안의 버튼 중 선택된 것만 active 클래스 → CSS 로 색칠
      for (const b of group.querySelectorAll("button")) {
        b.classList.toggle("active", b.dataset.value === state[key]);
      }
    });
  }
}

/** 식사 시간 버튼을 현재 시각에 맞게 미리 선택해 둠 */
function preselectMeal() {
  state.meal = guessMeal();
  // 속성 선택자: data-group 이 meal 인 묶음 안에서, data-value 가 state.meal 인 버튼
  const btn = document.querySelector(`[data-group="meal"] [data-value="${state.meal}"]`);
  if (btn) btn.classList.add("active");
}

/** [메뉴 보기] : 첫 라운드 시작 (기록을 모두 새로 시작) */
async function startRounds() {
  state.ingredient = $("ingredient").value.trim();
  state.round = 1;
  state.liked = [];
  state.shown = [];
  state.selected = new Set();
  state.keptCount = {};
  state.history = [];

  try {
    const data = await post("/api/round", buildRequest());
    renderRound(data.menus);
  } catch (err) {
    showError(`메뉴를 불러오지 못했어요: ${err.message} (백엔드가 켜져 있는지 확인하세요)`);
  }
}

/**
 * 이번 라운드에서 클릭한 것을 기록에 반영
 * - 선택(✓)한 메뉴는 liked 에 추가
 * - 이전에 끌렸지만 이번에 선택을 풀었다면 liked 에서 제거 ("이제는 아니다"로 마음이 바뀐 것)
 */
function commitSelection() {
  const currentIds = state.current.map((m) => m.id);
  // filter : 조건이 true 인 것만 남김
  state.liked = state.liked.filter(
    (id) => !currentIds.includes(id) || state.selected.has(id)
  );
  for (const id of state.selected) {
    if (!state.liked.includes(id)) state.liked.push(id);
  }
}

/** [다음] : 선택한 것은 남기고, 나머지는 새 메뉴로 교체 */
async function nextRound() {
  // 마지막 라운드였으면 결과로
  if (state.round >= MAX_ROUNDS) {
    return showFinal();
  }

  // [이전] 으로 돌아올 수 있도록, 바뀌기 전 상태를 사진 찍어 둠
  const snapshot = takeSnapshot();
  commitSelection();

  // 이번에 선택한 메뉴들 = 다음 라운드에도 그대로 남길 메뉴
  // [...Set] : 펼침 연산자로 Set 을 배열로 바꿈
  const keep = [...state.selected];

  try {
    const data = await post("/api/round", buildRequest(keep));

    // 성공했을 때만 기록을 확정
    state.history.push(snapshot);
    for (const id of keep) {
      // (값 || 0) : 아직 기록이 없으면(undefined) 0 으로 보고 +1
      state.keptCount[id] = (state.keptCount[id] || 0) + 1;
    }
    state.round += 1;
    state.selected = new Set(keep); // 남긴 메뉴는 다음 화면에서도 ✓ 상태 유지
    renderRound(data.menus);
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
 * [결과 보기] : 지금 선택(✓)되어 있는 메뉴들로 결과 화면을 만듦
 * 서버에 물어볼 필요 없이, 브라우저가 가진 기록만으로 만들 수 있음
 */
function showFinal() {
  commitSelection();

  // 지금 화면의 메뉴 중 선택된 것만
  const picked = state.current.filter((m) => state.selected.has(m.id));

  if (picked.length === 0) {
    showError("선택한 메뉴가 없어요. 끌리는 메뉴를 눌러 주세요.");
    return;
  }

  // 정렬 기준 1: 오래 살아남은 메뉴가 위로 (keptCount 큰 순)
  // 정렬 기준 2: 같으면 먼저 클릭했던 메뉴가 위로 (liked 배열 안의 순서)
  // sort((a, b) => 숫자) : 숫자가 음수면 a 가 앞, 양수면 b 가 앞
  picked.sort(
    (a, b) =>
      (state.keptCount[b.id] || 0) - (state.keptCount[a.id] || 0) ||
      state.liked.indexOf(a.id) - state.liked.indexOf(b.id)
  );
  renderResult(picked);
}

// =============================================================================
// 시작 : 페이지가 열리면 실행되는 부분
// =============================================================================
setupChips();
preselectMeal();

$("start-btn").addEventListener("click", startRounds);
$("next-btn").addEventListener("click", nextRound);
$("prev-btn").addEventListener("click", prevRound);
$("result-btn").addEventListener("click", showFinal);
// 결과 화면의 [이전] : 마지막 라운드 화면으로 그대로 돌아감 (선택 상태 유지)
$("result-prev-btn").addEventListener("click", () => showScreen("round"));
// 처음부터 다시: 시작 화면으로. 시작 화면에서 고른 값은 그대로 남겨 둠 (다시 고르기 편하게)
$("restart-btn").addEventListener("click", () => showScreen("start"));
