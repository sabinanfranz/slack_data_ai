const $ = (sel) => document.querySelector(sel);

let currentChannelId = null;
let currentThreadTs = null;
let refreshInFlight = false;

function showError(msg) {
  const el = $("#trError");
  if (!el) return;
  el.style.display = "block";
  el.textContent = msg;
}
function clearError() {
  const el = $("#trError");
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

function fmtKstFromIso(iso) {
  if (!iso) return "-";
  try {
    return new Date(iso).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
  } catch {
    return String(iso);
  }
}

async function loadChannels() {
  const sel = $("#trChannelSelect");
  sel.innerHTML = "";
  const rows = await apiJson("/api/thread-reports/channels");
  if (!rows.length) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "활성 채널 없음 (Channels에서 추가/활성화)";
    sel.appendChild(opt);
    sel.disabled = true;
    return [];
  }
  sel.disabled = false;
  for (const ch of rows) {
    const opt = document.createElement("option");
    opt.value = ch.channel_id;
    opt.textContent = ch.name ? `#${ch.name} (${ch.channel_id})` : ch.channel_id;
    sel.appendChild(opt);
  }
  return rows;
}

function renderThreadList(rows, channelId) {
  const container = $("#trThreadList");
  container.classList.remove("muted");
  container.innerHTML = "";
  if (!rows.length) {
    container.classList.add("muted");
    container.textContent = "스레드가 없습니다. (ingest/리포트 생성 필요)";
    return;
  }

  for (const r of rows) {
    const item = document.createElement("div");
    item.className = "thread-item";
    item.dataset.threadTs = r.thread_ts;

    const title = document.createElement("div");
    title.className = "thread-title";
    title.textContent = (r.title || r.one_line || "(no text)").slice(0, 120);

    const meta = document.createElement("div");
    meta.className = "thread-meta";
    const reportBadge = r.has_report ? " | report✓" : " | report✗";
    meta.textContent = `replies: ${r.reply_count} · updated: ${fmtKstFromIso(r.updated_at)}${reportBadge}`;

    item.appendChild(title);
    item.appendChild(meta);

    item.addEventListener("click", async () => {
      document
        .querySelectorAll("#trThreadList .thread-item.active")
        .forEach((x) => x.classList.remove("active"));
      item.classList.add("active");
      await loadReport(channelId, r.thread_ts);
    });

    container.appendChild(item);
  }
}

function renderReport(data) {
  const el = $("#trReport");
  el.classList.remove("muted");
  el.innerHTML = "";
  if (!data) {
    el.classList.add("muted");
    el.textContent = "리포트가 없습니다. (ingest/summary/report 생성 필요)";
    return;
  }

  const meta = document.createElement("div");
  meta.className = "muted";
  const staleBadge =
    data.meta && data.meta.is_stale ? " | 상태: 구버전(새로고침 권장)" : " | 상태: 최신/알수없음";
  meta.textContent = `model: ${data.model} | source_ts: ${data.source_latest_ts}${staleBadge}`;
  el.appendChild(meta);

  const topic = document.createElement("div");
  topic.className = "section";
  topic.innerHTML = `<h3>논의 주제</h3><p>${data.report_json.topic || "-"}</p>`;
  el.appendChild(topic);

  const roles = document.createElement("div");
  roles.className = "section";
  roles.innerHTML = `<h3>참석자 역할</h3>`;
  if (data.report_json.participants_roles && data.report_json.participants_roles.length) {
    const list = document.createElement("ul");
    for (const p of data.report_json.participants_roles) {
      const li = document.createElement("li");
      const ev = (p.evidence || []).join("; ");
      li.textContent = `${p.name} – ${p.role}${ev ? ` (근거: ${ev})` : ""}`;
      list.appendChild(li);
    }
    roles.appendChild(list);
  } else {
    const empty = document.createElement("div");
    empty.className = "muted";
    empty.textContent = "데이터 없음";
    roles.appendChild(empty);
  }
  el.appendChild(roles);

  const timeline = document.createElement("div");
  timeline.className = "section";
  timeline.innerHTML = `<h3>일별 진척</h3>`;
  if (data.report_json.timeline_daily && data.report_json.timeline_daily.length) {
    for (const d of data.report_json.timeline_daily) {
      const card = document.createElement("div");
      card.className = "card muted";
      const parts = [];
      if (d.progress && d.progress.length) parts.push(`progress: ${d.progress.join("; ")}`);
      if (d.decisions && d.decisions.length) parts.push(`decisions: ${d.decisions.join("; ")}`);
      if (d.open_questions && d.open_questions.length) parts.push(`open: ${d.open_questions.join("; ")}`);
      card.innerHTML = `<strong>${d.date_kst}</strong><br>${parts.join("<br>") || "(내용 없음)"}`;
      timeline.appendChild(card);
    }
  } else {
    const empty = document.createElement("div");
    empty.className = "muted";
    empty.textContent = "데이터 없음";
    timeline.appendChild(empty);
  }
  el.appendChild(timeline);
}

