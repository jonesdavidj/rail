"use strict";

const $ = (id) => document.getElementById(id);
const node = (tag, className, text) => {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text != null) element.textContent = text;
  return element;
};
const london = (date, seconds = false) => new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/London", hour: "2-digit", minute: "2-digit", hour12: false,
  ...(seconds ? {second: "2-digit"} : {}),
}).format(date);
const memory = {
  get() { try { return localStorage.getItem("rail.lastRoute"); } catch { return null; } },
  set(id) { try { localStorage.setItem("rail.lastRoute", id); } catch { /* Private storage can be unavailable. */ } },
  fast(id) { try { return localStorage.getItem("rail.fast." + id) === "1"; } catch { return false; } },
  setFast(id, enabled) { try { localStorage.setItem("rail.fast." + id, enabled ? "1" : "0"); } catch { /* Device storage is optional. */ } },
};
let routes = [], current = null, refreshMs = 30000, refreshTimer, editing = null;
let globalWarning = "", bootSequence = 0, tokenRequired = false, nextDomId = 0;
let writeBusy = false, routeRevision = 0;
const boards = new Map();
const station = {from: null, to: null};
const searches = {};
const stateFor = (id) => {
  if (!boards.has(id)) boards.set(id, {
    stack: [{offset: 0}], fast: memory.fast(id), data: null, open: new Set(), domIds: new Map(), loading: false,
    error: null, sequence: 0, controller: null, received: 0, noticesOpen: false,
  });
  return boards.get(id);
};
const activeRoute = () => routes.find((route) => route.id === current);
const say = (message) => { $("announcement").textContent = message; };

async function api(path, options = {}) {
  const response = await fetch(path, {cache: "no-store", ...options});
  let body;
  try { body = await response.json(); }
  catch { throw new Error("Could not read the response. Reload the page to reconnect or renew your access session."); }
  if (!response.ok) {
    const error = new Error(typeof body.error === "string" ? body.error : (
      typeof body.detail === "string" ? body.detail : "Check the details and try again."
    ));
    error.status = response.status;
    error.code = body.error_code;
    throw error;
  }
  return body;
}

function renderTabs() {
  const list = $("tabs");
  list.replaceChildren();
  for (const route of routes) {
    const button = node("button", "tab", route.label);
    button.type = "button";
    button.id = "tab-" + route.id;
    button.role = "tab";
    button.setAttribute("aria-selected", String(route.id === current));
    button.setAttribute("aria-controls", "departures");
    button.tabIndex = route.id === current ? 0 : -1;
    button.onclick = () => selectRoute(route.id, true);
    button.onkeydown = (event) => {
      const index = routes.findIndex((item) => item.id === route.id);
      let next;
      if (event.key === "ArrowRight") next = (index + 1) % routes.length;
      if (event.key === "ArrowLeft") next = (index - 1 + routes.length) % routes.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = routes.length - 1;
      if (next != null) { event.preventDefault(); selectRoute(routes[next].id, true); }
    };
    list.append(button);
  }
  list.hidden = !routes.length;
}

function updateHeading() {
  const route = activeRoute();
  $("title").textContent = route?.label || "Your departures";
  $("route-codes").textContent = route ? `${route.origin} → ${route.destination}` : "DEPARTURES";
  document.title = route ? `${route.label} · Rail` : "Rail · Departures";
  if (route) $("departures").setAttribute("aria-labelledby", "tab-" + route.id);
  else $("departures").removeAttribute("aria-labelledby");
}

function selectRoute(id, focus = false) {
  if (!routes.some((route) => route.id === id)) return;
  current = id;
  globalWarning = "";
  memory.set(id);
  const url = new URL(location.href);
  url.searchParams.set("route", id);
  history.replaceState(null, "", url.pathname + url.search + url.hash);
  renderTabs(); updateHeading(); renderBoard();
  if (focus) {
    const tab = $("tab-" + id);
    tab.focus({preventScroll: true});
    const strip = $("tabs").getBoundingClientRect(), item = tab.getBoundingClientRect();
    if (item.left < strip.left) $("tabs").scrollLeft += item.left - strip.left;
    if (item.right > strip.right) $("tabs").scrollLeft += item.right - strip.right;
  }
  loadBoard(id, true);
}

function schedule() {
  clearTimeout(refreshTimer);
  if (!document.hidden && current) refreshTimer = setTimeout(() => loadBoard(current), refreshMs);
}

