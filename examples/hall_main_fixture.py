"""Deterministic versioned hall fixture used by the README and its test."""

from __future__ import annotations

import json
from pathlib import Path

from jiangnan_agent.assets import module_from_asset
from jiangnan_agent.assembly.model import Assembly
from jiangnan_agent.io import JiangnanProject


def create_hall_main_fixture() -> JiangnanProject:
    config_path = Path(__file__).with_name("hall_v1_parameters.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    module = module_from_asset(
        "hall-main",
        config["asset_id"],
        config["parameters"],
        schema_version=config["parameter_schema_version"],
        asset_version=config["asset_version"],
    )
    return JiangnanProject(name="Versioned hall fixture", assembly=Assembly((module,)))
