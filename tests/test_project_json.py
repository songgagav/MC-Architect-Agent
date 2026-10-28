from __future__ import annotations

from jiangnan_agent.io.project_json import JiangnanProject, load_project, save_project


def test_project_save_and_load_preserves_modules_and_settings(tmp_path) -> None:
    project = JiangnanProject(
        name="苏州厅堂",
        project_id="fixed-project-id",
        modules=[{"id": "hall-1", "custom_extension": {"keep": True}}],
        settings={"seed": 17, "building": {"width": 9}},
    )
    path = tmp_path / "workspace" / "hall.jap.json"

    save_project(project, path)
    loaded = load_project(path)

    assert loaded.to_dict() == project.to_dict()


def test_project_rejects_unknown_format_version() -> None:
    import pytest

    with pytest.raises(ValueError, match="unsupported project format"):
        JiangnanProject.from_dict({"name": "bad", "format_version": 7})
