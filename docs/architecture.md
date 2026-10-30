# Architecture

See [runtime ADR](adr/001-runtime.md), [route config ADR](adr/002-route-config.md)
and [normalisation/paging ADR](adr/003-normalisation-and-paging.md).

app/main.py is the HTTP boundary; config.py validates runtime routes; providers.py
produces raw boards; normalise.py maps them to models.py; paging.py builds pages.
app/static/index.html is a minimal API preview. app/data contains only reference
station data and its licence, never user configuration. tests/ is entirely offline.
