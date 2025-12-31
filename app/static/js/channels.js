const $ = (sel) => document.querySelector(sel);

function showError(msg) {
  const el = $("#channelsError");
  if (!el) return;
  el.style.display = "block";
  el.textContent = msg;
}

function clearError() {
  const el = $("#channelsError");
  if (!el) return;
  el.style.display = "none";
  el.textContent = "";
}

function fmtDate(v) {
  if (!v) return "-";
  try {
    return new Date(v).toLocaleString();
  } catch {
    return String(v);
  }
}

async function apiJson(url, opts = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = data.detail || `Request failed: ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

function renderChannels(rows) {
  const tbody = $("#channelsTbody");
  if (!tbody) return;

  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="muted">No channels yet</td></tr>`;
    return;
  }

  tbody.innerHTML = rows
    .map((ch) => {
      const activeTxt = ch.is_active ? "ON" : "OFF";
      const btnTxt = ch.is_active ? "비활성화" : "활성화";
      const lastTs = ch.last_ts ? ch.last_ts : "-";
      const ingestStatus = ch.ingest_status || "idle";
      const ingestLabel = ingestStatus === "running" ? "Ingesting…" : "Ingest Now";
      return `
        <tr data-channel-id="${ch.channel_id}">
          <td class="clickable">${ch.channel_id}</td>
          <td class="clickable">${ch.name ?? "-"}</td>
          <td>${activeTxt}</td>
          <td>${lastTs}</td>
          <td>${fmtDate(ch.last_ingested_at)}</td>
          <td>${ingestLabel}</td>
          <td>${fmtDate(ch.created_at)}</td>
          <td>
            <div class="row gap-sm">
              <button class="toggle-btn" data-id="${ch.channel_id}" data-active="${ch.is_active}">
                ${btnTxt}
              </button>
              <button class="ingest-btn" data-id="${ch.channel_id}" data-status="${ingestStatus}" ${
        ingestStatus === "running" ? "disabled" : ""
      }>
                ${ingestLabel}
              </button>
            </div>
          </td>
        </tr>
      `;
    })
    .join("");

  tbody.querySelectorAll(".toggle-btn").forEach((btn) => {
    btn.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      clearError();
      const id = btn.getAttribute("data-id");
      const active = btn.getAttribute("data-active") === "true";
      try {
        await apiJson(`/api/channels/${id}`, {
          method: "PATCH",
          body: JSON.stringify({ is_active: !active }),
        });
        await loadChannels();
      } catch (e) {
        showError(e.message);
      }
    });
  });

  tbody.querySelectorAll(".ingest-btn").forEach((btn) => {
    btn.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      const id = btn.getAttribute("data-id");
      if (btn.disabled) return;
      await triggerIngest(id, btn);
    });
  });

  tbody.querySelectorAll("tr[data-channel-id]").forEach((row) => {
    row.addEventListener("click", (ev) => {
      if (ev.target.closest("button")) return;
      const id = row.getAttribute("data-channel-id");
      if (id) {
        window.location.href = `/thread-reports?channel_id=${encodeURIComponent(id)}`;
      }
    });
  });
}

async function loadChannels() {
  clearError();
  try {
    const rows = await apiJson("/api/channels");
    renderChannels(rows);
  } catch (e) {
    showError(e.message);
  }
}

async function triggerIngest(channelId, btn) {
  clearError();
  btn.disabled = true;
  btn.textContent = "Ingesting…";
  try {
    const res = await apiJson(`/api/channels/${channelId}/ingest`, {
      method: "POST",
      body: JSON.stringify({ backfill_days: 14, mode: "full" }),
    });
    btn.textContent = "Done";
    btn.disabled = false;
    showError("");
    await loadChannels();
  } catch (e) {
    btn.disabled = false;
    btn.textContent = "Ingest Now";
    showError(e.message);
  }
}

async function onAddChannel() {
  clearError();
  const input = $("#channelIdInput");
  const channelId = (input?.value || "").trim();
  if (!channelId) {
    showError("channel_id를 입력하세요.");
    return;
  }

  try {
    await apiJson("/api/channels", {
      method: "POST",
      body: JSON.stringify({ channel_id: channelId }),
    });
    input.value = "";
    await loadChannels();
    // 선택: 추가 직후 즉시 ingest 실행
    const btn = document.querySelector(`.ingest-btn[data-id="${channelId}"]`);
    if (btn) {
      await triggerIngest(channelId, btn);
    }
  } catch (e) {
    showError(e.message);
  }
}

window.addEventListener("DOMContentLoaded", () => {
  $("#addChannelBtn")?.addEventListener("click", onAddChannel);
  loadChannels();
});
