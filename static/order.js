// Customer ordering page: render menu, manage cart, submit order.
const state = { menu: [], taxRate: 0, cart: loadCart() };

function loadCart() {
  try { return JSON.parse(localStorage.getItem("cart") || "{}"); } catch { return {}; }
}
function saveCart() {
  try { localStorage.setItem("cart", JSON.stringify(state.cart)); } catch {}
}
const allItems = () => state.menu.flatMap((c) => c.items);
const findItem = (id) => allItems().find((i) => i.id === Number(id));

async function init() {
  try {
    const data = await api("/api/menu");
    state.menu = data.categories;
    state.taxRate = data.tax_rate;
    // Drop cart lines for items that disappeared or sold out since last visit.
    for (const id of Object.keys(state.cart)) {
      const it = findItem(id);
      if (!it || !it.available) delete state.cart[id];
    }
    renderMenu();
    renderCart();
  } catch (e) {
    document.getElementById("menu").innerHTML = `<p class="error">Couldn't load the menu: ${esc(e.message)}</p>`;
  }
}

function renderMenu() {
  const tabs = document.getElementById("category-tabs");
  tabs.innerHTML = state.menu
    .map((c) => `<a href="#cat-${c.id}" class="chip">${esc(c.name)}</a>`)
    .join("");

  document.getElementById("menu").innerHTML = state.menu
    .map(
      (c) => `
      <section class="menu-section" id="cat-${c.id}">
        <h2>${esc(c.name)}</h2>
        <div class="menu-grid">
          ${c.items.map(itemCard).join("")}
        </div>
      </section>`
    )
    .join("");
}

function itemCard(i) {
  const tags = i.tags.map((t) => `<span class="tag tag-${t}">${TAG_LABELS[t] || esc(t)}</span>`).join("");
  return `
    <article class="item ${i.available ? "" : "sold-out"}">
      <div class="item-top">
        <h3>${esc(i.name)}</h3>
        <span class="price">${money(i.price_cents)}</span>
      </div>
      <p>${esc(i.description)}</p>
      <div class="item-bottom">
        <div class="tags">${tags}</div>
        ${i.available
          ? `<button class="btn small" data-add="${i.id}">Add</button>`
          : `<span class="muted small">Sold out</span>`}
      </div>
    </article>`;
}

function totals() {
  const subtotal = Object.entries(state.cart).reduce((sum, [id, qty]) => sum + (findItem(id)?.price_cents || 0) * qty, 0);
  const tax = Math.round(subtotal * state.taxRate);
  return { subtotal, tax, total: subtotal + tax };
}

function renderCart() {
  const lines = Object.entries(state.cart);
  document.getElementById("cart-lines").innerHTML = lines
    .map(([id, qty]) => {
      const it = findItem(id);
      return `
        <li>
          <div><strong>${esc(it.name)}</strong><br><span class="muted small">${money(it.price_cents)} each</span></div>
          <div class="qty">
            <button aria-label="Remove one" data-dec="${id}">−</button>
            <span>${qty}</span>
            <button aria-label="Add one" data-inc="${id}">+</button>
          </div>
        </li>`;
    })
    .join("");
  const t = totals();
  document.getElementById("cart-empty").hidden = lines.length > 0;
  document.getElementById("subtotal").textContent = money(t.subtotal);
  document.getElementById("tax").textContent = money(t.tax);
  document.getElementById("total").textContent = money(t.total);
  document.getElementById("fab-total").textContent = money(t.total);
  document.getElementById("cart-fab").hidden = lines.length === 0;
  document.getElementById("place-order").disabled = lines.length === 0;
  saveCart();
}

document.addEventListener("click", (e) => {
  const add = e.target.closest("[data-add]");
  const inc = e.target.closest("[data-inc]");
  const dec = e.target.closest("[data-dec]");
  if (add) {
    const id = add.dataset.add;
    state.cart[id] = Math.min((state.cart[id] || 0) + 1, 20);
    toast(`Added ${findItem(id).name}`);
  } else if (inc) {
    state.cart[inc.dataset.inc] = Math.min(state.cart[inc.dataset.inc] + 1, 20);
  } else if (dec) {
    const id = dec.dataset.dec;
    state.cart[id] -= 1;
    if (state.cart[id] <= 0) delete state.cart[id];
  } else if (e.target.id === "cart-fab") {
    document.getElementById("cart").scrollIntoView({ behavior: "smooth" });
    return;
  } else return;
  renderCart();
});

const form = document.getElementById("checkout");
form.addEventListener("change", (e) => {
  if (e.target.name === "order_type") {
    document.getElementById("table-field").hidden = e.target.value !== "dine_in";
  }
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = document.getElementById("checkout-error");
  err.hidden = true;
  const fd = new FormData(form);
  const body = {
    customer_name: fd.get("customer_name"),
    phone: fd.get("phone"),
    order_type: fd.get("order_type"),
    notes: fd.get("notes"),
    items: Object.entries(state.cart).map(([id, quantity]) => ({ id: Number(id), quantity })),
  };
  if (body.order_type === "dine_in") body.table_number = fd.get("table_number");

  const btn = document.getElementById("place-order");
  btn.disabled = true;
  btn.textContent = "Placing order…";
  try {
    const order = await api("/api/orders", { method: "POST", body });
    state.cart = {};
    saveCart();
    window.location.href = `/track/${order.code}`;
  } catch (ex) {
    err.textContent = ex.message;
    err.hidden = false;
    btn.disabled = false;
    btn.textContent = "Place order";
  }
});

init();
