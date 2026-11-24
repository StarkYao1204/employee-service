const loginPanel = document.querySelector("#login-panel");
const workspacePanel = document.querySelector("#workspace-panel");
const chatPanel = document.querySelector("#chat-panel");
const emptyChat = document.querySelector("#empty-chat");
const loginForm = document.querySelector("#login-form");
const loginButton = document.querySelector("#login-button");
const chatForm = document.querySelector("#chat-form");
const usernameInput = document.querySelector("#username");
const passwordInput = document.querySelector("#password");
const threadList = document.querySelector("#thread-list");
const threadsLoading = document.querySelector("#threads-loading");
const threadsEmpty = document.querySelector("#threads-empty");
const messagesLoading = document.querySelector("#messages-loading");
const newThreadButton = document.querySelector("#new-thread-button");
const currentUserLabel = document.querySelector("#current-user");
const threadLabel = document.querySelector("#thread-label");
const messageInput = document.querySelector("#message");
const sendButton = document.querySelector("#send-button");
const cancelButton = document.querySelector("#cancel-button");
const messages = document.querySelector("#messages");
const errorMessage = document.querySelector("#error-message");
const confirmationPanel = document.querySelector("#confirmation-panel");
const confirmationContent = document.querySelector("#confirmation-content");
const approveButton = document.querySelector("#approve-button");
const rejectButton = document.querySelector("#reject-button");

const TOKEN_STORAGE_KEY = "access_token";

// localStorage 让 Token 在刷新后继续存在；退出或失效时必须主动删除。
let accessToken = localStorage.getItem(TOKEN_STORAGE_KEY);
let currentThreadId = null;

// 每个会话一套独立状态：events 是渲染buffer，stream 保存运行中的控制器。
// 切换会话只换渲染目标，不 abort 旧流——后端靠 SSE 连接存活继续跑完。
const threadViews = new Map();
let liveTextNode = null; // 当前正在逐字追加的 assistant 节点，切会话/全量重放后失效。

function getView(threadId) {
  if (!threadViews.has(threadId)) {
    threadViews.set(threadId, {
      events: [], // 渲染指令：{kind:"message"|"event"|"text", ...}
      historyLoaded: false,
      confirmation: null,
      stream: null, // { controller, status:"running"|"done"|"waiting_confirmation"|"stopped", hidden, warned }
      queue: [], // 本会话排队待发的问题
    });
  }
  return threadViews.get(threadId);
}

function saveAccessToken(token) {
  accessToken = token;
  localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

function clearAccessToken() {
  accessToken = null;
  localStorage.removeItem(TOKEN_STORAGE_KEY);
}

function authHeaders(extra = {}) {
  const headers = { ...extra };
  // 除登录外的受保护请求才带 Bearer；user_id / role 一律不来自浏览器。
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  return headers;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: authHeaders({
      "Content-Type": "application/json",
      ...(options.headers || {}),
    }),
  });
  const data = await response.json().catch(() => ({}));
  // 401 统一视为登录失效：清 Token、终止所有流、回到登录页。
  if (response.status === 401) {
    logout();
    throw new Error("登录状态已失效，请重新登录");
  }
  if (!response.ok) throw new Error(data.detail || "请求失败");
  return data;
}

function showError(error) {
  errorMessage.textContent = error.message || String(error);
}

function clearError() {
  errorMessage.textContent = "";
}

// —— 以下四个 DOM 追加函数只负责“往当前 #messages 加节点”，渲染由 renderView 统一调度 ——
function appendMessage(role, text = "") {
  const item = document.createElement("div");
  item.className = `message ${role}`;
  item.textContent = text;
  messages.appendChild(item);
  messages.scrollTop = messages.scrollHeight;
  return item;
}

function appendStreamEvent(text, isError = false) {
  const item = document.createElement("div");
  item.className = `stream-event${isError ? " error" : ""}`;
  item.textContent = text;
  messages.appendChild(item);
  messages.scrollTop = messages.scrollHeight;
}