async function loadBoard(id, announce = false) {
  if (!id || !routes.some((route) => route.id === id)) return;
  const state = stateFor(id);
  if (state.loading && !announce) { schedule(); return; }
  state.controller?.abort();
  const controller = new AbortController();
  state.controller = controller;
  const sequence = ++state.sequence;
  state.loading = true;
  if (id === current) renderBoard();
  const timeout = setTimeout(() => controller.abort("timeout"), 20000);
  try {
    const position = state.stack.at(-1);
    const query = new URLSearchParams({route: id, offset: position.offset});
    if (position.cursor) query.set("cursor", position.cursor);
    if (state.fast) query.set("fast", "1");
    const data = await api("/api/board?" + query, {signal: controller.signal});
    if (sequence !== state.sequence) return;
    state.data = data;
    state.received = Date.now();
    state.error = null;
    const alive = new Set(data.services.map((service) => service.id));
    state.open = new Set([...state.open].filter((key) => alive.has(key)));
    for (const key of state.domIds.keys()) if (!alive.has(key)) state.domIds.delete(key);
    if (announce && id === current) say(`${data.services.length} departures loaded.`);
  } catch (error) {
    if (sequence !== state.sequence || (controller.signal.aborted && controller.signal.reason !== "timeout")) return;
    state.error = controller.signal.reason === "timeout"
      ? "The update took too long. Try again, or check your connection."
      : error.status ? error.message : "Could not reach the departure board. Check your connection and try again, or reload the page to renew your access session.";
    if (error.status === 404) state.error = "This journey was removed on another device. Open route settings to refresh your saved routes.";
    if (error.code === "rate_limit") state.error += " Wait a minute before trying again.";
    if (error.code === "authentication" || error.code === "configuration") state.error += " The server owner needs to check the feed settings.";
    const age = (Date.now() - state.received) / 1000 + (state.data?.cache_age_seconds || 0);
    if (age > 900) state.data = null;
  } finally {
    clearTimeout(timeout);
    if (sequence === state.sequence) state.loading = false;
    if (id === current) { renderBoard(); schedule(); }
  }
}

function showState(title, message, actions = []) {
  const container = $("board-state");
  container.replaceChildren(node("h2", "", title), node("p", "", message));
  const controls = node("div", "state-actions");
  for (const [label, callback] of actions) {
    const button = node("button", "", label);
    button.type = "button"; button.onclick = callback; controls.append(button);
  }
  if (actions.length) container.append(controls);
  container.hidden = false;
}

function statusText(service) {
  if (service.status === "on_time") return service.in_min < -1 ? "Departed" : "On time";
  if (service.status === "late") return `${service.delay_min} min late`;
  if (service.status === "delayed") return "Delayed";
  if (service.status === "cancelled") return "Cancelled";
  if (service.status === "part_cancelled") return "Destination call cancelled";
  return "Awaiting update";
}