async function loadThreads(channelId, { autoSelect = true } = {}) {
  clearError();
  currentChannelId = channelId;
  const list = $("#trThreadList");
  list.classList.add("muted");
  list.textContent = "Loading...";
  try {
    const rows = await apiJson(`/api/thread-reports?channel_id=${encodeURIComponent(channelId)}&limit=200`);
    renderThreadList(rows, channelId);
    if (autoSelect) {
      const first = rows[0];
      if (first) {
        await loadReport(channelId, first.thread_ts);
        const firstEl = list.querySelector(`.thread-item[data-thread-ts="${first.thread_ts}"]`);
        if (firstEl) firstEl.classList.add("active");
      } else {
        renderReport(null);
      }
    }
  } catch (e) {
    showError(e.message);
    list.classList.add("muted");
    list.textContent = "로드 실패";
  }
}

async function loadReport(channelId, threadTs) {
  clearError();
  currentChannelId = channelId;
  currentThreadTs = threadTs;
  const el = $("#trReport");
  el.classList.add("muted");
  el.textContent = "Loading...";
  try {
    const data = await apiJson(
      `/api/thread-reports/${encodeURIComponent(channelId)}/${encodeURIComponent(threadTs)}`
    );
    renderReport(data);
    setRefreshButtonState({ hasReport: true, stale: data.meta?.is_stale });
  } catch (e) {
    el.classList.add("muted");
    el.textContent = "리포트가 없습니다. (refresh 필요)";
    setRefreshButtonState({ hasReport: false, stale: true });
  }
}

function setRefreshButtonState({ hasReport, stale }) {
  const btn = $("#trRefreshBtn");
  const badge = $("#trStatusBadge");
  if (!btn || !badge) return;
  btn.disabled = refreshInFlight;
  btn.textContent = refreshInFlight ? "생성/갱신 중..." : hasReport ? "새로고침" : "즉시 생성";
  badge.textContent = hasReport ? (stale ? "리포트 있음 · 구버전" : "리포트 있음 · 최신 추정") : "리포트 없음";
}

async function refreshReport() {
  if (!currentChannelId || !currentThreadTs) return;
  const btn = $("#trRefreshBtn");
  refreshInFlight = true;
  setRefreshButtonState({ hasReport: true, stale: true });
  try {
    const data = await apiJson(
      `/api/thread-reports/${encodeURIComponent(currentChannelId)}/${encodeURIComponent(
        currentThreadTs
      )}/refresh?force=true`,
      { method: "POST" }
    );
    // Render updated report immediately
    renderReport({
      channel_id: currentChannelId,
      thread_ts: currentThreadTs,
      report_json: data.report_json,
      model: data.model,
      source_latest_ts: data.source_latest_ts,
      source_latest_ts_epoch: data.source_latest_ts_epoch,
      updated_at: data.updated_at,
      meta: data.meta,
    });
    // Reload list to sync has_report/updated_at
    if (currentChannelId) {
      await loadThreads(currentChannelId, { autoSelect: false });
      // reselect current thread
      const list = $("#trThreadList");
      const target = list?.querySelector(`.thread-item[data-thread-ts="${currentThreadTs}"]`);
      if (target) target.classList.add("active");
    }
  } catch (e) {
    showError(e.message || "리포트 생성 실패");
  } finally {
    refreshInFlight = false;
    setRefreshButtonState({ hasReport: true, stale: false });
  }
}

window.addEventListener("DOMContentLoaded", async () => {
  try {
    const channels = await loadChannels();
    const sel = $("#trChannelSelect");
    const params = new URLSearchParams(window.location.search);
    const initialId = params.get("channel_id");

    sel.addEventListener("change", async () => {
      const id = sel.value;
      if (id) await loadThreads(id);
    });

    $("#trReloadBtn")?.addEventListener("click", async () => {
      const id = sel.value;
      if (id) await loadThreads(id);
    });

    $("#trRefreshBtn")?.addEventListener("click", refreshReport);

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
