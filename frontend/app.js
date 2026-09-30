const API_URL = "http://localhost:8001/api/chat";

const chatEl = document.getElementById("chat");
const formEl = document.getElementById("chat-form");
const inputEl = document.getElementById("chat-input");

const history = [];

function addBubble(role, text) {
  const div = document.createElement("div");
  div.className = `bubble ${role === "user" ? "user" : "bot"}`;
  div.textContent = text;
  chatEl.appendChild(div);
  chatEl.scrollTop = chatEl.scrollHeight;
  return div;
}

addBubble("bot", "안녕하세요! 오늘 어떤 메뉴가 궁금하세요? 기분이나 재료, 인원수를 알려주시면 추천해드릴게요.");

formEl.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = inputEl.value.trim();
  if (!text) return;

  addBubble("user", text);
  history.push({ role: "user", content: text });
  inputEl.value = "";
  inputEl.disabled = true;

  const pending = addBubble("bot", "생각 중...");

  try {
    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: history }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `서버 오류 (${res.status})`);
    }

    const data = await res.json();
    pending.textContent = data.reply;
    history.push({ role: "assistant", content: data.reply });
  } catch (err) {
    pending.textContent = `오류: ${err.message}`;
  } finally {
    inputEl.disabled = false;
    inputEl.focus();
  }
});
