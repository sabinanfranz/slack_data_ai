const $ = (sel) => document.querySelector(sel);

function showError(msg) {
  const el = $("#statsError");
  if (!el) return;
  el.style.display = "block";
  el.textContent = msg;
}
function clearError() {
  const el = $("#statsError");
  if (!el) return;
  el.style.display = "none";
  el.textContent = "";
}

async function apiJson(url) {
  const res = await fetch(url, { headers: { "Content-Type": "application/json" } });
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
  const sel = $("#statsChannelSelect");
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
    opt.textContent = ch.name ? `#${ch.name} (${ch.channel_id})` : ch.channel_id;
    sel.appendChild(opt);
  }
  return active;
}

function setText(id, v) {
  const el = $(id);
  if (el) el.textContent = v;
}

function renderDaily(rows) {
  const tbody = $("#dailyTbody");
  tbody.innerHTML = "";
  if (!rows || !rows.length) {
    tbody.innerHTML = `<tr><td colspan="2" class="muted">No data</td></tr>`;
    return;
  }
  for (const r of rows) {
    const tr = document.createElement("tr");
    const td1 = document.createElement("td");
    td1.textContent = r.date_kst;
    const td2 = document.createElement("td");
    td2.textContent = String(r.message_count);
    tr.appendChild(td1);
    tr.appendChild(td2);
    tbody.appendChild(tr);
  }
}

function renderTopThreads(rows) {
  const tbody = $("#topThreadsTbody");
  tbody.innerHTML = "";
  if (!rows || !rows.length) {
    tbody.innerHTML = `<tr><td colspan="4" class="muted">No data</td></tr>`;
    return;
  }
  for (const t of rows) {
    const tr = document.createElement("tr");

    const tdCnt = document.createElement("td");
    tdCnt.textContent = String(t.reply_count ?? 0);

    const tdText = document.createElement("td");
    tdText.textContent = (t.root_text || "(no text)").slice(0, 120);

    const tdTs = document.createElement("td");
    tdTs.textContent = t.thread_ts;

    const tdUpd = document.createElement("td");
    tdUpd.textContent = fmtKstFromIso(t.updated_at);

    tr.appendChild(tdCnt);
    tr.appendChild(tdText);
    tr.appendChild(tdTs);
    tr.appendChild(tdUpd);
    tbody.appendChild(tr);
  }
}

function renderTopUsers(rows) {
  const tbody = $("#topUsersTbody");
  tbody.innerHTML = "";
  if (!rows || !rows.length) {
    tbody.innerHTML = `<tr><td colspan="3" class="muted">No data</td></tr>`;
    return;
  }
  for (const u of rows) {
    const tr = document.createElement("tr");

    const tdCnt = document.createElement("td");
    tdCnt.textContent = String(u.message_count ?? 0);

    const tdName = document.createElement("td");
    tdName.textContent = u.name || u.user_id;

    const tdId = document.createElement("td");
    tdId.textContent = u.user_id;

    tr.appendChild(tdCnt);
    tr.appendChild(tdName);
    tr.appendChild(tdId);
    tbody.appendChild(tr);
  }
}

async function loadStats() {
  clearError();
  const channelId = $("#statsChannelSelect")?.value;
  const days = Number($("#daysInput")?.value || 7);
  const topN = Number($("#topNInput")?.value || 10);

  if (!channelId) {
    showError("채널을 선택하세요.");
    return;
  }

  const url = `/api/channels/${encodeURIComponent(
    channelId
  )}/stats?days=${encodeURIComponent(days)}&top_n=${encodeURIComponent(topN)}`;
  const data = await apiJson(url);

  setText("#rangeText", `${data.start_date_kst} ~ ${data.end_date_kst_exclusive} (exclusive)`);
  setText("#totalMessages", String(data.total_messages));
  setText("#totalThreads", String(data.total_threads));
  setText("#uniqueUsers", String(data.unique_users));

  renderDaily(data.daily_messages);
  renderTopThreads(data.top_threads);
  renderTopUsers(data.top_users);
}

window.addEventListener("DOMContentLoaded", async () => {
  try {
    const channels = await loadChannels();
    $("#loadStatsBtn")?.addEventListener("click", loadStats);
    $("#statsChannelSelect")?.addEventListener("change", loadStats);

    if (channels.length) await loadStats();
  } catch (e) {
    showError(e.message);
  }
});