function serviceRow(service, state, justOpened) {
  if (!state.domIds.has(service.id)) state.domIds.set(service.id, "service-" + ++nextDomId);
  const id = state.domIds.get(service.id);
  const item = node("li", "service"); item.dataset.status = service.status;
  item.classList.toggle("fast", service.is_fast);
  const toggle = node("button", "service-toggle");
  toggle.type = "button"; toggle.id = id;
  const open = state.open.has(service.id);
  toggle.setAttribute("aria-expanded", String(open));
  toggle.setAttribute("aria-controls", id + "-stops");
  const dep = node("span", "dep");
  dep.append(node("span", "planned", service.planned));
  if (service.expected && service.status !== "cancelled") dep.append(node("span", "expected", "exp " + service.expected));
  const destination = node("span", "destination");
  destination.append(node("strong", "", service.destination || activeRoute().destination));
  const arrival = node("span", "arrival");
  arrival.append(node("span", "planned", service.arrival?.planned || "--:--"));
  if (service.arrival?.expected && !service.arrival.cancelled) arrival.append(node("span", "expected", "exp " + service.arrival.expected));
  const meta = [];
  if (service.service_type === "bus") meta.push("Replacement bus");
  if (service.operator_name || service.operator) meta.push(service.operator_name || service.operator);
  if (service.length > 0) meta.push(`${service.length} cars`);
  const stopsText = service.stop_count == null ? "" : (service.stop_count === 0 ? "Non-stop" : `${service.stop_count} ${service.stop_count === 1 ? "stop" : "stops"}`);
  const metadata = node("span", "service-meta", meta.join(" · "));
  if (stopsText) {
    if (meta.length) metadata.append(document.createTextNode(" · "));
    const stopSummary = node("span", "stop-summary");
    if (service.is_fast) stopSummary.append(node("span", "fast-pill", "Fast"), document.createTextNode(", "));
    stopSummary.append(document.createTextNode(stopsText)); metadata.append(stopSummary);
  }
  if (service.journey_minutes != null) {
    if (metadata.childNodes.length) metadata.append(document.createTextNode(" · "));
    metadata.append(node("span", "journey-time", `${service.journey_minutes} min`));
  }
  if (service.is_quickest) metadata.append(document.createTextNode(" · "), node("span", "quickest", "Quickest"));
  const status = node("span", "service-status");
  status.append(node("span", "status", statusText(service)), node("span", "disclosure", open ? "Hide stops −" : "Show stops +"));
  toggle.append(dep, destination, node("span", "platform", service.platform || "TBC"), arrival,
    metadata, status);
  toggle.setAttribute("aria-label", [
    `Planned departure ${service.planned}`,
    service.expected && service.status !== "cancelled" ? `expected departure ${service.expected}` : "",
    `to ${service.destination || activeRoute().destination}`,
    service.platform && service.platform !== "TBC" ? `platform ${service.platform}` : "platform to be confirmed",
    `planned arrival ${service.arrival?.planned || "unavailable"}`,
    service.arrival?.expected && !service.arrival.cancelled ? `expected arrival ${service.arrival.expected}` : "",
    statusText(service), ...meta, service.is_fast ? "Fast" : "", stopsText,
    service.journey_minutes != null ? `${service.journey_minutes} minute journey` : "",
    service.is_quickest ? "Quickest" : "", open ? "Hide stops" : "Show stops",
  ].filter(Boolean).join(". "));
  const descriptions = [];
  item.append(toggle);
  if (service.reason) {
    const reason = node("p", "service-reason", service.reason);
    reason.id = id + "-reason"; descriptions.push(reason.id); item.append(reason);
  }
  if (service.future_cancellation || service.future_delay) {
    const warning = node("p", "future-warning", service.future_cancellation
      ? "⚠ May be cancelled later in this journey" : "⚠ May be delayed later in this journey");
    warning.id = id + "-warning"; descriptions.push(warning.id); item.append(warning);
  }
  if (descriptions.length) toggle.setAttribute("aria-describedby", descriptions.join(" "));
  const stops = node("div", "stops" + (justOpened === service.id ? " just-opened" : ""));
  stops.id = id + "-stops"; stops.hidden = !open;
  if (open) {
    const list = node("ol");
    for (const point of service.stops) {
      const row = node("li", point.cancelled || service.status === "cancelled" ? "cancelled" : "");
      const label = node("span", "", point.name || point.crs);
      if (point.expected) label.append(node("span", "stop-expected", ` (was ${point.planned || "--:--"})`));
      row.append(node("span", "stop-time", point.expected || point.planned || "--:--"), label);
      list.append(row);
    }
    if (service.stops.length) stops.append(list);
    else stops.append(node("p", "no-stops", "Stops are not available for this service. Try the next update."));
  }
  item.append(stops);
  toggle.onclick = () => {
    if (state.open.has(service.id)) state.open.delete(service.id); else state.open.add(service.id);
    renderBoard(state.open.has(service.id) ? service.id : null);
  };
  return item;
}