function showConfirmation(confirmation) {
  confirmationPanel.classList.toggle("hidden", !confirmation);
  confirmationContent.textContent = confirmation
    ? JSON.stringify(confirmation, null, 2)
    : "";
}

// 把某个会话的 buffer 重放到 #messages。只有当前会话才真正画，避免串台。
function renderView(threadId) {
  if (threadId !== currentThreadId) return;
  const view = getView(threadId);
  // messages-loading 是 messages 的固定子元素，清空后要放回，靠 hidden 控制显隐。
  messages.replaceChildren(messagesLoading);

  let textNode = null; // 连续的 text_delta 归并到同一个 assistant 气泡。
  for (const item of view.events) {
    if (item.kind === "message") {
      appendMessage(item.role, item.text);
      textNode = null;
    } else if (item.kind === "event") {
      appendStreamEvent(item.text, item.isError);
      textNode = null;
    } else if (item.kind === "text") {
      if (!textNode) textNode = appendMessage("assistant");
      textNode.textContent += item.text;
      messages.scrollTop = messages.scrollHeight;
    }
  }
  showConfirmation(view.confirmation);
  updateStreamingControls(view);
  // 全量重放后，把逐字追加的落点指向重建出的最后一个文本节点。
  liveTextNode = textNode;
}

// 输入框与发送按钮不禁用——同会话运行时允许“排队”。
function updateStreamingControls(view) {
  const running = view.stream?.status === "running";
  cancelButton.classList.toggle("hidden", !running);
  cancelButton.textContent = view.stream?.hidden ? "已在后台运行" : "后台运行";
  cancelButton.disabled = Boolean(view.stream?.hidden);
}

function setLoginLoading(loading) {
  loginButton.disabled = loading;
  usernameInput.disabled = loading;
  passwordInput.disabled = loading;
  loginButton.textContent = loading ? "正在进入…" : "进入工作区";
}

// —— SSE 解析与分帧逻辑保持原有实现，逐字未动 ——
function parseSseBlock(block) {
  let event = "message";
  const dataLines = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  return { event, data: JSON.parse(dataLines.join("\n")) };
}

async function readSse(response, onEvent) {
  if (!response.body) throw new Error("浏览器不支持读取流式响应");
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      if (block.trim()) onEvent(parseSseBlock(block));
      boundary = buffer.indexOf("\n\n");
    }
  }
}

function setThreadsState(state) {
  // 列表状态切换：loading / empty / ready 三态互斥。
  threadsLoading.classList.toggle("hidden", state !== "loading");
  threadsEmpty.classList.toggle("hidden", state !== "empty");
  threadList.classList.toggle("hidden", state !== "ready");
}

// 卡片状态标记：运行中 / 待确认 / 排队中，按会话视图实时刷新。
function updateThreadCardStatus(threadId) {
  const card = threadList.querySelector(
    `.thread-card[data-thread-id="${CSS.escape(threadId)}"]`,
  );
  if (!card) return;
  const badge = card.querySelector(".thread-status");
  if (!badge) return;
  const view = threadViews.get(threadId);
  const stream = view?.stream;
  let label = "";
  let tone = "";
  if (stream?.status === "running") {
    label = "运行中";
    tone = "running";
  } else if (view?.confirmation) {
    label = "待确认";
    tone = "pending";
  } else if (view?.queue?.length) {
    label = `排队中 ${view.queue.length}`;
    tone = "queued";
  }
  badge.textContent = label;
  badge.className = `thread-status${label ? ` ${tone}` : " hidden"}`;
}

function updateAllThreadCardStatus() {
  for (const threadId of threadViews.keys()) updateThreadCardStatus(threadId);
}

