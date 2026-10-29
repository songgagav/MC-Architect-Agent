from __future__ import annotations

import re
from pathlib import Path

from jiangnan_agent.io.project_json import load_project


PROJECT_ROOT = Path(__file__).resolve().parents[1]
README_PATH = PROJECT_ROOT / "README.md"
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
    assert loaded.revision_cursor == 1