function renderBoard(justOpened = null) {
  const focused = document.activeElement?.id;
  const route = activeRoute(), state = current ? stateFor(current) : null, data = state?.data;
  const list = $("services"); list.replaceChildren();
  $("board-state").hidden = true;
  $("mode").hidden = !data?.demo;
  $("departures").setAttribute("aria-busy", String(Boolean(state?.loading)));
  $("filter-all").disabled = $("filter-fast").disabled = !route;
  $("filter-all").setAttribute("aria-pressed", String(!state?.fast));
  $("filter-fast").setAttribute("aria-pressed", String(Boolean(state?.fast)));
  $("filter-fast").textContent = data ? `Fast only (${data.fast_count} of ${data.total_count})` : "Fast only";
  const error = globalWarning || state?.error || (data?.stale ? data.error || "Live updates are unavailable." : "");
  const alert = $("board-error"); alert.replaceChildren(); alert.hidden = !error || (!data && route && !globalWarning);
  if (error) {
    const when = data?.generated_at ? london(new Date(data.generated_at)) : "";
    alert.append(node("span", "", error + (data ? ` Showing the last board${when ? " from " + when : ""}.` : "")));
    const retry = node("button", "", "Try again"); retry.type = "button";
    retry.onclick = () => { globalWarning = ""; route ? loadBoard(current, true) : boot(); };
    alert.append(retry);
  }
  if (!route) showState("Make it your journey", "Add your first route in settings to see departures.", [["Add a journey", openSettings]]);
  else if (!data && state.loading) showState("Loading departures…", "Checking the next direct services for this route.");
  else if (!data) showState("Departures couldn't be loaded", state.error || "Try again, check your connection or reload the page to renew your access session.", [["Try again", () => loadBoard(current, true)], ["Reload page", () => location.reload()]]);
  else if (!data.services.length) {
    const walking = route.min_departure_minutes;
    showState(data.services_available === false ? "Departure information is unavailable" : state.fast ? "No fast trains in this window. Try Later trains." : "No direct trains in this window",
      state.fast ? "Try Later trains, or choose All trains to see every service."
      : walking > 0 && state.stack.length === 1 && state.stack.at(-1).offset >= 0
        ? `Your ${walking}-minute walking allowance may hide earlier trains. Reduce it in settings or try again later.`
        : "Try the next departures, check your selected stations in settings, or try again shortly.",
      [[state.stack.at(-1).offset !== 0 || state.stack.length > 1 ? "Back to next departures" : "Try again", () => { state.stack = [{offset: 0}]; state.data = null; loadBoard(current, true); }], ["Route settings", openSettings]]);
  } else data.services.forEach((service) => list.append(serviceRow(service, state, justOpened)));
  const messages = (data?.messages || []).filter((message) => !(data.demo && message.startsWith("Demo data")));
  $("notices").hidden = !messages.length;
  $("notices").open = state?.noticesOpen || false;
  $("notice-count").textContent = messages.length ? `(${messages.length})` : "";
  const signature = JSON.stringify(messages);
  if ($("notice-content").dataset.signature !== signature) {
    $("notice-content").replaceChildren(...messages.map((message) => node("p", "", message)));
    $("notice-content").dataset.signature = signature;
  }
  $("earlier").disabled = !data || state.loading || (state.stack.length === 1 && state.stack[0].offset < 0);
  $("later").disabled = !data?.has_next || state.loading;
  $("return-now").hidden = !state || (state.stack.length === 1 && state.stack.at(-1).offset === 0);
  $("updated").textContent = data?.generated_at ? `Updated ${london(new Date(data.generated_at), true)}${data.stale || state.error ? " · last available board" : ""}` : "Waiting for an update";
  $("refresh-note").textContent = document.hidden ? "Updates paused while hidden" : `Refreshes every ${refreshMs / 1000} seconds`;
  if (focused?.startsWith("service-")) ($(focused) || $("departures")).focus({preventScroll: true});
}

function page(direction) {
  const state = stateFor(current);
  if (direction === "later" && state.data?.next_cursor) state.stack.push({offset: state.data.next_offset, cursor: state.data.next_cursor});
  else if (direction === "earlier") { if (state.stack.length > 1) state.stack.pop(); else state.stack = [{offset: -45}]; }
  else state.stack = [{offset: 0}];
  state.data = null; state.error = null;
  loadBoard(current, true);
}
$("notices").addEventListener("toggle", () => { if (current) stateFor(current).noticesOpen = $("notices").open; });
$("earlier").onclick = () => page("earlier");
$("later").onclick = () => page("later");
$("return-now").onclick = () => page("now");
function setFast(enabled) {
  if (!current) return;
  const state = stateFor(current); state.fast = enabled;
  memory.setFast(current, enabled); state.stack = [{offset: 0}]; state.data = null; state.error = null;
  loadBoard(current, true);
}
$("filter-all").onclick = () => setFast(false);
$("filter-fast").onclick = () => setFast(true);

