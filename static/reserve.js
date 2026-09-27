// Reservation page: fetch open slots for the chosen date/party size, then book.
const form = document.getElementById("reserve-form");
const dateInput = form.elements.date;
const slotsEl = document.getElementById("slots");
let selectedSlot = null;

const today = new Date();
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
dateInput.min = iso(today);
dateInput.max = iso(new Date(today.getTime() + 60 * 864e5));
dateInput.value = iso(today);

async function loadSlots() {
  selectedSlot = null;
  if (!dateInput.value) return;
  slotsEl.innerHTML = `<p class="muted">Loading times…</p>`;
  try {
    const data = await api(`/api/reservations/availability?date=${dateInput.value}&party_size=${form.elements.party_size.value}`);
    const open = data.slots.filter((s) => s.available);
    slotsEl.innerHTML = open.length
      ? data.slots
          .map((s) => `<button type="button" class="slot" data-slot="${s.value}" ${s.available ? "" : "disabled"}>${fmt(s.time)}</button>`)
          .join("")
      : `<p class="muted">No tables left for that day and party size. Try another date.</p>`;
  } catch (e) {
    slotsEl.innerHTML = `<p class="error">${esc(e.message)}</p>`;
  }
}

function fmt(hhmm) {
  const [h, m] = hhmm.split(":").map(Number);
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
}

slotsEl.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-slot]");
  if (!btn) return;
  slotsEl.querySelectorAll(".slot").forEach((b) => b.classList.remove("selected"));
  btn.classList.add("selected");
  selectedSlot = btn.dataset.slot;
});

dateInput.addEventListener("change", loadSlots);
form.elements.party_size.addEventListener("change", loadSlots);

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = document.getElementById("reserve-error");
  err.hidden = true;
  if (!selectedSlot) {
    err.textContent = "Please pick a time.";
    err.hidden = false;
    return;
  }
  const fd = new FormData(form);
  try {
    const r = await api("/api/reservations", {
      method: "POST",
      body: {
        name: fd.get("name"), phone: fd.get("phone"), email: fd.get("email"),
        notes: fd.get("notes"), party_size: Number(fd.get("party_size")), reserved_for: selectedSlot,
      },
    });
    const when = new Date(r.reserved_for);
    form.hidden = true;
    const done = document.getElementById("reserve-done");
    done.hidden = false;
    done.innerHTML = `
      <h2>You're booked, ${esc(r.name)}!</h2>
      <p>Table for <strong>${r.party_size}</strong> on <strong>${when.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}</strong>
      at <strong>${fmt(r.reserved_for.slice(11))}</strong>.</p>
      <p class="muted">Confirmation #${r.id}. We'll hold your table for 15 minutes.</p>
      <a class="btn" href="/">Order ahead</a>`;
  } catch (ex) {
    err.textContent = ex.message;
    err.hidden = false;
    loadSlots();
  }
});

loadSlots();