function renderThreadCard(thread) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "thread-card";
  button.dataset.threadId = thread.thread_id;
  // 卡片内容全部用 textContent 写入，不拼接 HTML。
  const createdAt = new Date(`${thread.created_at}Z`).toLocaleString();
  const title = document.createElement("span");
  title.className = "thread-card-title";
  title.textContent = createdAt;
  const shortId = document.createElement("span");
  shortId.className = "thread-card-id";
  shortId.textContent = thread.thread_id.slice(0, 8);
  const badge = document.createElement("span");
  badge.className = "thread-status hidden";
  button.append(title, shortId, badge);
  if (thread.thread_id === currentThreadId) button.classList.add("active");
  return button;
}

async function refreshThreads() {
  setThreadsState("loading");
  try {
    const threads = await requestJson("/api/threads");
    threadList.replaceChildren();
    for (const thread of threads) threadList.appendChild(renderThreadCard(thread));
    setThreadsState(threads.length ? "ready" : "empty");
    updateAllThreadCardStatus();
  } catch (error) {
    setThreadsState("ready");
    throw error;
  }
}

async function openThread(threadId, loadHistory = true) {
  // 切换会话不 abort 旧流：旧流继续在后台跑，事件写进自己的 buffer。
  currentThreadId = threadId;
  const view = getView(threadId);
  threadLabel.textContent = `Thread：${threadId}`;
  emptyChat.classList.add("hidden");
  chatPanel.classList.remove("hidden");
  // 选中态随当前会话移动。
  for (const card of threadList.querySelectorAll(".thread-card")) {
    card.classList.toggle("active", card.dataset.threadId === threadId);
  }

  if (loadHistory && !view.historyLoaded) {
    view.historyLoaded = true;
    messagesLoading.classList.remove("hidden");
    try {
      const history = await requestJson(
        `/api/thread/${encodeURIComponent(threadId)}/messages`,
      );
      // 历史消息插到 buffer 最前面，之后才是本轮流的事件。
      const historyEvents = history.messages.map((m) => ({
        kind: "message",
        role: m.role,
        text: m.content,
      }));
      view.events.unshift(...historyEvents);
      view.confirmation = history.confirmation;
      if (history.messages.length === 0) {
        view.events.push({ kind: "event", text: "这段会话还没有消息，可以开始提问。" });
      }
    } catch (error) {
      showError(error);
    } finally {
      messagesLoading.classList.add("hidden");
    }
  } else if (!loadHistory) {
    view.events.push({ kind: "event", text: "新会话已创建，可以开始提问。" });
  }
  renderView(threadId);
  updateThreadCardStatus(threadId);
}

// 单个 SSE 事件 → 写入对应会话的 buffer（不直接碰 DOM）。
function handleStreamEvent(threadId, stream, event, data) {
  const view = getView(threadId);
  // 点了“后台运行”：展示类事件不再写入，但确认/结束状态仍要记录。
  if (stream.hidden) {
    if (event === "confirmation") {
      view.confirmation = data;
      updateThreadCardStatus(threadId);
    }
    if (event === "done") {
      stream.status = data.status === "waiting_confirmation" ? "waiting_confirmation" : "done";
      updateThreadCardStatus(threadId);
    }
    return;
  }

  // 文本增量：当前会话直接往同一节点追加，保持逐字节奏；后台会话只写 buffer。
  if (event === "text_delta") {
    view.events.push({ kind: "text", text: data.text });
    if (threadId === currentThreadId) {
      if (!liveTextNode || !liveTextNode.isConnected) liveTextNode = appendMessage("assistant");
      liveTextNode.textContent += data.text;
      messages.scrollTop = messages.scrollHeight;
    }
    return;
  }
  // 非文本事件会打断连续文本，下一片 text_delta 要新建节点（只影响当前会话）。
  if (threadId === currentThreadId) liveTextNode = null;

  if (event === "status") view.events.push({ kind: "event", text: data.message });
  if (event === "tool_start") view.events.push({ kind: "event", text: `正在调用：${data.label}` });
  if (event === "tool_end") view.events.push({ kind: "event", text: `${data.label} 已返回结果` });
  if (event === "tool_error") view.events.push({ kind: "event", text: data.message, isError: true });
  if (event === "confirmation") {
    view.confirmation = data;
    updateThreadCardStatus(threadId);
  }
  if (event === "done") {
    stream.status = data.status === "waiting_confirmation" ? "waiting_confirmation" : "done";
    updateThreadCardStatus(threadId);
  }
  // 错误作为普通事件记录，不 throw——让流跑完，避免半截 tool_calls 落盘。
  if (event === "error") view.events.push({ kind: "event", text: data.message || "调用出错", isError: true });
  renderView(threadId);
}

