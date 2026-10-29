from __future__ import annotations

import re
from pathlib import Path

from jiangnan_agent.io.project_json import load_project


PROJECT_ROOT = Path(__file__).resolve().parents[1]
README_PATH = PROJECT_ROOT / "README.md"
AGENTS_PATH = PROJECT_ROOT / "AGENTS.md"
MCP_SERVER_PATH = PROJECT_ROOT / "jiangnan_agent" / "agent_tools" / "mcp_server.py"
EXAMPLE_MARKER = "Python API 可按模块 ID 重新生成厅堂或直廊，记录方块差异，并在工程中保留撤销/重做快照："


def test_readme_module_editing_example_runs_from_a_clean_workspace(tmp_path, monkeypatch) -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    section = readme.split(EXAMPLE_MARKER, maxsplit=1)[1]
    match = re.search(r"```python\s*\n(.*?)\n```", section, re.DOTALL)
    assert match is not None, "README module-editing Python example was not found"
    namespace = {"__name__": "__main__"}
    monkeypatch.chdir(tmp_path)

    exec(compile(match.group(1), "README.md Python example", "exec"), namespace)

    project_path = Path(namespace["project_path"])
    loaded = load_project(project_path)
    assert loaded.assembly.modules["hall-main"].parameters["bay_count"] == 5
    assert loaded.assembly.modules["hall-main"].metadata["asset_id"] == "jiangnan.hall"
    assert loaded.assembly.modules["hall-main"].metadata["asset_version"] == 2
    assert loaded.assembly.modules["hall-main"].metadata["knowledge_base_version"] == 2
    assert loaded.assembly.modules["hall-main"].metadata["parameter_config"]["bay_count"] == 5
    assert loaded.revision_cursor == 1


def test_codex_mcp_documentation_matches_the_tool_contract() -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    agents = AGENTS_PATH.read_text(encoding="utf-8")
    server_source = MCP_SERVER_PATH.read_text(encoding="utf-8")
    expected_command = (
        r'codex mcp add jiangnan-architect -- "E:\MCbuild\.venv\Scripts\python.exe" '
        r'-m jiangnan_agent.agent_tools.mcp_server --workspace-root "E:\MCbuild"'
    )
    expected_tools = {
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
    declared_tools = set(re.findall(r"@_strict_tool\(server\)\s*\n\s*def (\w+)\(", server_source))

    assert r'.\.venv\Scripts\python.exe -m pip install -e ".[dev,mcp]"' in readme
    assert expected_command in readme
    assert "codex mcp list" in readme
    assert "重新加载 Codex" in readme
    assert declared_tools == expected_tools
    assert "模块或参数不明确时先询问用户" in agents
    assert "不写入任何 Minecraft 存档" in agents
    assert "inspect_changes" in agents
