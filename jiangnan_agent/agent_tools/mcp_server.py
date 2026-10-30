"""MCP stdio adapter for the bounded local project tool service."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import ConfigDict

from .service import ProjectToolService


def _strict_tool(server: FastMCP):
    """Register a typed tool and forbid undeclared or coercible top-level values."""

    def register(function):
        server.add_tool(function)
        # FastMCP v1 builds argument models from signatures but has no public extra-field policy.
        registered = server._tool_manager.get_tool(function.__name__)
        argument_model = registered.fn_metadata.arg_model
        argument_model.model_config = ConfigDict(extra="forbid", strict=True)
        argument_model.model_rebuild(force=True)
        registered.parameters = argument_model.model_json_schema(by_alias=True)
        return function

    return register


def create_mcp_server(workspace_root: Path) -> FastMCP:
    """Build a stdio-capable MCP server around one confined workspace."""

    service = ProjectToolService(workspace_root)
    server = FastMCP(
        "Jiangnan Architect",
        instructions=(
            "Use these tools to edit Jiangnan Minecraft building projects in the configured workspace. "
            "Project paths are relative to workspace/projects and exports are relative to workspace/exports. "
            "Use list_knowledge_rules for sourced architectural claims and preserve the returned evidence kind, "
            "source, confidence, and scope. Never write into Minecraft saves."
        ),
    )

    @_strict_tool(server)
    def list_knowledge_rules(
        region: str | None = None,
        building_type: str | None = None,
        evidence_kind: str | None = None,
        knowledge_version: int | None = None,
    ) -> dict[str, Any]:
        """Read sourced knowledge rules with exact region and building-type filters."""

        return service.list_knowledge_rules(
            region=region,
            building_type=building_type,
            evidence_kind=evidence_kind,
            knowledge_version=knowledge_version,
        )

    @_strict_tool(server)
    def list_projects() -> list[dict[str, Any]]:
        """List projects in the configured workspace."""

        return service.list_projects()

    @_strict_tool(server)
    def get_project(project_path: str) -> dict[str, Any]:
        """Read the metadata for one workspace project."""

        return service.get_project(project_path)

    @_strict_tool(server)
    def list_modules(project_path: str) -> list[dict[str, Any]]:
        """List module summaries in one project."""

        return service.list_modules(project_path)

    @_strict_tool(server)
    def get_module(project_path: str, module_id: str) -> dict[str, Any]:
        """Read one module's parameters, anchors, bounds, and palette summary."""

        return service.get_module(project_path, module_id)

    @_strict_tool(server)
    def create_project(name: str, project_path: str) -> dict[str, Any]:
        """Create a new project without replacing an existing file."""

        return service.create_project(name, project_path)

    @_strict_tool(server)
    def create_module(
        project_path: str,
        module_id: str,
        kind: str,
        parameters: dict[str, Any],
        attach_to_module_id: str | None = None,
        attach_to_anchor_name: str | None = None,
        module_anchor_name: str | None = None,
    ) -> dict[str, Any]:
        """Generate a hall or corridor, optionally placing it at named connected anchors."""

        return service.create_module(
            project_path,
            module_id,
            kind,
            parameters,
            attach_to_module_id=attach_to_module_id,
            attach_to_anchor_name=attach_to_anchor_name,
            module_anchor_name=module_anchor_name,
        )

    @_strict_tool(server)
    def set_parameters(project_path: str, module_id: str, parameter_updates: dict[str, Any]) -> dict[str, Any]:
        """Regenerate one hall or corridor using updated named parameters."""

        return service.set_parameters(project_path, module_id, parameter_updates)

    @_strict_tool(server)
    def transform_module(
        project_path: str,
        module_id: str,
        operation: str,
        offset: list[int] | None = None,
        quarter_turns: int | None = None,
        axis: str | None = None,
    ) -> dict[str, Any]:
        """Translate, rotate around Y, or mirror one module."""

        return service.transform_module(
            project_path,
            module_id,
            operation,
            offset=offset,
            quarter_turns=quarter_turns,
            axis=axis,
        )

    @_strict_tool(server)
    def connect_modules(
        project_path: str,
        first_module_id: str,
        first_anchor_name: str,
        second_module_id: str,
        second_anchor_name: str,
    ) -> dict[str, Any]:
        """Connect two existing modules whose named anchors are already aligned."""

        return service.connect_modules(
            project_path,
            first_module_id,
            first_anchor_name,
            second_module_id,
            second_anchor_name,
        )

    @_strict_tool(server)
    def replace_module(project_path: str, module_id: str, kind: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Replace one module while retaining its recorded geometric transforms."""

        return service.replace_module(project_path, module_id, kind, parameters)

    @_strict_tool(server)
    def validate_assembly(project_path: str) -> dict[str, Any]:
        """Check module collisions, clearances, and connection alignment."""

        return service.validate_assembly(project_path)

    @_strict_tool(server)
    def inspect_changes(project_path: str, revision_id: int | None = None, limit: int = 20) -> dict[str, Any]:
        """Summarize one revision and return at most 100 individual block changes."""

        return service.inspect_changes(project_path, revision_id=revision_id, limit=limit)

    @_strict_tool(server)
    def export_schematic(project_path: str, output_path: str) -> dict[str, Any]:
        """Export a validated project as a Sponge v3 schematic in the workspace exports folder."""

        return service.export_schematic(project_path, output_path)

    return server


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Jiangnan Architect MCP stdio server.")
    parser.add_argument(
        "--workspace-root",
        required=True,
        type=Path,
        help="repository root containing workspace/projects and workspace/exports",
    )
    args = parser.parse_args()
    create_mcp_server(args.workspace_root).run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
