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
    tbody.innerHTML = `<tr><td colspan="7" class="muted">No channels yet</td></tr>`;
    return;
  }

  tbody.innerHTML = rows
    .map((ch) => {
      const activeTxt = ch.is_active ? "ON" : "OFF";
      const btnTxt = ch.is_active ? "비활성화" : "활성화";
      const lastTs = ch.last_ts ? ch.last_ts : "-";
      return `
        <tr>
          <td>${ch.channel_id}</td>
          <td>${ch.name ?? "-"}</td>
          <td>${activeTxt}</td>
          <td>${lastTs}</td>
          <td>${fmtDate(ch.last_ingested_at)}</td>
          <td>${fmtDate(ch.created_at)}</td>
          <td>
            <button data-id="${ch.channel_id}" data-active="${ch.is_active}">
              ${btnTxt}
            </button>
          </td>
        </tr>
      `;
    })
    .join("");

  tbody.querySelectorAll("button[data-id]").forEach((btn) => {
    btn.addEventListener("click", async () => {
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
  } catch (e) {
    showError(e.message);
  }
}

window.addEventListener("DOMContentLoaded", () => {
  $("#addChannelBtn")?.addEventListener("click", onAddChannel);
  loadChannels();
});
