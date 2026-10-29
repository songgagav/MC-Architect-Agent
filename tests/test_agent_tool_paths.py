from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from jiangnan_agent.agent_tools.project_access import ProjectAccess


def test_project_access_resolves_confined_relative_paths(tmp_path: Path) -> None:
    project_root = tmp_path / "workspace" / "projects"
    export_root = tmp_path / "workspace" / "exports"
    project_root.mkdir(parents=True)
    export_root.mkdir(parents=True)
    project_file = project_root / "sample.jap.json"
    project_file.write_text("{}", encoding="utf-8")
    access = ProjectAccess(tmp_path)

    assert access.resolve_project_path("sample.jap.json", operation="read") == project_file.resolve()
    assert access.resolve_project_path("sample.jap.json", operation="edit") == project_file.resolve()
    assert access.resolve_project_path("new/sample.jap.json", operation="create") == (
        project_root / "new" / "sample.jap.json"
    ).resolve()
    assert access.resolve_export_path("sample.schem") == (export_root / "sample.schem").resolve()


@pytest.mark.parametrize(
    "relative_path",
    (
        "../outside.jap.json",
        "sub/../../outside.jap.json",
        r"C:\outside\project.jap.json",
        r"\outside\project.jap.json",
        "wrong.txt",
    ),
)
def test_paths_reject_traversal_absolute_and_wrong_suffix(tmp_path: Path, relative_path: str) -> None:
    access = ProjectAccess(tmp_path)

    with pytest.raises(ValueError):
        access.resolve_project_path(relative_path, operation="create")


@pytest.mark.parametrize(
    "relative_path",
    (
        r"\rooted\project.jap.json",
        r"C:drive-relative.jap.json",
        r"C:\absolute\project.jap.json",
        r"\\server\share\project.jap.json",
        r"\\?\C:\workspace\projects\project.jap.json",
        r"\\.\C:\workspace\projects\project.jap.json",
        r"sub\..\..\outside.jap.json",
    ),
)
def test_platform_independent_path_classifier_rejects_windows_anchors_and_traversal(
    relative_path: str,
) -> None:
    assert ProjectAccess._is_unsafe_relative_path(relative_path)


def test_project_access_enforces_read_edit_and_create_existence(tmp_path: Path) -> None:
    project_root = tmp_path / "workspace" / "projects"
    project_root.mkdir(parents=True)
    existing = project_root / "existing.jap.json"
    existing.write_text("{}", encoding="utf-8")
    access = ProjectAccess(tmp_path)

    with pytest.raises(ValueError, match="does not exist"):
        access.resolve_project_path("missing.jap.json", operation="read")
    with pytest.raises(ValueError, match="does not exist"):
        access.resolve_project_path("missing.jap.json", operation="edit")
    with pytest.raises(ValueError, match="already exists"):
        access.resolve_project_path("existing.jap.json", operation="create")
    with pytest.raises(ValueError):
        access.resolve_export_path("wrong.txt")


def test_paths_reject_traversal_absolute_and_symlink_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = tmp_path / "workspace" / "projects"
    project_root.mkdir(parents=True)
    outside = tmp_path / "outside.jap.json"
    access = ProjectAccess(tmp_path)
    candidate = project_root / "linked.jap.json"
    real_resolve = Path.resolve

    def resolve_with_external_link(path: Path, strict: bool = False) -> Path:
        if path == candidate:
            return outside
        return real_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", resolve_with_external_link)

    with pytest.raises(ValueError):
        access.resolve_project_path("linked.jap.json", operation="create")


def test_project_access_rejects_real_symlink_escape(tmp_path: Path) -> None:
    project_root = tmp_path / "workspace" / "projects"
    project_root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    access = ProjectAccess(tmp_path)
    link = project_root / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError):
        if not _create_windows_junction(link, outside):
            pytest.skip("the current Windows account cannot create a directory symlink or junction")

    with pytest.raises(ValueError, match="outside"):
        access.resolve_project_path(r"linked\escape.jap.json", operation="create")


def test_project_access_rejects_symlink_loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = tmp_path / "workspace" / "projects"
    project_root.mkdir(parents=True)
    candidate = project_root / "loop" / "escape.jap.json"
    access = ProjectAccess(tmp_path)
    real_resolve = Path.resolve

    def resolve_with_loop(path: Path, strict: bool = False) -> Path:
        if path == candidate:
            raise RuntimeError("Symlink loop")
        return real_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", resolve_with_loop)

    with pytest.raises(ValueError, match="outside"):
        access.resolve_project_path(r"loop\escape.jap.json", operation="create")


def _create_windows_junction(link: Path, target: Path) -> bool:
    if not (link.anchor and target.anchor and link.anchor[0].isalpha()):
        return False
    escaped_link = str(link).replace("'", "''")
    escaped_target = str(target).replace("'", "''")
    script = (
        "$ErrorActionPreference = 'Stop'; "
        f"New-Item -ItemType Junction -Path '{escaped_link}' -Target '{escaped_target}' | Out-Null"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0
