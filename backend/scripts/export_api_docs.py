"""Write docs/API.md from the application's own OpenAPI schema.

Run from ``backend/``::

    python -m scripts.export_api_docs

Generating the document from the code keeps it from drifting out of date.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.errors import STATUS_BY_CODE
from app.main import app

OUTPUT = Path(__file__).resolve().parents[2] / "docs" / "API.md"


def _resolve(schema: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    """Follow a ``$ref`` into components.schemas."""
    ref = schema.get("$ref")
    if not ref:
        return schema
    return spec["components"]["schemas"][ref.rsplit("/", 1)[-1]]  # type: ignore[no-any-return]


def _type_of(prop: dict[str, Any]) -> str:
    """Short human-readable type for a schema property."""
    if "$ref" in prop:
        return prop["$ref"].rsplit("/", 1)[-1]
    if "anyOf" in prop:
        return " | ".join(_type_of(item) for item in prop["anyOf"])
    kind = prop.get("type", "any")
    if kind == "array":
        return f"{_type_of(prop.get('items', {}))}[]"
    if "enum" in prop:
        return " | ".join(f'"{value}"' for value in prop["enum"])
    return str(kind)


def _fields(schema: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    """Markdown table rows for an object schema."""
    schema = _resolve(schema, spec)
    required = set(schema.get("required", []))
    rows = []
    for name, prop in schema.get("properties", {}).items():
        mark = "yes" if name in required else "no"
        description = str(prop.get("description", "")).replace("\n", " ")
        # A literal pipe would end the table cell, so escape it.
        kind = _type_of(prop).replace("|", "\\|")
        rows.append(f"| `{name}` | `{kind}` | {mark} | {description} |")
    return rows


def build() -> str:
    """Render the full markdown document."""
    spec = app.openapi()
    out: list[str] = [
        "# API reference",
        "",
        f"StegaGuard API v{spec['info']['version']}. Generated from the OpenAPI schema by "
        "`python -m scripts.export_api_docs`; live docs are at `/docs` when the backend runs.",
        "",
        "All endpoints live under `/api`. Errors always use one envelope:",
        "",
        "```json",
        json.dumps(
            {"error": {"code": "CAPACITY_EXCEEDED", "message": "…", "details": {}}},
            indent=2,
            ensure_ascii=False,
        ),
        "```",
        "",
        "| Error code | HTTP status |",
        "|---|---|",
    ]
    out += [f"| `{code}` | {status} |" for code, status in STATUS_BY_CODE.items()]
    out += [
        "",
        "Verification failures inside `/extract` are reported in a normal `200` response (see the "
        "stages list); input problems use the envelope above.",
        "",
    ]
    for path, methods in sorted(spec["paths"].items()):
        for verb, operation in methods.items():
            out += [f"## `{verb.upper()} {path}`", ""]
            if operation.get("summary"):
                out += [f"**{operation['summary']}**", ""]
            if operation.get("description"):
                out += [str(operation["description"]), ""]
            body = operation.get("requestBody", {}).get("content", {})
            for content_type, content in body.items():
                out += [f"Request body (`{content_type}`):", ""]
                out += ["| Field | Type | Required | Description |", "|---|---|---|---|"]
                out += _fields(content["schema"], spec) + [""]
            responses = operation.get("responses", {})
            ok = responses.get("200", {}).get("content", {}).get("application/json", {})
            if ok.get("schema"):
                resolved = _resolve(ok["schema"], spec)
                title = resolved.get("title", "JSON")
                out += [f"Response `200` (`{title}`):", ""]
                if resolved.get("properties"):
                    out += ["| Field | Type | Required | Description |", "|---|---|---|---|"]
                    out += _fields(ok["schema"], spec) + [""]
            errors = sorted(code for code in responses if code != "200" and code != "422")
            if errors:
                out += ["Possible error statuses: " + ", ".join(f"`{c}`" for c in errors), ""]
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    """Write the document and report where it went."""
    OUTPUT.write_text(build(), encoding="utf-8")
    print(f"Wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
