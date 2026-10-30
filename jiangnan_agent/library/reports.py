"""Stable JSON report formatting and non-overwriting export helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import StyleAnalysis


def style_analysis_document(analysis: StyleAnalysis) -> dict[str, Any]:
    return {
        "report_type": "minecraft_style_analysis",
        "report_version": 1,
        "analysis_id": analysis.analysis_id,
        "revision": analysis.revision,
        "profile_id": analysis.profile_id,
        "profile_version": analysis.profile_version,
        "status": analysis.status,
        "source_assets": [
            {"asset_id": asset_id, "version": version}
            for asset_id, version in analysis.source_assets
        ],
        "review": {
            "reviewer": analysis.reviewer,
            "reviewed_at": analysis.reviewed_at,
            "note": analysis.review_note,
        },
        "created_at": analysis.created_at,
        "analysis": dict(analysis.analysis),
    }


def export_json_no_overwrite(document: object, destination: str | Path) -> Path:
    """Write UTF-8 JSON using exclusive creation, preserving any existing path."""
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)
    return path
