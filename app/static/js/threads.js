const $ = (sel) => document.querySelector(sel);

function showError(msg) {
  const el = $("#threadsError");
  if (!el) return;
  el.style.display = "block";
  el.textContent = msg;
}
function clearError() {
  const el = $("#threadsError");
  if (!el) return;
  el.style.display = "none";
  el.textContent = "";
}

async function apiJson(url, opts = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed: ${res.status}`);
  return data;
}

function fmtKstFromEpochSeconds(epochSec) {
  if (!epochSec) return "-";
  try {
    return new Date(epochSec * 1000).toLocaleString("ko-KR", {
      timeZone: "Asia/Seoul",
    });
  } catch {
    return String(epochSec);
  }
}

function fmtKstFromIso(iso) {
  if (!iso) return "-";
  try {
    return new Date(iso).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
  } catch {
    return String(iso);
  }
}

async function loadChannelsIntoSelect() {
  const sel = $("#channelSelect");
  sel.innerHTML = "";
  const all = await apiJson("/api/channels");
  const active = all.filter((c) => c.is_active);

  if (!active.length) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "활성 채널 없음 (Channels에서 추가/활성화)";
    sel.appendChild(opt);
    sel.disabled = true;
    return [];
  }

  sel.disabled = false;
  for (const ch of active) {
    const opt = document.createElement("option");
    opt.value = ch.channel_id;
    const label = ch.name ? `#${ch.name} (${ch.channel_id})` : ch.channel_id;
    opt.textContent = label;
    sel.appendChild(opt);
  }
  return active;
}

function renderThreadsList(channelId, rows) {
  const container = $("#threadsList");
  container.classList.remove("muted");
  container.innerHTML = "";

  if (!rows.length) {
    container.classList.add("muted");
    const msg = document.createElement("div");
    msg.textContent = "스레드가 없습니다. (ingest 실행 필요)";
    const btn = document.createElement("button");
    btn.textContent = "Ingest Now";
    btn.addEventListener("click", async () => {
      try {
        await apiJson(`/api/channels/${encodeURIComponent(channelId)}/ingest`, {
          method: "POST",
          body: JSON.stringify({ backfill_days: 14, mode: "full" }),
        });
        // brief wait then reload threads
        setTimeout(() => loadThreads(channelId), 2000);
      } catch (e) {
        showError(e.message);
      }
    });
    container.appendChild(msg);
    container.appendChild(btn);
    return;
  }

  for (const t of rows) {
    const item = document.createElement("div");
    item.className = "thread-item";

    const title = document.createElement("div");
    title.className = "thread-title";
    title.textContent = (t.one_line || t.root_text || "(no text)").slice(0, 120);

    const meta = document.createElement("div");
    meta.className = "thread-meta";
    meta.textContent = `replies: ${t.reply_count} · updated: ${fmtKstFromIso(
      t.updated_at
    )}`;

    item.appendChild(title);
    item.appendChild(meta);

    item.addEventListener("click", async () => {
      document
        .querySelectorAll(".thread-item.active")
        .forEach((x) => x.classList.remove("active"));
      item.classList.add("active");
      await loadThreadTimeline(channelId, t.thread_ts);
    });

    container.appendChild(item);
  }
}

function renderTimeline(detail) {
  const el = $("#threadTimeline");
  el.classList.remove("muted");
  el.innerHTML = "";

  if (!detail.messages || !detail.messages.length) {
    el.classList.add("muted");
    el.textContent = "메시지가 없습니다.";
    return;
  }

  for (const m of detail.messages) {
    const row = document.createElement("div");
    row.className = "msg" + (m.is_root ? " root" : "");

    const meta = document.createElement("div");
    meta.className = "msg-meta";
    const who = m.author_name || m.user_id || "(unknown)";
    meta.textContent = `${fmtKstFromEpochSeconds(m.ts_epoch)} · ${who}`;

    const body = document.createElement("div");
    body.className = "msg-body";
    body.innerHTML = m.text_html || "";

    row.appendChild(meta);
    row.appendChild(body);
    el.appendChild(row);
  }
}

async function loadThreads(channelId) {
  clearError();
  const container = $("#threadsList");
  container.classList.add("muted");
  container.textContent = "Loading...";
  const rows = await apiJson(
    `/api/channels/${encodeURIComponent(channelId)}/threads?limit=50&offset=0`
  );
  renderThreadsList(channelId, rows);

  const tl = $("#threadTimeline");
  tl.classList.add("muted");
  tl.textContent = "스레드를 선택하면 메시지가 표시됩니다";
}

async function loadThreadTimeline(channelId, threadTs) {
  clearError();
  const el = $("#threadTimeline");
  el.classList.add("muted");
  el.textContent = "Loading timeline...";
  const detail = await apiJson(
    `/api/channels/${encodeURIComponent(channelId)}/threads/${encodeURIComponent(
      threadTs
    )}`
  );
  renderTimeline(detail);
}

window.addEventListener("DOMContentLoaded", async () => {
  try {
    const channels = await loadChannelsIntoSelect();
    const sel = $("#channelSelect");
    const params = new URLSearchParams(window.location.search);
    const initialId = params.get("channel_id");

    sel.addEventListener("change", async () => {
      const id = sel.value;
      if (id) await loadThreads(id);
    });

    $("#reloadThreadsBtn")?.addEventListener("click", async () => {
      const id = sel.value;
      if (id) await loadThreads(id);
    });

    if (channels.length) {
      const targetId =
        initialId && channels.find((c) => c.channel_id === initialId)
          ? initialId
          : channels[0].channel_id;
      sel.value = targetId;
      await loadThreads(targetId);
    }
  } catch (e) {
    showError(e.message);
  }
});
