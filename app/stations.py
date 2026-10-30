"""Search the bundled CRS catalogue without external dependencies."""

import re

from app.config import STATIONS


def search_stations(query: str) -> list[dict[str, str]]:
    query = query.strip().casefold()
    if not query:
        return []
    terms = query.split()
    matches: list[tuple[int, str, str]] = []
    for crs, name in STATIONS.items():
        code, lowered = crs.casefold(), name.casefold()
        words = re.findall(r"\w+", lowered)
        if code == query:
            rank = 0
        elif code.startswith(query):
            rank = 1
        elif lowered.startswith(query):
            rank = 2
        elif all(any(word.startswith(term) for word in words) for term in terms):
            rank = 3
        else:
            continue
        matches.append((rank, name, crs))
    return [{"crs": crs, "name": name} for _, name, crs in sorted(matches)[:10]]
