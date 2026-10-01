// =============================================================================
// app.js - 채팅 화면의 동작(로직)을 담당하는 자바스크립트
//
// 하는 일:
//   1) 사용자가 입력창에 글을 쓰고 [보내기]를 누르면
//   2) 화면에 내 말풍선을 추가하고
//   3) 백엔드 서버(main.py)에 지금까지의 대화를 보낸 뒤
//   4) 받은 AI 답변을 말풍선으로 보여 줍니다.
//
// HTML(index.html) = 화면의 뼈대, CSS(style.css) = 꾸미기, JS(이 파일) = 움직임
// =============================================================================

// 백엔드 API 주소.
// docker-compose.yml 에서 백엔드 컨테이너의 8000번 포트를 내 PC의 8001번에 연결해 두었기 때문에 8001 입니다.
// const : 다시 바꿀 수 없는 변수(상수) 선언
const API_URL = "http://localhost:8001/api/chat";

// ---- HTML 요소 가져오기 ----
// document.getElementById("id") : index.html 에서 id="..." 로 표시한 요소를 찾아옵니다.
// 이름 끝의 El 은 "Element(요소)" 라는 뜻으로 붙인 것 (변수 이름 짓는 습관)
const chatEl = document.getElementById("chat");        // 말풍선들이 쌓이는 대화 영역 <main id="chat">
const formEl = document.getElementById("chat-form");   // 입력창 + 버튼을 감싼 <form>
const inputEl = document.getElementById("chat-input"); // 글자를 입력하는 <input>

// 지금까지의 대화 기록을 저장하는 배열.
// AI(LLM)는 이전 대화를 스스로 기억하지 못하기 때문에, 매번 "대화 전체"를 서버로 보내야
// "아까 말한 그거 말고 다른 거" 같은 말도 이해할 수 있습니다.
// 예) [{ role: "user", content: "점심 추천" }, { role: "assistant", content: "김치찌개..." }]
const history = [];

/**
 * 대화 영역에 말풍선 하나를 추가하는 함수
 * @param {string} role - "user"(내 말) 또는 그 외(AI 말)
 * @param {string} text - 말풍선에 넣을 글자
 * @returns {HTMLDivElement} 만든 말풍선 요소 (나중에 글자를 바꾸려고 돌려줌)
 */
function addBubble(role, text) {
  // 새 <div> 요소를 메모리에 만듦 (아직 화면에는 안 보임)
  const div = document.createElement("div");

  // CSS 클래스 지정. 템플릿 문자열(백틱 `)의 ${ } 안에 값을 넣을 수 있습니다.
  // 삼항 연산자: 조건 ? 참일때값 : 거짓일때값
  // → role이 "user"면 "bubble user"(오른쪽 주황색), 아니면 "bubble bot"(왼쪽 회색)  ※ style.css 참고
  div.className = `bubble ${role === "user" ? "user" : "bot"}`;

  // textContent 로 글자를 넣음.
  // innerHTML 을 쓰면 AI 답변 안의 <태그>가 진짜 HTML로 실행될 수 있어 위험(XSS)하므로 textContent 가 안전합니다.
  div.textContent = text;

  // 대화 영역 맨 끝에 붙임 → 이제 화면에 보임
  chatEl.appendChild(div);

  // 스크롤을 맨 아래로 내려서 새 말풍선이 보이게 함
  // scrollHeight = 내용 전체 높이, scrollTop = 현재 스크롤 위치
  chatEl.scrollTop = chatEl.scrollHeight;

  return div;
}

// 페이지가 열리자마자 AI의 첫 인사 말풍선을 보여 줌.
// (이 인사말은 history 에 넣지 않으므로 서버로는 보내지지 않습니다)
addBubble("bot", "안녕하세요! 오늘 어떤 메뉴가 궁금하세요? 기분이나 재료, 인원수를 알려주시면 추천해드릴게요.");

// ---- [보내기] 버튼 또는 Enter 키를 눌렀을 때 실행될 코드 등록 ----
// addEventListener("submit", 함수) : form 이 제출(submit)될 때 함수를 실행해 달라고 등록
// async (e) => { } : 화살표 함수 + async. 안에서 await 로 서버 응답을 기다릴 수 있습니다.
// e : 이벤트 정보가 담긴 객체
formEl.addEventListener("submit", async (e) => {
  // form 은 원래 제출하면 페이지를 새로고침합니다. 그러면 대화가 다 날아가므로 막습니다.
  e.preventDefault();

  // 입력값 앞뒤 공백 제거
  const text = inputEl.value.trim();
  // 빈 문자열이면 아무것도 하지 않고 함수 종료
  if (!text) return;

  // 내 말풍선을 화면에 추가하고, 대화 기록에도 저장
  addBubble("user", text);
  history.push({ role: "user", content: text });

  // 입력창 비우기 + 답변이 올 때까지 입력 막기 (중복 전송 방지)
  inputEl.value = "";
  inputEl.disabled = true;

  // 답변을 기다리는 동안 보여 줄 임시 말풍선. 나중에 글자만 진짜 답변으로 바꿉니다.
  const pending = addBubble("bot", "생각 중...");

  // try / catch / finally : 에러 처리 구문
  //   try     - 실행해 볼 코드
  //   catch   - try 안에서 에러가 나면 실행
  //   finally - 성공하든 실패하든 마지막에 항상 실행
  try {
    // fetch : 브라우저에서 서버로 HTTP 요청을 보내는 기본 함수
    // await : 서버 응답이 올 때까지 기다림 (CPU로 LLM을 돌리면 수십 초 걸릴 수 있음)
    const res = await fetch(API_URL, {
      method: "POST",                                     // 데이터를 보내는 요청이므로 POST
      headers: { "Content-Type": "application/json" },    // "보내는 데이터는 JSON 형식이에요" 라고 알림
      body: JSON.stringify({ messages: history }),        // JS 객체 → JSON 문자열로 변환해서 전송
                                                          // main.py 의 ChatRequest 모양과 똑같아야 함!
    });

    // res.ok : 상태 코드가 200~299 이면 true (성공)
    if (!res.ok) {
      // 실패했을 때 서버가 보낸 에러 내용({"detail": "..."})을 읽음.
      // 혹시 JSON이 아니어서 읽기에 실패하면 .catch 로 빈 객체 {} 를 대신 사용
      const err = await res.json().catch(() => ({}));
      // throw : 에러를 일부러 발생시킴 → 아래 catch 블록으로 바로 이동
      // A || B : A가 비어 있으면(undefined 등) B를 사용
      throw new Error(err.detail || `서버 오류 (${res.status})`);
    }

    // 성공: 응답 JSON을 JS 객체로 변환. 모양은 { reply: "답변..." } (main.py 의 ChatResponse)
    const data = await res.json();
    // "생각 중..." 말풍선의 글자를 진짜 답변으로 교체
    pending.textContent = data.reply;
    // AI 답변도 대화 기록에 저장 → 다음 질문 때 함께 보내져서 AI가 문맥을 이해함
    history.push({ role: "assistant", content: data.reply });
  } catch (err) {
    // 네트워크 오류(백엔드 꺼짐 등)나 위에서 throw 한 에러를 말풍선에 표시
    pending.textContent = `오류: ${err.message}`;
  } finally {
    // 성공이든 실패든 입력창을 다시 쓸 수 있게 풀어 주고, 커서를 입력창에 둠
    inputEl.disabled = false;
    inputEl.focus();
  }
});
