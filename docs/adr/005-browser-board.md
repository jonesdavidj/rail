# ADR 005: A same-origin, framework-free departure board

Status: implemented.

Use native HTML, CSS and JavaScript, served by the existing FastAPI process. The
prototype's dark/amber monospace board remains the visual baseline. No bundler,
Node runtime, third-party fonts, component framework or external runtime assets
are required. Keep the Python provider/normaliser contract as the source of data;
write all server-provided strings with textContent (or form value/ARIA attributes).

Route tabs come from the API. The URL's route ID takes priority over the device's
last route in localStorage. Paging history, disclosures and notice expansion are
kept per route in memory. Stable service IDs preserve open stops across refresh;
only an explicit opening action adds the animation class. DOM refresh restores
keyboard focus. Reduced motion disables this animation.

One timer refreshes the visible route at the server-configured interval (30 seconds
by default). visibilitychange clears it and aborts an in-flight browser request;
returning to the page immediately refreshes. London time is explicit in Intl.
Cache errors/age are displayed, rather than converting old data into fresh data.

The settings sheet uses native dialog focus containment/Escape and an accessible
station combobox. Add/edit/remove use existing APIs. Add PUT /api/routes/order to
validate membership and atomically persist a permutation under the same route-store
lock. This avoids deleting and recreating routes to change tab order. The optional
admin token is supplied only to write endpoints, never persisted in browser storage,
and is cleared when the sheet closes. Health exposes only whether it is required.

A local manifest, 192/512 PNG icons, SVG favicon, Apple touch icon and standalone
Apple metadata support iPhone Add to Home Screen. HTTPS is provided by existing
Caddy/Cloudflare ingress. Offline departure caching is disabled to avoid presenting
old times as current; no service worker or background polling is introduced.

Visual review uses a temporary Playwright script in ignored work/, not a committed
browser test suite. Screenshots and review notes live in docs/screenshots. A single
focused config test protects route-order membership/persistence; no frontend unit
tooling or CI browser job is added.