function message(text, success = false) {
  const target = $("settings-message"); target.textContent = text;
  target.hidden = !text; target.classList.toggle("success", success);
  if (text && $("settings").open) target.scrollIntoView({block: "nearest"});
}
function resetForm() {
  $("route-form").reset(); editing = null; station.from = station.to = null;
  $("fast-destination").textContent = "the destination";
  $("form-heading").textContent = "Add a journey"; $("save-route").textContent = "Add journey";
  $("cancel-edit").hidden = true; $("return-option").hidden = false;
  for (const name of ["from", "to"]) {
    searches[name]?.close(); $(name).removeAttribute("aria-invalid");
    $(name + "-hint").textContent = "Search and select a station.";
  }
}
function openSettings() {
  message(""); resetForm(); renderSavedRoutes();
  $("token-section").hidden = !tokenRequired;
  $("settings").showModal(); $("settings-close").focus();
  // Reconcile routes changed by another device without erasing a form in progress.
  const revision = routeRevision;
  api("/api/routes").then((saved) => {
    if (revision !== routeRevision) return;
    applyRoutes(saved); renderSavedRoutes();
  }).catch((error) => message(error.message));
}
$("settings-open").onclick = openSettings;
$("settings-close").onclick = () => $("settings").close();
$("settings").addEventListener("close", () => {
  $("admin-token").value = ""; resetForm(); $("settings-open").focus();
});
$("cancel-edit").onclick = resetForm;

function applyRoutes(saved, select = null) {
  const previous = routes;
  routeRevision++;
  routes = saved;
  for (const [id, state] of boards) {
    const old = previous.find((route) => route.id === id), updated = routes.find((route) => route.id === id);
    if (!updated || JSON.stringify(old) !== JSON.stringify(updated)) {
      state.controller?.abort(); state.sequence++; boards.delete(id);
    }
  }
  if (select && routes.some((route) => route.id === select)) current = select;
  if (!routes.some((route) => route.id === current)) current = routes[0]?.id || null;
  renderTabs(); updateHeading(); renderBoard();
  if (current) {
    memory.set(current);
    const url = new URL(location.href); url.searchParams.set("route", current);
    history.replaceState(null, "", url.pathname + url.search + url.hash);
    if (!stateFor(current).data) loadBoard(current, true);
  } else { clearTimeout(refreshTimer); const url = new URL(location.href); url.searchParams.delete("route"); history.replaceState(null, "", url.pathname + url.search); }
}

async function write(path, method, body) {
  if (writeBusy) { message("A change is being saved. Please try again in a moment."); return null; }
  if (tokenRequired && !$("admin-token").value) {
    message("Enter your editing token above, then try again."); $("admin-token").focus(); return null;
  }
  const headers = {};
  if (body != null) headers["Content-Type"] = "application/json";
  if ($("admin-token").value) headers.Authorization = "Bearer " + $("admin-token").value;
  writeBusy = true;
  try { return await api(path, {method, headers, ...(body != null ? {body: JSON.stringify(body)} : {})}); }
  catch (error) {
    if (error.status === 401) {
      tokenRequired = true; $("token-section").hidden = false;
      message("The editing token was not accepted. Enter it above and try again."); $("admin-token").focus();
    } else message(error.status ? error.message : "Could not confirm the save. Check your connection, then close and reopen settings to reload your saved routes.");
    return null;
  } finally { writeBusy = false; }
}

function renderSavedRoutes(focus = null) {
  const list = $("saved-routes"); list.replaceChildren();
  if (!routes.length) list.append(node("li", "hint", "No saved routes yet. Add a journey below."));
  routes.forEach((route, index) => {
    const item = node("li", "saved-route"), info = node("div", "saved-route-info");
    info.append(node("p", "saved-route-name", route.label), node("p", "saved-route-codes", `${route.origin} → ${route.destination}${route.min_departure_minutes ? ` · ${route.min_departure_minutes} min walk` : ""}`));
    const actions = node("div", "route-actions");
    for (const [direction, symbol, delta] of [["up", "↑", -1], ["down", "↓", 1]]) {
      const button = node("button", "", symbol); button.type = "button"; button.id = `${direction}-${route.id}`;
      button.setAttribute("aria-label", `Move ${route.label} ${direction}`);
      button.disabled = index + delta < 0 || index + delta >= routes.length;
      button.onclick = async () => {
        button.disabled = true;
        const ids = routes.map((item) => item.id);
        [ids[index], ids[index + delta]] = [ids[index + delta], ids[index]];
        const saved = await write("/api/routes/order", "PUT", {ids});
        if (saved) { applyRoutes(saved); renderSavedRoutes(`edit-${route.id}`); message("Tab order saved.", true); }
        else renderSavedRoutes(`edit-${route.id}`);
      };
      actions.append(button);
    }
    const edit = node("button", "edit-route", "Edit"); edit.type = "button"; edit.id = "edit-" + route.id;
    edit.setAttribute("aria-label", `Edit ${route.label}`); edit.onclick = () => editRoute(route);
    const remove = node("button", "remove-route", "Remove"); remove.type = "button";
    remove.setAttribute("aria-label", `Remove ${route.label}`);
    remove.onclick = async () => {
      remove.disabled = true;
      const saved = await write("/api/routes?" + new URLSearchParams({id: route.id}), "DELETE");
      if (saved) { if (editing === route.id) resetForm(); applyRoutes(saved); renderSavedRoutes(); message("Journey removed.", true); }
      else remove.disabled = false;
    };
    actions.append(edit, remove); item.append(info, actions); list.append(item);
  });
  if (focus) $(focus)?.focus({preventScroll: true});
}

