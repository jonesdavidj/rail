# Departure board visual review

Reviewed 2026-10-30 on Demo data using system Chromium through a temporary
Playwright script. The script lives only in ignored work/; no browser tests,
Playwright dependency, package.json or browser CI job are committed.

| Scene | Phone: 390 × 844 viewport | Tablet: 1024 × 900 viewport |
|---|---|---|
| Surbiton → Waterloo | [out-390.png](out-390.png) | [out-1024.png](out-1024.png) |
| Waterloo → Surbiton | [back-390.png](back-390.png) | [back-1024.png](back-1024.png) |
| Expanded stops | [stops-390.png](stops-390.png) | [stops-1024.png](stops-1024.png) |
| Cancelled row and reason | [cancelled-390.png](cancelled-390.png) | [cancelled-1024.png](cancelled-1024.png) |
| Settings sheet | [settings-390.png](settings-390.png) | [settings-1024.png](settings-1024.png) |
| Station search | [search-390.png](search-390.png) | [search-1024.png](search-1024.png) |
| Open notices | [notices-390.png](notices-390.png) | [notices-1024.png](notices-1024.png) |

[Phone form scrolled to walking time and return controls](settings-form-390.png).
Board/stops/notices images include full scrollable content; settings and cancelled
row images show the viewport. Phone capture uses touch/mobile emulation. Times
are generated relative to capture time, not a frozen live timetable.

Review and corrections:

- Checked both default tabs, orange expected times, TBC platforms, red cancellation
  strike-through/reason, carriage omission, stop counts and replacement-bus labels.
- Compact tablet rows retain readable primary times; the mobile form scrolls inside
  a fixed sheet header. No horizontal page overflow at either requested width.
- Corrected the Demo Earlsfield CRS (EAD, not EAR/Earley) and propagated delay
  estimates through intermediate calls before the final captures.
- Preserved expansion through a real 30-second refresh: aria-expanded remained true
  and the refreshed stops had animation-name none. Reduced-motion emulation also
  produced animation-name none.
- Exercised keyboard tab navigation and station selection, add-with-return, walking
  time, edit, reorder, reload/last-tab restoration, remove and Earlier/Later. All
  temporary route writes used work/ui-data, not production state, and were removed.
- Viewed a real browser-offline error state and corrected spacing/action guidance.
  No external page requests or JavaScript page errors were observed.
- Text palette contrast checked numerically against the dark surfaces; focus rings,
  keyboard selection and native dialog focus containment reviewed in Chromium.

Physical iPhone installation/VoiceOver and real wall-tablet hardware were not
available. Manifest and icons are supplied; confirm Safari Add to Home Screen
and physical-device ergonomics after deployment. No live feed key was used.
