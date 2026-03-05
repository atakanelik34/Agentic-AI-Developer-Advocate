"""Download RevenueCat v2 OpenAPI and refresh endpoint registry JSON."""

from __future__ import annotations

import json
import subprocess
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path

import yaml


OPENAPI_URL = "https://www.revenuecat.com/docs/redocusaurus/plugin-redoc-0.yaml"
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "config" / "revenuecat_v2_endpoints.json"


def _download_openapi() -> str:
    result = subprocess.run(
        ["curl", "-fsSL", OPENAPI_URL],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _extract_registry(openapi_yaml: str) -> dict[str, object]:
    spec = yaml.safe_load(openapi_yaml)
    paths = spec.get("paths", {}) if isinstance(spec, dict) else {}

    registry: OrderedDict[str, list[str]] = OrderedDict()
    for path in sorted(paths.keys()):
        item = paths[path]
        if not isinstance(item, dict):
            continue
        methods = sorted(
            method.upper()
            for method in item.keys()
            if method.lower() in {"get", "post", "put", "patch", "delete"}
        )
        registry[path] = methods

    return {
        "source": OPENAPI_URL,
        "base_url": "https://api.revenuecat.com/v2",
        "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "endpoint_count": len(registry),
        "paths": registry,
    }


def main() -> None:
    openapi_yaml = _download_openapi()
    payload = _extract_registry(openapi_yaml)
    DEFAULT_OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Updated {DEFAULT_OUTPUT} with {payload['endpoint_count']} endpoints")


if __name__ == "__main__":
    main()