async function editRoute(route) {
  resetForm(); editing = route.id; message("");
  $("form-heading").textContent = "Edit journey"; $("save-route").textContent = "Save changes";
  $("cancel-edit").hidden = false; $("return-option").hidden = true;
  $("label").value = route.label; $("walking").value = route.min_departure_minutes;
  $("fast-max").value = route.fast_max_stops;
  for (const [name, crs] of [["from", route.origin], ["to", route.destination]]) {
    if (editing !== route.id || !$("settings").open) return;
    station[name] = {crs, name: crs}; $(name).value = crs; $(name + "-hint").textContent = "Selected: " + crs;
    try {
      const results = await api("/api/stations?" + new URLSearchParams({q: crs}));
      const selected = results.find((result) => result.crs === crs);
      if (editing === route.id && station[name]?.crs === crs && selected) searches[name].select(selected);
    } catch { /* Existing CRS stays selected even when station-name lookup fails. */ }
  }
  if (editing === route.id) $("from").focus();
}

function stationSearch(name) {
  const input = $(name), results = $(name + "-results"), hint = $(name + "-hint");
  let items = [], active = -1, timer, controller, sequence = 0;
  const close = () => { clearTimeout(timer); controller?.abort(); sequence++; items = []; results.hidden = true; input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); active = -1; };
  const select = (item) => {
    station[name] = item; input.value = `${item.name} (${item.crs})`;
    if (name === "to") $("fast-destination").textContent = item.name;
    hint.textContent = `Selected: ${item.crs}`; input.removeAttribute("aria-invalid"); close();
  };
  const highlight = () => {
    [...results.querySelectorAll("[role=option]")].forEach((option, index) => option.setAttribute("aria-selected", String(index === active)));
    if (active >= 0) { input.setAttribute("aria-activedescendant", `${name}-option-${active}`); $(`${name}-option-${active}`)?.scrollIntoView({block: "nearest"}); }
    else input.removeAttribute("aria-activedescendant");
  };
  input.addEventListener("input", () => {
    close(); station[name] = null; hint.textContent = "Search and select a station.";
    if (name === "to") $("fast-destination").textContent = "the destination";
    const query = input.value.trim();
    if (!query) return;
    const own = sequence;
    timer = setTimeout(async () => {
      controller = new AbortController(); results.replaceChildren(node("div", "search-message", "Searching stations…"));
      results.hidden = false; input.setAttribute("aria-expanded", "true");
      try {
        const found = await api("/api/stations?" + new URLSearchParams({q: query}), {signal: controller.signal});
        if (own !== sequence) return;
        items = found;
        results.replaceChildren();
        if (!items.length) results.append(node("div", "search-message", "No stations found. Try a name or three-letter code."));
        items.forEach((item, index) => {
          const option = node("button", "station-option"); option.type = "button"; option.tabIndex = -1;
          option.role = "option"; option.id = `${name}-option-${index}`;
          option.setAttribute("aria-selected", "false");
          option.append(node("span", "", item.name), node("span", "station-code", item.crs));
          option.onpointerdown = (event) => event.preventDefault();
          option.onclick = () => { select(item); input.focus(); };
          results.append(option);
        });
        hint.textContent = items.length ? `${items.length} results. Use arrow keys, then Enter to select.` : "Try a different station name or code.";
      } catch (error) {
        if (own !== sequence || controller.signal.aborted) return;
        items = []; results.replaceChildren(node("div", "search-message", "Station search unavailable. Check your connection and try typing again."));
      }
    }, 220);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !results.hidden) { event.preventDefault(); event.stopPropagation(); close(); }
    else if ((event.key === "ArrowDown" || event.key === "ArrowUp") && !results.hidden && items.length) {
      event.preventDefault(); active = (active + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length; highlight();
    } else if (event.key === "Enter" && !results.hidden) {
      event.preventDefault(); if (active >= 0) select(items[active]);
    }
  });
  input.addEventListener("blur", () => setTimeout(close, 120));
  return {close, select};
}
searches.from = stationSearch("from"); searches.to = stationSearch("to");

