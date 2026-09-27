// Kitchen dashboard: order board, reservations list, menu availability.
const NEXT = {
  received: { to: "preparing", label: "Start" },
  preparing: { to: "ready", label: "Mark ready" },
  ready: { to: "completed", label: "Complete" },
};
let activeTab = "orders";

function minutesAgo(sqlUtc) {
  const t = new Date(sqlUtc.replace(" ", "T") + "Z");
  return Math.max(0, Math.round((Date.now() - t) / 60000));
}

async function loadStats() {
  const s = await api("/api/staff/stats");
  document.getElementById("s-active").textContent = s.active_orders;
  document.getElementById("s-orders").textContent = s.orders_today;
  document.getElementById("s-revenue").textContent = money(s.revenue_today_cents);
  document.getElementById("s-covers").textContent = s.covers_today;
}

async function loadOrders() {
  const orders = await api("/api/staff/orders?status=active");
  for (const status of Object.keys(NEXT)) {
    const list = orders.filter((o) => o.status === status);
    document.getElementById(`c-${status}`).textContent = list.length;
    document.getElementById(`col-${status}`).innerHTML = list.length
      ? list.map(ticket).join("")
      : `<p class="muted small empty">Nothing here</p>`;
  }
}

function ticket(o) {
  const age = minutesAgo(o.created_at);
  const late = age >= 20 && o.status !== "ready";
  return `
    <article class="ticket ${late ? "late" : ""}">
      <header>
        <strong>#${o.code}</strong>
        <span class="small ${late ? "late-text" : "muted"}">${age}m ago</span>
      </header>
      <p class="small">${o.order_type === "pickup" ? "Pickup" : `Table ${o.table_number}`} · ${esc(o.customer_name)}</p>
      <ul>${o.items.map((i) => `<li><b>${i.quantity}×</b> ${esc(i.name)}</li>`).join("")}</ul>
      ${o.notes ? `<p class="note">${esc(o.notes)}</p>` : ""}
      <footer>
        <button class="btn small primary" data-order="${o.id}" data-to="${NEXT[o.status].to}">${NEXT[o.status].label}</button>
        <button class="btn small ghost" data-order="${o.id}" data-to="cancelled">Cancel</button>
      </footer>
    </article>`;
}

async function loadReservations() {
  const dateEl = document.getElementById("res-date");
  const rows = await api(`/api/staff/reservations?date=${dateEl.value}`);
  document.getElementById("res-body").innerHTML = rows.length
    ? rows
        .map(
          (r) => `
      <tr class="${r.status}">
        <td>${r.reserved_for.slice(11)}</td>
        <td>${esc(r.name)}</td>
        <td>${r.party_size}</td>
        <td>${esc(r.phone)}</td>
        <td class="small">${esc(r.notes)}</td>
        <td>
          <select data-res="${r.id}">
            ${["booked", "seated", "no_show", "cancelled"].map((s) => `<option value="${s}" ${s === r.status ? "selected" : ""}>${s.replace("_", "-")}</option>`).join("")}
          </select>
        </td>
      </tr>`
        )
        .join("")
    : `<tr><td colspan="6" class="muted">No reservations for this date.</td></tr>`;
}

async function loadMenu() {
  const data = await api("/api/menu");
  document.getElementById("menu-body").innerHTML = data.categories
    .flatMap((c) =>
      c.items.map(
        (i) => `
      <tr>
        <td>${esc(i.name)}</td>
        <td class="muted">${esc(c.name)}</td>
        <td>${money(i.price_cents)}</td>
        <td><label class="switch"><input type="checkbox" data-item="${i.id}" ${i.available ? "checked" : ""}><span></span></label></td>
      </tr>`
      )
    )
    .join("");
}

async function refresh() {
  try {
    await loadStats();
    if (activeTab === "orders") await loadOrders();
    if (activeTab === "reservations") await loadReservations();
  } catch (e) {
    if (e.message.includes("login")) window.location.href = "/staff/login";
    else toast(e.message);
  }
}

document.addEventListener("click", async (e) => {
  const tab = e.target.closest("[data-tab]");
  if (tab) {
    activeTab = tab.dataset.tab;
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
    document.querySelectorAll(".panel").forEach((p) => (p.hidden = p.id !== `panel-${activeTab}`));
    if (activeTab === "menu") loadMenu();
    refresh();
    return;
  }
  const btn = e.target.closest("[data-order]");
  if (btn) {
    if (btn.dataset.to === "cancelled" && !confirm("Cancel this order?")) return;
    btn.disabled = true;
    try {
      await api(`/api/staff/orders/${btn.dataset.order}`, { method: "PATCH", body: { status: btn.dataset.to } });
      await refresh();
    } catch (ex) {
      toast(ex.message);
      btn.disabled = false;
    }
  }
});

document.addEventListener("change", async (e) => {
  try {
    if (e.target.matches("[data-res]")) {
      await api(`/api/staff/reservations/${e.target.dataset.res}`, { method: "PATCH", body: { status: e.target.value } });
      toast("Reservation updated");
      loadReservations();
      loadStats();
    } else if (e.target.matches("[data-item]")) {
      await api(`/api/staff/menu/${e.target.dataset.item}`, { method: "PATCH", body: { available: e.target.checked } });
      toast(e.target.checked ? "Back on the menu" : "Marked sold out");
    } else if (e.target.id === "res-date") {
      loadReservations();
    }
  } catch (ex) {
    toast(ex.message);
  }
});

const d = new Date();
document.getElementById("res-date").value =
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
refresh();
setInterval(refresh, 10000);