// 本轮结束后自动发送排队的问题；待确认时先提示用户处理确认。
function drainQueue(threadId) {
  const view = getView(threadId);
  if (!view || view.stream?.status === "running") return;
  if (view.confirmation) {
    if (view.queue.length && !view.stream?.warned) {
      if (view.stream) view.stream.warned = true;
      view.events.push({ kind: "event", text: "本轮等待确认，请先批准或拒绝后再提问。" });
      renderView(threadId);
    }
    updateThreadCardStatus(threadId);
    return;
  }
  if (view.queue.length === 0) {
    updateThreadCardStatus(threadId);
    return;
  }
  const next = view.queue.shift();
  startStream(threadId, next, true); // true：用户气泡排队时已画过，避免重复追加。
}

async function startStream(threadId, message, bubbleShown = false) {
  const view = getView(threadId);
  if (!bubbleShown) view.events.push({ kind: "message", role: "user", text: message });
  const controller = new AbortController();
  const stream = { controller, status: "running", hidden: false, warned: false };
  view.stream = stream;
  updateThreadCardStatus(threadId);
  renderView(threadId);

  let response;
  try {
    response = await fetch(
      `/api/thread/${encodeURIComponent(threadId)}/chat/stream`,
      {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ message }),
        signal: controller.signal,
      },
    );
  } catch (error) {
    if (error.name !== "AbortError") {
      view.events.push({ kind: "event", text: "网络异常，请求发送失败", isError: true });
    }
    stream.status = "done";
    renderView(threadId);
    updateThreadCardStatus(threadId);
    return;
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    if (response.status === 401) {
      logout();
      return;
    }
    view.events.push({ kind: "event", text: error.detail || "请求失败", isError: true });
    stream.status = "done";
    renderView(threadId);
    updateThreadCardStatus(threadId);
    return;
  }

  try {
    await readSse(response, ({ event, data }) => handleStreamEvent(threadId, stream, event, data));
  } catch (error) {
    if (error.name !== "AbortError") {
      view.events.push({ kind: "event", text: "接收结果时出错", isError: true });
    }
  } finally {
    if (stream.status === "running") stream.status = "done";
    renderView(threadId);
    // SSE 读完意味着服务端 generator 已结束、并发锁已释放，此时发排队消息不会 409。
    drainQueue(threadId);
  }
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();
  setLoginLoading(true);
  try {
    // 登录走表单编码，不带 Authorization；成功后才把 Token 写入 localStorage。
    const body = new URLSearchParams({
      username: usernameInput.value.trim(),
      password: passwordInput.value,
    });
    const response = await fetch("/api/auth/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    const token = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(token.detail || "登录失败");

    saveAccessToken(token.access_token);
    const currentUser = await requestJson("/api/auth/me");
    currentUserLabel.textContent = `${currentUser.display_name}（${currentUser.role}）`;
    await refreshThreads();
    passwordInput.value = "";
    loginPanel.classList.add("hidden");
    workspacePanel.classList.remove("hidden");
  } catch (error) {
    clearAccessToken();
    showError(error);
  } finally {
    setLoginLoading(false);
  }
});

