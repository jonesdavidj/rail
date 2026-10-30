"""Explicit, one-request live diagnostics: python -m app --check [--raw]."""

import argparse
import json
from datetime import datetime

from app.config import Settings, load_config
from app.normalise import LONDON, normalise_board, objects
from app.rail_data import ProviderError, RailDataProvider


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--raw", action="store_true", help="Print the first raw service as well")
    parser.add_argument("--route", default="out", help="Saved route ID (default: out)")
    args = parser.parse_args()
    settings = Settings.from_environment()
    routes = load_config(settings.data_path).config.routes
    route = next((route for route in routes if route.id == args.route), None)
    if route is None:
        parser.error("Unknown saved route ID")
    now = datetime.now(LONDON)
    try:
        # Always live: never let a successful Demo response masquerade as a key check.
        result = RailDataProvider(settings).board(route, 0, now)
        board = normalise_board(result.raw, route.destination, now)
    except ProviderError as error:
        print(f"FAILED [{error.code}]: {error}")
        return 1
    print(f"LIVE: {route.origin} to {route.destination}")
    if args.raw:
        services = objects(result.raw.get("trainServices")) or objects(
            result.raw.get("busServices")
        )
        print("First raw service:")
        print(json.dumps(services[0] if services else None, indent=2, ensure_ascii=False))
    print(board.model_dump_json(indent=2, exclude_none=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
