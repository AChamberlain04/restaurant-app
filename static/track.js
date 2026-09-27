// Live order tracking: polls the API every 8 seconds until the order is done.
const code = document.getElementById("track").dataset.code;
const STEPS = ["received", "preparing", "ready", "completed"];
const COPY = {
  received: ["We've got your order!", "The kitchen will start on it shortly."],
  preparing: ["Your food is being prepared", "Our cooks are on it."],
  ready: ["Your order is ready!", null],
  completed: ["Enjoy your meal!", "Thanks for ordering with Ember & Oak."],
  cancelled: ["This order was cancelled", "Please call us if this is unexpected."],
};
let timer;

async function refresh() {
  try {
    const o = await api(`/api/orders/${code}`);
    render(o);
    if (o.status === "completed" || o.status === "cancelled") clearInterval(timer);
  } catch (e) {
    document.getElementById("status-headline").textContent = "We couldn't find that order.";
    document.getElementById("status-sub").textContent = "Double-check the code in your link.";
    document.getElementById("progress").hidden = true;
    clearInterval(timer);
  }
}

function render(o) {
  const [head, sub] = COPY[o.status];
  document.getElementById("status-headline").textContent = head;
  document.getElementById("status-sub").textContent =
    sub ?? (o.order_type === "pickup" ? "Head to the pickup counter." : `Coming out to table ${o.table_number}.`);

  const progress = document.getElementById("progress");
  progress.classList.toggle("cancelled", o.status === "cancelled");
  const current = STEPS.indexOf(o.status);
  progress.querySelectorAll("li").forEach((li, idx) => {
    li.classList.toggle("done", current >= idx);
    li.classList.toggle("current", current === idx);
    if (li.dataset.step === "completed") li.textContent = o.order_type === "pickup" ? "Picked up" : "Served";
  });

  document.getElementById("order-detail").innerHTML = `
    <ul class="receipt">
      ${o.items.map((i) => `<li><span>${i.quantity} × ${esc(i.name)}</span><span>${money(i.unit_price_cents * i.quantity)}</span></li>`).join("")}
      <li class="sub"><span>Subtotal</span><span>${money(o.subtotal_cents)}</span></li>
      <li class="sub"><span>Tax</span><span>${money(o.tax_cents)}</span></li>
      <li class="grand"><span>Total</span><span>${money(o.total_cents)}</span></li>
    </ul>
    <p class="muted small">${o.order_type === "pickup" ? "Pickup" : `Dine-in · Table ${o.table_number}`} · for ${esc(o.customer_name)}${o.notes ? ` · “${esc(o.notes)}”` : ""}</p>`;
}

refresh();
timer = setInterval(refresh, 8000);