newThreadButton.addEventListener("click", async () => {
  clearError();
  newThreadButton.disabled = true;
  try {
    const thread = await requestJson("/api/threads", { method: "POST" });
    await refreshThreads();
    await openThread(thread.thread_id, false);
  } catch (error) {
    showError(error);
  } finally {
    newThreadButton.disabled = false;
  }
});

// 卡片列表用事件委托：点击任意卡片即打开对应会话（不打断该会话的后台流）。
threadList.addEventListener("click", (event) => {
  const card = event.target.closest(".thread-card");
  if (!card) return;
  clearError();
  openThread(card.dataset.threadId).catch(showError);
});

chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = messageInput.value.trim();
  if (!message || !currentThreadId) return;
  messageInput.value = "";
  clearError();

  const view = getView(currentThreadId);
  if (view.stream?.status === "running") {
    // 同会话本轮仍在跑：气泡先画出来，问题排到队列，连接保持不中断。
    view.queue.push(message);
    view.events.push({ kind: "message", role: "user", text: message });
    view.events.push({ kind: "event", text: "已排队，本轮结束后自动发送" });
    renderView(currentThreadId);
    updateThreadCardStatus(currentThreadId);
    return;
  }
  startStream(currentThreadId, message);
});

// 停止 = 转为后台运行：连接不断、后端继续跑完，只是不再显示本轮结果。
cancelButton.addEventListener("click", () => {
  const view = getView(currentThreadId);
  if (!view || view.stream?.status !== "running") return;
  view.stream.hidden = true;
  view.stream.warned = false;
  view.events.push({ kind: "event", text: "本轮已转后台运行，完成后可继续提问" });
  renderView(currentThreadId);
});

async function submitConfirmation(approved) {
  clearError();
  approveButton.disabled = true;
  rejectButton.disabled = true;
  try {
    // 确认请求体只包含 approved；待确认状态由服务端判定。
    const reply = await requestJson(
      `/api/thread/${encodeURIComponent(currentThreadId)}/confirm`,
      { method: "POST", body: JSON.stringify({ approved }) },
    );
    const view = getView(currentThreadId);
    view.confirmation = null;
    if (view.stream) view.stream.status = "done";
    if (reply.answer) view.events.push({ kind: "message", role: "assistant", text: reply.answer });
    renderView(currentThreadId);
    updateThreadCardStatus(currentThreadId);
    drainQueue(currentThreadId);
  } catch (error) {
    showError(error);
  } finally {
    approveButton.disabled = false;
    rejectButton.disabled = false;
  }
}

approveButton.addEventListener("click", () => submitConfirmation(true));
rejectButton.addEventListener("click", () => submitConfirmation(false));

function logout() {
  // 退出必须掐断所有后台流：Token 已失效，不能再有请求挂着或往界面写结果。
  for (const view of threadViews.values()) view.stream?.controller.abort();
  threadViews.clear();
  currentThreadId = null;
  messages.replaceChildren(messagesLoading);
  threadList.replaceChildren();
  setThreadsState("empty");
  confirmationPanel.classList.add("hidden");
  chatPanel.classList.add("hidden");
  emptyChat.classList.remove("hidden");
  workspacePanel.classList.add("hidden");
  loginPanel.classList.remove("hidden");
  setLoginLoading(false);
  clearError();
}

document.querySelector("#thread-logout-button").addEventListener("click", logout);

async function restoreLogin() {
  if (!accessToken) return;

  try {
    // 本地有 Token 不等于可信，必须由服务端重新验证身份。
    const currentUser = await requestJson("/api/auth/me");
    currentUserLabel.textContent = `${currentUser.display_name}（${currentUser.role}）`;
    await refreshThreads();
    loginPanel.classList.add("hidden");
    workspacePanel.classList.remove("hidden");
  } catch (error) {
    clearAccessToken();
    showError(new Error("登录状态已失效，请重新登录"));
  }
}

restoreLogin();
