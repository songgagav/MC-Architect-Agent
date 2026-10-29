from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def test_mcp_stdio_lists_strict_tools_and_creates_a_project_module(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pytest.importorskip("mcp", reason="install the optional [mcp] extra to run the protocol test")
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    async def exercise_server() -> None:
        repository_root = Path(__file__).resolve().parents[1]
        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "jiangnan_agent.agent_tools.mcp_server", "--workspace-root", str(tmp_path)],
            cwd=str(repository_root),
        )
        with open(os.devnull, "w", encoding="utf-8") as error_log:
            async with stdio_client(server, errlog=error_log) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    tools = {tool.name: tool for tool in listed.tools}
                    expected_names = {
                        "list_knowledge_rules",
                        "list_projects",
                        "get_project",
                        "list_modules",
                        "get_module",
                        "create_project",
                        "create_module",
                        "set_parameters",
                        "transform_module",
                        "connect_modules",
                        "replace_module",
                        "validate_assembly",
                        "inspect_changes",
                        "export_schematic",
                    }
                    assert set(tools) == expected_names
                    assert all(tool.inputSchema["additionalProperties"] is False for tool in tools.values())

                    knowledge_schema = tools["list_knowledge_rules"].inputSchema
                    assert knowledge_schema["type"] == "object"
                    assert set(knowledge_schema["properties"]) == {
                        "region",
                        "building_type",
                        "evidence_kind",
                        "knowledge_version",
                    }

                    schema = tools["create_module"].inputSchema
                    assert schema["type"] == "object"
                    assert schema["additionalProperties"] is False
                    assert set(schema["required"]) == {"project_path", "module_id", "kind", "parameters"}
                    assert schema["properties"]["parameters"]["type"] == "object"

                    projects = await session.call_tool("list_projects", {})
                    assert projects.isError is False
                    knowledge = await session.call_tool(
                        "list_knowledge_rules",
                        {
                            "region": "cn.anhui.south.huizhou",
                            "building_type": "residential_building",
                            "evidence_kind": "literature_fact",
                        },
                    )
                    assert knowledge.isError is False
                    knowledge_text = "\n".join(item.text for item in knowledge.content if hasattr(item, "text"))
                    assert "hui-materials-and-gable-decoration" in knowledge_text
                    assert "https://www.huangshan.gov.cn/zjhs/rwhz/hpjz/8294057.html" in knowledge_text
                    assert not (tmp_path / "workspace").exists()
                    extra_argument = await session.call_tool(
                        "create_project",
                        {"name": "Ignored data", "project_path": "ignored.json", "unexpected": True},
                    )
                    assert extra_argument.isError is True
                    assert not (tmp_path / "workspace" / "projects" / "ignored.json").exists()
                    created = await session.call_tool(
                        "create_project",
                        {"name": "Three-bay residence", "project_path": "residence.json"},
                    )
                    assert created.isError is False
                    module = await session.call_tool(
                        "create_module",
                        {
                            "project_path": "residence.json",
                            "module_id": "hall-main",
                            "kind": "hall",
                            "parameters": {"bay_count": 3},
                        },
                    )
                    assert module.isError is False
                    project_file = tmp_path / "workspace" / "projects" / "residence.json"
                    saved = json.loads(project_file.read_text(encoding="utf-8"))
                    assert saved["assembly"]["modules"][0]["module_id"] == "hall-main"

    asyncio.run(exercise_server())
    assert capsys.readouterr().out == ""


def test_cli_import_succeeds_when_mcp_module_is_unavailable(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    blocker = """
import sys
from importlib.abc import MetaPathFinder

class BlockMcp(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'mcp' or fullname.startswith('mcp.'):
            raise ModuleNotFoundError('MCP blocked for optional-dependency test', name=fullname)
        return None

sys.meta_path.insert(0, BlockMcp())
import jiangnan_agent.cli
"""
    result = subprocess.run(
        [sys.executable, "-c", blocker],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