$("route-form").onsubmit = async (event) => {
  event.preventDefault(); message("");
  for (const name of ["from", "to"]) {
    if (!station[name]) { $(name).setAttribute("aria-invalid", "true"); message(`Select a ${name === "from" ? "departure" : "destination"} station from the search results.`); $(name).focus(); return; }
  }
  if (station.from.crs === station.to.crs) { message("Choose two different stations for your journey."); $("to").focus(); return; }
  const walking = $("walking").value === "" ? 0 : Number($("walking").value);
  if (!Number.isInteger(walking) || walking < 0 || walking > 120) { message("Walking time must be a whole number from 0 to 120 minutes."); $("walking").focus(); return; }
  const fastMax = Number($("fast-max").value);
  if ($("fast-max").value === "" || !Number.isInteger(fastMax) || fastMax < 0 || fastMax > 5) { message("Fast stops must be a whole number from 0 to 5."); $("fast-max").focus(); return; }
  const button = $("save-route"); button.disabled = true;
  const original = routes.find((route) => route.id === editing);
  const id = editing || "route-" + (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36));
  const route = {id, label: $("label").value.trim() || `${station.from.name} to ${station.to.name}`.slice(0, 100),
    origin: station.from.crs, destination: station.to.crs, min_departure_minutes: walking,
    page_size: original?.page_size || 7, fast_max_stops: fastMax, add_return_journey: !editing && $("add-return").checked};
  const saved = await write("/api/routes", editing ? "PUT" : "POST", route);
  button.disabled = false;
  if (saved) { applyRoutes(saved, id); resetForm(); renderSavedRoutes(); message("Journey saved. Close settings to see its departures.", true); }
};

async function boot() {
  const sequence = ++bootSequence;
  showState("Loading your routes…", "Your departure board will appear here.");
  try {
    const [saved, health] = await Promise.all([api("/api/routes"), api("/api/health")]);
    if (sequence !== bootSequence) return;
    tokenRequired = Boolean(health.write_token_required);
    if (Number.isFinite(health.refresh_seconds)) refreshMs = Math.max(5000, health.refresh_seconds * 1000);
    routes = saved;
    const deep = new URLSearchParams(location.search).get("route"), last = memory.get();
    const wanted = deep || last;
    current = routes.some((route) => route.id === wanted) ? wanted : routes[0]?.id || null;
    renderTabs(); updateHeading();
    if (current) {
      if (deep && !routes.some((route) => route.id === deep)) globalWarning = "That saved route is no longer available. Showing your first route; choose another tab or add it in settings.";
      memory.set(current);
      const url = new URL(location.href); url.searchParams.set("route", current);
      history.replaceState(null, "", url.pathname + url.search + url.hash);
      renderBoard(); await loadBoard(current, true);
    } else renderBoard();
  } catch (error) {
    if (sequence !== bootSequence) return;
    showState("Couldn't load your routes", error.message, [["Try again", boot], ["Reload page", () => location.reload()]]);
  }
}
function tick() { $("clock").textContent = london(new Date()); $("clock").dateTime = new Date().toISOString(); }
document.addEventListener("visibilitychange", () => {
  tick(); clearTimeout(refreshTimer);
  if (document.hidden) { for (const state of boards.values()) state.controller?.abort(); }
  else if (current) loadBoard(current);
  if (current) renderBoard();
});
window.addEventListener("popstate", () => {
  const id = new URLSearchParams(location.search).get("route");
  if (routes.some((route) => route.id === id)) selectRoute(id);
});
tick(); setInterval(tick, 10000); boot();
