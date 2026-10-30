"""Query and import service for the local reference library."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from ..knowledge import KnowledgeBase, load_knowledge_base
from .database import LibraryDatabase
from .errors import AssetIntegrityError, LibraryLookupError, LitematicFormatError
from .litematic import PARSER_VERSION, TARGET_MINECRAFT_DATA_VERSION, analyze_litematic, read_litematic
from .models import (
    ComponentSummary,
    LitematicDocument,
    LitematicRegion,
    ReferenceAsset,
    ReferenceComponent,
    SEMANTIC_COMPONENT_TYPES,
    SemanticAnnotation,
    StyleAnalysis,
)
from .semantics import normalize_annotation_geometry, summarize_annotation

DEFAULT_DATABASE_PATH = Path("workspace/library/architect_library.sqlite3")
_PACKAGE_ROOT = Path(__file__).resolve().parents[2]


class LibraryService:
    """Persistence and read-only query layer; project instances remain outside the library."""

    def __init__(self, database: LibraryDatabase | str | Path, *, project_root: str | Path | None = None) -> None:
        self.database = database if isinstance(database, LibraryDatabase) else LibraryDatabase(database)
        self.project_root = Path(project_root).resolve() if project_root is not None else _PACKAGE_ROOT

    def initialize(self) -> int:
        version = self.database.initialize()
        self._synchronize_catalogs()
        self._upgrade_reference_analyses()
        return version

    def _upgrade_reference_analyses(self) -> None:
        """Recompute stored aggregates when a file was analyzed by an older parser."""

        with self.database.connection() as connection:
            rows = connection.execute(
                """SELECT rf.file_id, rf.sha256, rf.parser_version AS file_parser_version,
                          ra.asset_id, ra.version, ra.source_file, ra.parser_version AS asset_parser_version
                   FROM reference_files rf JOIN reference_assets ra USING(file_id)
                   WHERE rf.parser_version != ? OR ra.parser_version != ?
                   ORDER BY rf.file_id, ra.asset_id, ra.version""",
                (PARSER_VERSION, PARSER_VERSION),
            ).fetchall()
        groups: dict[int, list[sqlite3.Row]] = {}
        for row in rows:
            groups.setdefault(int(row["file_id"]), []).append(row)
        for file_id, assets in groups.items():
            expected_sha = str(assets[0]["sha256"])
            parsed: tuple[Any, Any] | None = None
            failure: Exception | None = None
            for asset in assets:
                path = self._resolve_source_path(str(asset["source_file"]))
                if not path.is_file():
                    continue
                try:
                    actual_sha, byte_size = _sha256(path)
                    if actual_sha != expected_sha:
                        failure = AssetIntegrityError(
                            f"SHA-256 mismatch while upgrading {asset['asset_id']}@{asset['version']}: "
                            f"expected {expected_sha}, got {actual_sha}"
                        )
                        continue
                    document = read_litematic(path)
                    analysis = analyze_litematic(document)
                    final_sha, final_size = _sha256(path)
                    if final_sha != actual_sha or final_size != byte_size:
                        raise AssetIntegrityError("reference Litematic changed while its analysis was upgraded")
                    parsed = (document, analysis)
                    break
                except (AssetIntegrityError, ValueError) as exc:
                    failure = exc
            if parsed is None:
                if failure is not None:
                    raise AssetIntegrityError(
                        f"could not upgrade reference analysis for file SHA-256 {expected_sha}: {failure}"
                    ) from failure
                paths = ", ".join(str(self._resolve_source_path(str(asset["source_file"]))) for asset in assets)
                raise AssetIntegrityError(
                    f"source file is missing while upgrading reference analysis for {expected_sha}: {paths}"
                )
            document, analysis = parsed
            inventory = {
                "file": document.minecraft_data_version,
                "regions": {region.name: region.minecraft_data_version for region in document.regions},
            }
            validation_status = _validation_status(analysis.compatibility_status)
            with self.database.transaction() as connection:
                connection.execute(
                    "DELETE FROM reference_material_counts WHERE file_id = ?", (file_id,)
                )
                connection.execute(
                    "DELETE FROM reference_layer_counts WHERE file_id = ?", (file_id,)
                )
                for block_state, count in analysis.palette_counts.items():
                    connection.execute(
                        "INSERT INTO reference_material_counts(file_id, block_state, block_count) VALUES (?, ?, ?)",
                        (file_id, block_state, count),
                    )
                for y, states in analysis.layer_material_counts.items():
                    for block_state, count in states.items():
                        connection.execute(
                            """INSERT INTO reference_layer_counts(file_id, y, block_state, block_count)
                               VALUES (?, ?, ?, ?)""",
                            (file_id, y, block_state, count),
                        )
                connection.execute(
                    "UPDATE reference_files SET minecraft_data_version = ?, parser_version = ? WHERE file_id = ?",
                    (document.minecraft_data_version, PARSER_VERSION, file_id),
                )
                for asset in assets:
                    row = connection.execute(
                        "SELECT provenance_json FROM reference_assets WHERE asset_id = ? AND version = ?",
                        (asset["asset_id"], asset["version"]),
                    ).fetchone()
                    provenance = _loads(row["provenance_json"])
                    provenance["data_version_inventory"] = inventory
                    connection.execute(
                        """UPDATE reference_assets SET dimensions_json = ?, block_count = ?,
                                  block_palette_json = ?, bounding_box_json = ?, validation_status = ?,
                                  author = ?, provenance_json = ?, parser_version = ?
                           WHERE asset_id = ? AND version = ?""",
                        (
                            _json(list(analysis.dimensions)),
                            analysis.block_count,
                            _json(dict(analysis.palette_counts)),
                            _json([list(analysis.bounding_box[0]), list(analysis.bounding_box[1])]),
                            validation_status,
                            document.author or "unknown",
                            _json(provenance),
                            PARSER_VERSION,
                            asset["asset_id"],
                            asset["version"],
                        ),
                    )

    def _synchronize_catalogs(self) -> None:
        knowledge = load_knowledge_base()
        module_catalog_path = Path(__file__).parent / "catalog" / "v1" / "modules.json"
        module_catalog = _read_json(module_catalog_path)
        module_records = module_catalog.get("modules")
        if not isinstance(module_records, list):
            raise ValueError(f"module catalog has no modules array: {module_catalog_path}")
        style_files = sorted((Path(__file__).parent / "styles" / "v1").glob("*.json"))
        parameter_files = sorted((Path(__file__).parent / "parameters").glob("v*/*.json"))
        style_records = [_read_json(path) | {"_definition_path": _relative_record_path(path)} for path in style_files]
        parameter_records = [(_read_json(path), path) for path in parameter_files]
        with self.database.transaction() as connection:
            self._upsert_knowledge(connection, knowledge)
            for schema, path in parameter_records:
                self._upsert_parameter_schema(connection, schema, path)
            self._upsert_module_catalog(connection, module_records)
            for style in style_records:
                self._upsert_style(connection, style)

    def _upsert_knowledge(self, connection: sqlite3.Connection, knowledge: KnowledgeBase) -> None:
        region_records = [
            {
                "region_id": profile.region_id,
                "label": profile.label,
                "status": profile.status.value,
                "scope": profile.scope,
                "source_ids": list(profile.source_ids),
                "notes": profile.notes,
                "registry_version": knowledge.version,
            }
            for profile in knowledge.regions.values()
        ]
        source_records = [
            {
                "source_id": source.source_id,
                "source_type": source.source_type,
                "title": source.title,
                "locator": source.locator,
                "publisher_or_author": source.publisher_or_author,
                "publication_date": source.publication_date,
                "date_note": source.date_note,
                "url": source.url,
                "doi": source.doi,
                "isbn": source.isbn,
                "section_or_page": source.section_or_page,
                "verification_level": source.verification_level,
                "accessed_date": source.accessed_date,
                "registry_version": knowledge.version,
            }
            for source in knowledge.sources.values()
        ]
        rule_records = [
            {
                "rule_id": rule.rule_id,
                "source_id": rule.source_id,
                "applicable_regions": list(rule.applicable_regions),
                "building_types": list(rule.building_types),
                "evidence_kind": rule.evidence_kind.value,
                "basis": rule.basis,
                "confidence": rule.confidence.value,
                "scope": rule.scope,
                "statement": rule.statement,
                "verification_level": rule.verification_level,
                "status": rule.status,
                "registry_version": knowledge.version,
            }
            for rule in knowledge.rules
        ]
        snapshot = {
            "version": knowledge.version,
            "sources": sorted(source_records, key=lambda item: item["source_id"]),
            "rules": sorted(rule_records, key=lambda item: item["rule_id"]),
            "regions": sorted(region_records, key=lambda item: item["region_id"]),
        }
        snapshot_json = _json(snapshot)
        snapshot_sha256 = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
        existing_snapshot = connection.execute(
            "SELECT content_sha256 FROM knowledge_registry_versions WHERE version = ?", (knowledge.version,)
        ).fetchone()
        if existing_snapshot is not None and existing_snapshot["content_sha256"] != snapshot_sha256:
            raise ValueError(
                f"knowledge registry version {knowledge.version} is immutable; create a new version for changed records"
            )
        connection.execute(
            """INSERT OR IGNORE INTO knowledge_registry_versions(version, content_sha256, loaded_at, snapshot_json)
               VALUES (?, ?, ?, ?)""",
            (knowledge.version, snapshot_sha256, _utc_now(), snapshot_json),
        )
        for record in region_records:
            connection.execute(
                """INSERT INTO region_profiles(region_id, label, status, scope, notes, record_json, registry_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(region_id) DO UPDATE SET label=excluded.label, status=excluded.status,
                       scope=excluded.scope, notes=excluded.notes, record_json=excluded.record_json,
                       registry_version=excluded.registry_version""",
                (
                    record["region_id"], record["label"], record["status"], record["scope"],
                    record["notes"], _json(record), record["registry_version"],
                ),
            )
        for record in source_records:
            connection.execute(
                """INSERT INTO knowledge_sources(
                       source_id, source_type, title, publisher_or_author, publication_date, date_note,
                       url, doi, isbn, section_or_page, verification_level, accessed_date, record_json, registry_version
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source_id) DO UPDATE SET source_type=excluded.source_type, title=excluded.title,
                       publisher_or_author=excluded.publisher_or_author, publication_date=excluded.publication_date,
                       date_note=excluded.date_note, url=excluded.url, doi=excluded.doi, isbn=excluded.isbn,
                       section_or_page=excluded.section_or_page, verification_level=excluded.verification_level,
                       accessed_date=excluded.accessed_date, record_json=excluded.record_json,
                       registry_version=excluded.registry_version""",
                (
                    record["source_id"], record["source_type"], record["title"],
                    record["publisher_or_author"], record["publication_date"], record["date_note"],
                    record["url"], record["doi"], record["isbn"], record["section_or_page"],
                    record["verification_level"], record["accessed_date"], _json(record),
                    record["registry_version"],
                ),
            )
        region_ids = set(knowledge.regions)
        for record in rule_records:
            connection.execute(
                """INSERT INTO knowledge_rules(
                       rule_id, source_id, evidence_kind, confidence, basis, scope, statement,
                       verification_level, status, building_types_json, record_json, registry_version
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(rule_id) DO UPDATE SET source_id=excluded.source_id,
                       evidence_kind=excluded.evidence_kind, confidence=excluded.confidence, basis=excluded.basis,
                       scope=excluded.scope, statement=excluded.statement,
                       verification_level=excluded.verification_level, status=excluded.status,
                       building_types_json=excluded.building_types_json, record_json=excluded.record_json,
                       registry_version=excluded.registry_version""",
                (
                    record["rule_id"], record["source_id"], record["evidence_kind"],
                    record["confidence"], record["basis"], record["scope"], record["statement"],
                    record["verification_level"], record["status"], _json(record["building_types"]),
                    _json(record),
                    record["registry_version"],
                ),
            )
            connection.execute("DELETE FROM knowledge_rule_regions WHERE rule_id = ?", (record["rule_id"],))
            for region_id in record["applicable_regions"]:
                if region_id in region_ids:
                    connection.execute(
                        "INSERT INTO knowledge_rule_regions(rule_id, region_id) VALUES (?, ?)",
                        (record["rule_id"], region_id),
                    )

    def _upsert_module_catalog(
        self, connection: sqlite3.Connection, module_records: Sequence[Mapping[str, Any]]
    ) -> None:
        for item in module_records:
            if not isinstance(item, Mapping):
                raise ValueError("module catalog entries must be JSON objects")
            asset_id = _nonempty(item.get("asset_id"), "module asset_id")
            version = _positive_int(item.get("version"), "module version")
            kind = _nonempty(item.get("kind"), "module kind")
            status = _nonempty(item.get("status"), "module status")
            if status not in {"implemented", "planned"}:
                raise ValueError(f"module {asset_id!r} has unsupported status {status!r}")
            schema_id = item.get("parameter_schema_id")
            schema_version = item.get("parameter_schema_version")
            if status == "implemented":
                if not isinstance(schema_id, str) or not isinstance(schema_version, int):
                    raise ValueError(f"implemented module {asset_id!r} must identify a parameter schema")
                schema_path = _PACKAGE_ROOT / "jiangnan_agent" / "parameters" / f"v{schema_version}" / f"{schema_id}.json"
                if not schema_path.is_file():
                    raise ValueError(f"module {asset_id!r} references missing parameter schema: {schema_path}")
                schema_data = _read_json(schema_path)
                if schema_data.get("asset_id") != asset_id or schema_data.get("kind") != kind:
                    raise ValueError(f"module {asset_id!r} parameter schema has incompatible asset/kind")
                self._upsert_parameter_schema(connection, schema_data, schema_path)
            generator_source_id = item.get("generator_source_id")
            if generator_source_id is not None:
                generator_source_id = _nonempty(generator_source_id, "generator_source_id")
            region_ids = _string_list(item.get("region_ids", []), "module region_ids")
            for region_id in region_ids:
                if connection.execute("SELECT 1 FROM region_profiles WHERE region_id = ?", (region_id,)).fetchone() is None:
                    raise ValueError(f"module {asset_id!r} references unregistered region {region_id!r}")
            anchors = _string_list(item.get("anchor_interfaces", []), "module anchor_interfaces")
            dependencies = _string_list(item.get("dependencies", []), "module dependencies")
            previews = _string_list(item.get("preview_files", []), "module preview_files")
            knowledge_rule_ids = _string_list(item.get("knowledge_rule_ids", []), "module knowledge_rule_ids")
            record = dict(item)
            record_json = _json(record)
            existing = connection.execute(
                "SELECT record_json FROM module_assets WHERE asset_id = ? AND version = ?",
                (asset_id, version),
            ).fetchone()
            if existing is not None and existing["record_json"] != record_json:
                raise ValueError(
                    f"module {asset_id!r} version {version} is immutable; create a new version for changed records"
                )
            connection.execute(
                """INSERT INTO module_assets(
                       asset_id, version, kind, status, generator_source_id, parameter_schema_id,
                       parameter_schema_version, definition_path, region_association_kind,
                       anchor_interfaces_json, dependencies_json, preview_files_json, record_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(asset_id, version) DO UPDATE SET kind=excluded.kind, status=excluded.status,
                       generator_source_id=excluded.generator_source_id,
                       parameter_schema_id=excluded.parameter_schema_id,
                       parameter_schema_version=excluded.parameter_schema_version,
                       definition_path=excluded.definition_path,
                       region_association_kind=excluded.region_association_kind,
                       anchor_interfaces_json=excluded.anchor_interfaces_json,
                       dependencies_json=excluded.dependencies_json, preview_files_json=excluded.preview_files_json,
                       record_json=excluded.record_json""",
                (
                    asset_id,
                    version,
                    kind,
                    status,
                    generator_source_id,
                    schema_id,
                    schema_version,
                    _nonempty(item.get("definition_path"), "module definition_path"),
                    _nonempty(item.get("region_association_kind"), "region_association_kind"),
                    _json(anchors),
                    _json(dependencies),
                    _json(previews),
                    record_json,
                ),
            )
            connection.execute(
                "DELETE FROM module_asset_regions WHERE asset_id = ? AND asset_version = ?",
                (asset_id, version),
            )
            for region_id in region_ids:
                connection.execute(
                    "INSERT INTO module_asset_regions(asset_id, asset_version, region_id) VALUES (?, ?, ?)",
                    (asset_id, version, region_id),
                )
            connection.execute(
                "DELETE FROM module_dependencies WHERE asset_id = ? AND asset_version = ?",
                (asset_id, version),
            )
            for dependency in dependencies:
                dependency_id, separator, dependency_version_text = dependency.partition("@")
                if not separator:
                    raise ValueError(f"module dependency must use asset_id@version syntax: {dependency!r}")
                dependency_version = _positive_int(int(dependency_version_text), "dependency version")
                connection.execute(
                    """INSERT INTO module_dependencies(
                           asset_id, asset_version, dependency_asset_id, dependency_version
                       ) VALUES (?, ?, ?, ?)""",
                    (asset_id, version, dependency_id, dependency_version),
                )
            connection.execute(
                "DELETE FROM module_knowledge_rules WHERE asset_id = ? AND asset_version = ?",
                (asset_id, version),
            )
            for rule_id in knowledge_rule_ids:
                if connection.execute("SELECT 1 FROM knowledge_rules WHERE rule_id = ?", (rule_id,)).fetchone() is None:
                    raise ValueError(f"module {asset_id!r} references unknown knowledge rule {rule_id!r}")
                connection.execute(
                    "INSERT INTO module_knowledge_rules(asset_id, asset_version, rule_id) VALUES (?, ?, ?)",
                    (asset_id, version, rule_id),
                )

    def _upsert_parameter_schema(
        self, connection: sqlite3.Connection, record: Mapping[str, Any], path: Path
    ) -> None:
        schema_id = _nonempty(record.get("schema_id"), "parameter schema_id")
        version = _positive_int(record.get("version"), "parameter schema version")
        asset_id = _nonempty(record.get("asset_id"), "parameter schema asset_id")
        kind = _nonempty(record.get("kind"), "parameter schema kind")
        parameters = record.get("parameters")
        if parameters is not None:
            if not isinstance(parameters, Mapping):
                raise ValueError(f"parameter schema {schema_id!r} parameters must be an object")
            categories = _string_list(
                record.get("source_categories", record.get("provenance_categories", [])),
                "parameter source_categories",
            )
            for parameter_name, parameter in parameters.items():
                if not isinstance(parameter_name, str) or not isinstance(parameter, Mapping):
                    raise ValueError(f"parameter schema {schema_id!r} has an invalid parameter entry")
                _nonempty(parameter.get("status"), f"parameter {parameter_name} status")
                for category_field in ("source_category", "derived_category"):
                    category = parameter.get(category_field)
                    if category is not None and category not in categories:
                        raise ValueError(
                            f"parameter {schema_id}.{parameter_name} references unregistered source category {category!r}"
                        )
        elif not isinstance(record.get("independent_fields"), list):
            raise ValueError(f"parameter schema {schema_id!r} must define parameters or independent_fields")
        definition_path = _relative_record_path(path)
        schema_json = _json(record)
        existing = connection.execute(
            "SELECT asset_id, kind, definition_path, schema_json FROM parameter_schemas WHERE schema_id = ? AND version = ?",
            (schema_id, version),
        ).fetchone()
        if existing is not None and (
            existing["asset_id"] != asset_id
            or existing["kind"] != kind
            or existing["definition_path"] != definition_path
            or existing["schema_json"] != schema_json
        ):
            raise ValueError(
                f"parameter schema {schema_id!r} version {version} is immutable; create a new version for changed records"
            )
        connection.execute(
            """INSERT INTO parameter_schemas(schema_id, version, asset_id, kind, definition_path, schema_json)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(schema_id, version) DO UPDATE SET asset_id=excluded.asset_id,
                   kind=excluded.kind, definition_path=excluded.definition_path, schema_json=excluded.schema_json""",
            (schema_id, version, asset_id, kind, definition_path, schema_json),
        )

    def _upsert_style(self, connection: sqlite3.Connection, item: Mapping[str, Any]) -> None:
        profile_id = _nonempty(item.get("profile_id"), "style profile_id")
        version = _positive_int(item.get("version"), "style version")
        region_id = _nonempty(item.get("design_target_region_id"), "style design_target_region_id")
        references = _string_list(item.get("reference_asset_ids", []), "style reference_asset_ids")
        raw_reference_versions = item.get("reference_asset_versions", {})
        if not isinstance(raw_reference_versions, Mapping):
            raise ValueError(f"style profile {profile_id!r} reference_asset_versions must be an object")
        if set(raw_reference_versions) - set(references):
            raise ValueError(f"style profile {profile_id!r} pins an asset version not listed in reference_asset_ids")
        reference_versions = {
            asset_id: _positive_int(asset_version, f"style reference version for {asset_id}")
            for asset_id, asset_version in raw_reference_versions.items()
        }
        if connection.execute("SELECT 1 FROM region_profiles WHERE region_id = ?", (region_id,)).fetchone() is None:
            raise ValueError(f"style profile {profile_id!r} references unknown region {region_id!r}")
        schema_ref = item.get("parameter_schema")
        if schema_ref is not None:
            if not isinstance(schema_ref, Mapping):
                raise ValueError(f"style profile {profile_id!r} parameter_schema must be an object")
            schema_id = _nonempty(schema_ref.get("schema_id"), "style parameter schema_id")
            schema_version = _positive_int(schema_ref.get("version"), "style parameter schema version")
            if connection.execute(
                "SELECT 1 FROM parameter_schemas WHERE schema_id = ? AND version = ?",
                (schema_id, schema_version),
            ).fetchone() is None:
                raise ValueError(f"style profile {profile_id!r} references missing parameter schema {schema_id}@{schema_version}")
        definition_path = _nonempty(item.get("_definition_path"), "style definition path")
        profile_json = _json({key: value for key, value in item.items() if key != "_definition_path"})
        existing = connection.execute(
            "SELECT definition_path, profile_json FROM style_profiles WHERE profile_id = ? AND version = ?",
            (profile_id, version),
        ).fetchone()
        if existing is not None and (
            existing["definition_path"] != definition_path or existing["profile_json"] != profile_json
        ):
            raise ValueError(
                f"style profile {profile_id!r} version {version} is immutable; create a new version for changed records"
            )
        connection.execute(
            """INSERT INTO style_profiles(
                   profile_id, version, label, region_profile_id, status, definition_path, profile_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(profile_id, version) DO UPDATE SET label=excluded.label,
                   region_profile_id=excluded.region_profile_id, status=excluded.status,
                   definition_path=excluded.definition_path, profile_json=excluded.profile_json""",
            (
                profile_id,
                version,
                _nonempty(item.get("label"), "style label"),
                region_id,
                _nonempty(item.get("status"), "style status"),
                definition_path,
                profile_json,
            ),
        )
        for asset_id in references:
            pinned_version = reference_versions.get(asset_id)
            existing_link = connection.execute(
                """SELECT asset_version FROM style_reference_assets
                   WHERE profile_id = ? AND profile_version = ? AND asset_id = ?""",
                (profile_id, version, asset_id),
            ).fetchone()
            if existing_link is not None:
                if pinned_version is None or int(existing_link["asset_version"]) == pinned_version:
                    continue
                connection.execute(
                    """DELETE FROM style_reference_assets
                       WHERE profile_id = ? AND profile_version = ? AND asset_id = ?""",
                    (profile_id, version, asset_id),
                )
            if pinned_version is None:
                row = connection.execute(
                    "SELECT version FROM reference_assets WHERE asset_id = ? ORDER BY version DESC LIMIT 1",
                    (asset_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT version FROM reference_assets WHERE asset_id = ? AND version = ?",
                    (asset_id, pinned_version),
                ).fetchone()
            if row is not None:
                connection.execute(
                    """INSERT INTO style_reference_assets(
                           profile_id, profile_version, asset_id, asset_version, reference_role
                       ) VALUES (?, ?, ?, ?, ?)""",
                    (profile_id, version, asset_id, int(row["version"]), "visual_reference"),
                )

    def import_litematic(
        self,
        source_path: str | Path,
        *,
        asset_id: str,
        name: str | None = None,
        building_type: str = "unspecified",
        region_profile_id: str | None = None,
        style_tags: Sequence[str] = (),
        provenance_note: str | None = None,
        usage_rights: Mapping[str, object] | None = None,
    ) -> ReferenceAsset:
        asset_id = _nonempty(asset_id, "asset_id")
        building_type = _nonempty(building_type, "building_type")
        source = Path(source_path).resolve()
        if not source.is_file():
            raise AssetIntegrityError(f"source Litematic file does not exist: {source}")
        digest_before, byte_size = _sha256(source)
        try:
            document = read_litematic(source)
            analysis = analyze_litematic(document)
        except ValueError as exc:
            raise AssetIntegrityError(f"source file is not a valid Litematic: {exc}") from exc
        digest_after, current_size = _sha256(source)
        if digest_after != digest_before or current_size != byte_size:
            raise AssetIntegrityError("source Litematic changed while it was being read")
        if region_profile_id is not None:
            region_profile_id = _nonempty(region_profile_id, "region_profile_id")
            self._require_active_region(region_profile_id)
        tags = _string_list(list(style_tags), "style_tags")
        display_name = _nonempty(name, "name") if name is not None else (document.name.strip() or source.stem)
        source_file = self._stored_source_path(source)
        provenance = {
            "source_kind": "user_supplied_reference",
            "embedded_author": document.author or None,
            "source_file": source_file,
            "sha256": digest_before,
            "data_version_inventory": {
                "file": document.minecraft_data_version,
                "regions": {region.name: region.minecraft_data_version for region in document.regions},
            },
            "region_attribution": "unverified" if region_profile_id is None else "user_assigned",
            "note": provenance_note or "Imported for visual research; no historical or regional attribution inferred.",
        }
        rights = dict(usage_rights or {})
        rights.setdefault("copyright_holder", document.author or "unknown")
        rights.setdefault("license", "unknown")
        rights.setdefault("redistribution", "not_granted")
        rights.setdefault("note", "No redistribution permission is inferred from possession of the local file.")
        stored_dimensions = _json(list(analysis.dimensions))
        stored_bounds = _json([list(analysis.bounding_box[0]), list(analysis.bounding_box[1])])
        now = _utc_now()
        with self.database.transaction() as connection:
            file_row = connection.execute("SELECT file_id FROM reference_files WHERE sha256 = ?", (digest_before,)).fetchone()
            if file_row is None:
                cursor = connection.execute(
                    """INSERT INTO reference_files(
                           sha256, file_format, byte_size, minecraft_data_version, parser_version
                       ) VALUES (?, 'litematic', ?, ?, ?)""",
                    (digest_before, byte_size, document.minecraft_data_version, PARSER_VERSION),
                )
                file_id = int(cursor.lastrowid)
                for block_state, count in analysis.palette_counts.items():
                    connection.execute(
                        "INSERT INTO reference_material_counts(file_id, block_state, block_count) VALUES (?, ?, ?)",
                        (file_id, block_state, count),
                    )
                for y, states in analysis.layer_material_counts.items():
                    for block_state, count in states.items():
                        connection.execute(
                            """INSERT INTO reference_layer_counts(file_id, y, block_state, block_count)
                               VALUES (?, ?, ?, ?)""",
                            (file_id, y, block_state, count),
                        )
            else:
                file_id = int(file_row["file_id"])
            existing = connection.execute(
                """SELECT version, name, source_file, region_profile_id, building_type, style_tags_json,
                          provenance_json, usage_rights_json
                   FROM reference_assets WHERE asset_id = ? AND file_id = ?""",
                (asset_id, file_id),
            ).fetchone()
            if existing is not None:
                expected = (
                    display_name,
                    source_file,
                    region_profile_id,
                    building_type,
                    _json(tags),
                    _json(provenance),
                    _json(rights),
                )
                actual = tuple(existing[key] for key in (
                    "name", "source_file", "region_profile_id", "building_type", "style_tags_json",
                    "provenance_json", "usage_rights_json",
                ))
                if expected != actual:
                    raise LibraryLookupError(
                        f"asset {asset_id!r} already references this SHA-256 with different metadata; "
                        "use a new asset ID or import a changed file as a new version"
                    )
                return self._reference_by_version(connection, asset_id, int(existing["version"]))
            version_row = connection.execute(
                "SELECT MAX(version) AS latest FROM reference_assets WHERE asset_id = ?", (asset_id,)
            ).fetchone()
            asset_version = 1 if version_row["latest"] is None else int(version_row["latest"]) + 1
            connection.execute(
                """INSERT INTO reference_assets(
                       asset_id, version, file_id, name, source_file, region_profile_id,
                       region_assignment_status, building_type, dimensions_json, block_count,
                       block_palette_json, bounding_box_json, style_tags_json, preview_files_json,
                       import_status, validation_status, author, provenance_json, usage_rights_json,
                       created_at, parser_version
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', 'imported', ?, ?, ?, ?, ?, ?)""",
                (
                    asset_id,
                    asset_version,
                    file_id,
                    display_name,
                    source_file,
                    region_profile_id,
                    "unverified" if region_profile_id is None else "user_assigned",
                    building_type,
                    stored_dimensions,
                    analysis.block_count,
                    _json(dict(analysis.palette_counts)),
                    stored_bounds,
                    _json(tags),
                    _validation_status(analysis.compatibility_status),
                    document.author or "unknown",
                    _json(provenance),
                    _json(rights),
                    now,
                    PARSER_VERSION,
                ),
            )
            self._sync_style_reference_links(connection, asset_id, asset_version)
            return self._reference_by_version(connection, asset_id, asset_version)

    def list_references(self, *, building_type: str | None = None) -> tuple[ReferenceAsset, ...]:
        with self.database.connection() as connection:
            if building_type is None:
                rows = connection.execute(
                    """SELECT ra.*, rf.file_format, rf.sha256, rf.minecraft_data_version
                       FROM reference_assets ra JOIN reference_files rf USING(file_id)
                       ORDER BY ra.asset_id, ra.version"""
                ).fetchall()
            else:
                rows = connection.execute(
                    """SELECT ra.*, rf.file_format, rf.sha256, rf.minecraft_data_version
                       FROM reference_assets ra JOIN reference_files rf USING(file_id)
                       WHERE ra.building_type = ? ORDER BY ra.asset_id, ra.version""",
                    (building_type,),
                ).fetchall()
            return tuple(_asset_from_row(row) for row in rows)

    def get_reference(self, asset_id: str, version: int | None = None) -> ReferenceAsset:
        with self.database.connection() as connection:
            if version is None:
                row = connection.execute(
                    """SELECT ra.*, rf.file_format, rf.sha256, rf.minecraft_data_version
                       FROM reference_assets ra JOIN reference_files rf USING(file_id)
                       WHERE ra.asset_id = ? ORDER BY ra.version DESC LIMIT 1""",
                    (asset_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    """SELECT ra.*, rf.file_format, rf.sha256, rf.minecraft_data_version
                       FROM reference_assets ra JOIN reference_files rf USING(file_id)
                       WHERE ra.asset_id = ? AND ra.version = ?""",
                    (asset_id, version),
                ).fetchone()
            if row is None:
                raise LibraryLookupError(f"unknown reference asset: {asset_id!r}")
            return _asset_from_row(row)

    def propose_annotations(
        self, asset_id: str, version: int | None = None
    ) -> tuple[SemanticAnnotation, ...]:
        """Create deterministic, candidate-only suggestions from explicit block identities."""
        from .annotation_rules import propose_region_annotations
        from .semantics import encode_x_runs

        asset_row = self._asset_file_row_for_reference(asset_id, version)
        asset_version = int(asset_row["version"])
        document, _source_path = self._read_verified_document(asset_id, asset_version)
        proposed: list[SemanticAnnotation] = []
        for region in document.regions:
            for proposal in propose_region_annotations(region):
                runs = encode_x_runs(proposal.positions)
                geometry = {"runs": [list(run) for run in runs]}
                identity = _json([asset_id, asset_version, region.name, proposal.rule_id, geometry])
                annotation_id = "rule." + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
                with self.database.connection() as connection:
                    existing = connection.execute(
                        "SELECT * FROM semantic_annotation_revisions WHERE annotation_id = ? ORDER BY revision DESC LIMIT 1",
                        (annotation_id,),
                    ).fetchone()
                if existing is not None:
                    proposed.append(_annotation_from_row(existing))
                    continue
                proposed.append(
                    self._append_annotation(
                        annotation_id=annotation_id,
                        asset_id=asset_id,
                        asset_version=asset_version,
                        region_name=region.name,
                        component_type=proposal.component_type,
                        geometry_type="block_set",
                        geometry=geometry,
                        source_kind="rule",
                        rule_id=proposal.rule_id,
                        confidence=proposal.confidence,
                        status="candidate",
                        reviewer=None,
                        reviewed_at=None,
                        review_note=None,
                        explanation=proposal.explanation,
                        expected_revision=0,
                    )
                )
        return tuple(proposed)

    def create_annotation(
        self,
        *,
        annotation_id: str,
        asset_id: str,
        region_name: str,
        component_type: str,
        geometry_type: str,
        geometry: Mapping[str, object],
        version: int | None = None,
        confidence: float | None = None,
    ) -> SemanticAnnotation:
        annotation_id = _nonempty(annotation_id, "annotation_id")
        asset_row = self._asset_file_row_for_reference(asset_id, version)
        asset_version = int(asset_row["version"])
        document, _source_path = self._read_verified_document(asset_id, asset_version)
        region = _find_region(document.regions, region_name)
        canonical = normalize_annotation_geometry(region, geometry_type, geometry)
        if component_type not in SEMANTIC_COMPONENT_TYPES:
            raise ValueError(f"unsupported semantic component type: {component_type!r}")
        summarize_annotation(region, component_type, geometry_type, canonical)
        if confidence is not None and (
            isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1
        ):
            raise ValueError("confidence must be between 0 and 1")
        with self.database.connection() as connection:
            existing = connection.execute(
                "SELECT 1 FROM semantic_annotation_revisions WHERE annotation_id = ? LIMIT 1", (annotation_id,)
            ).fetchone()
        if existing is not None:
            raise ValueError(f"annotation ID already exists: {annotation_id!r}")
        return self._append_annotation(
            annotation_id=annotation_id,
            asset_id=asset_id,
            asset_version=asset_version,
            region_name=region_name,
            component_type=component_type,
            geometry_type=geometry_type,
            geometry=canonical,
            source_kind="manual",
            rule_id=None,
            confidence=confidence,
            status="candidate",
            reviewer=None,
            reviewed_at=None,
            review_note=None,
            expected_revision=0,
        )

    def update_annotation(
        self,
        annotation_id: str,
        *,
        component_type: str | None = None,
        geometry_type: str | None = None,
        geometry: Mapping[str, object] | None = None,
        confidence: float | None = None,
        review_note: str | None = None,
    ) -> SemanticAnnotation:
        current = self.get_annotation(annotation_id)
        document, _source_path = self._read_verified_document(current.asset_id, current.asset_version)
        region = _find_region(document.regions, current.region_name)
        new_type = component_type if component_type is not None else current.component_type
        new_geometry_type = geometry_type if geometry_type is not None else current.geometry_type
        raw_geometry = dict(geometry) if geometry is not None else dict(current.geometry)
        canonical = normalize_annotation_geometry(region, new_geometry_type, raw_geometry)
        if new_type not in SEMANTIC_COMPONENT_TYPES:
            raise ValueError(f"unsupported semantic component type: {new_type!r}")
        summarize_annotation(region, new_type, new_geometry_type, canonical)
        if confidence is not None and (
            isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1
        ):
            raise ValueError("confidence must be between 0 and 1")
        return self._append_annotation(
            annotation_id=current.annotation_id,
            asset_id=current.asset_id,
            asset_version=current.asset_version,
            region_name=current.region_name,
            component_type=new_type,
            geometry_type=new_geometry_type,
            geometry=canonical,
            source_kind="manual",
            rule_id=None,
            confidence=confidence,
            status="candidate",
            reviewer=None,
            reviewed_at=None,
            review_note=review_note,
            expected_revision=current.revision,
        )

    def review_annotation(
        self,
        annotation_id: str,
        *,
        reviewer: str,
        decision: str,
        note: str | None = None,
    ) -> SemanticAnnotation:
        current = self.get_annotation(annotation_id)
        if decision not in {"verified", "rejected"}:
            raise ValueError("review decision must be 'verified' or 'rejected'")
        reviewer = _nonempty(reviewer, "reviewer")
        self.analyze_annotation(current.annotation_id, current.revision)
        return self._append_annotation(
            annotation_id=current.annotation_id,
            asset_id=current.asset_id,
            asset_version=current.asset_version,
            region_name=current.region_name,
            component_type=current.component_type,
            geometry_type=current.geometry_type,
            geometry=dict(current.geometry),
            source_kind=current.source_kind,
            rule_id=current.rule_id,
            confidence=current.confidence,
            status=decision,
            reviewer=reviewer,
            reviewed_at=_utc_now(),
            review_note=note,
            expected_revision=current.revision,
        )

    def list_annotations(
        self,
        *,
        asset_id: str | None = None,
        version: int | None = None,
        component_type: str | None = None,
        status: str | None = None,
        annotation_id: str | None = None,
        include_history: bool = False,
    ) -> tuple[SemanticAnnotation, ...]:
        clauses: list[str] = []
        parameters: list[object] = []
        if not include_history:
            clauses.append("(a.annotation_id, a.revision) IN (SELECT annotation_id, MAX(revision) FROM semantic_annotation_revisions GROUP BY annotation_id)")
        for column, value in (("asset_id", asset_id), ("asset_version", version), ("component_type", component_type), ("status", status), ("annotation_id", annotation_id)):
            if value is not None:
                clauses.append(f"a.{column} = ?")
                parameters.append(value)
        query = "SELECT a.* FROM semantic_annotation_revisions a"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY a.asset_id, a.asset_version, a.region_name, a.annotation_id, a.revision"
        with self.database.connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(_annotation_from_row(row) for row in rows)

    def get_annotation(self, annotation_id: str, revision: int | None = None) -> SemanticAnnotation:
        with self.database.connection() as connection:
            if revision is None:
                row = connection.execute(
                    "SELECT * FROM semantic_annotation_revisions WHERE annotation_id = ? ORDER BY revision DESC LIMIT 1",
                    (annotation_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM semantic_annotation_revisions WHERE annotation_id = ? AND revision = ?",
                    (annotation_id, revision),
                ).fetchone()
        if row is None:
            raise LibraryLookupError(f"unknown semantic annotation: {annotation_id!r}")
        return _annotation_from_row(row)

    def analyze_annotation(self, annotation_id: str, revision: int | None = None) -> ComponentSummary:
        annotation = self.get_annotation(annotation_id, revision)
        document, _source_path = self._read_verified_document(annotation.asset_id, annotation.asset_version)
        region = _find_region(document.regions, annotation.region_name)
        return summarize_annotation(region, annotation.component_type, annotation.geometry_type, annotation.geometry)

    def register_reference_component(
        self,
        annotation_id: str,
        *,
        name: str,
        style_tags: Sequence[str] = (),
        parameterization_status: str = "not_parameterized",
        revision: int | None = None,
    ) -> ReferenceComponent:
        annotation = self.get_annotation(annotation_id, revision)
        if annotation.status != "verified":
            raise ValueError("reference components can only be registered from a verified annotation")
        if parameterization_status not in {"not_parameterized", "planned"}:
            raise ValueError("reference components cannot be marked as implemented parameterized generators")
        component_name = _nonempty(name, "name")
        tags = _string_list(list(style_tags), "style_tags")
        with self.database.connection() as connection:
            existing = connection.execute(
                "SELECT * FROM reference_components WHERE annotation_id = ? AND annotation_revision = ?",
                (annotation.annotation_id, annotation.revision),
            ).fetchone()
        if existing is not None:
            component = _component_from_row(existing)
            if component.name != component_name or component.style_tags != tuple(tags):
                raise ValueError("a registered component version is immutable; create a new annotation revision")
            return component
        summary = self.analyze_annotation(annotation.annotation_id, annotation.revision)
        component_id = "reference-component." + hashlib.sha256(annotation_id.encode("utf-8")).hexdigest()[:20]
        with self.database.transaction() as connection:
            version_row = connection.execute(
                "SELECT MAX(version) FROM reference_components WHERE component_id = ?", (component_id,)
            ).fetchone()
            component_version = 1 if version_row[0] is None else int(version_row[0]) + 1
            now = _utc_now()
            record = _component_record(
                component_id=component_id,
                version=component_version,
                annotation=annotation,
                summary=summary,
                name=component_name,
                style_tags=tags,
                parameterization_status=parameterization_status,
                created_at=now,
            )
            connection.execute(
                """INSERT INTO reference_components(
                       component_id, version, source_asset_id, source_asset_version, annotation_id,
                       annotation_revision, name, component_type, region_name, origin_json,
                       dimensions_json, bounding_box_json, block_count, block_states_json,
                       materials_json, layer_materials_json, coordinate_runs_json, style_tags_json,
                       component_status, parameterization_status, created_at, record_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record["component_id"], record["version"], record["source_asset_id"],
                    record["source_asset_version"], record["annotation_id"], record["annotation_revision"],
                    record["name"], record["component_type"], record["region_name"], _json(record["local_origin"]),
                    _json(record["dimensions"]), _json(record["bounding_box"]), record["block_count"],
                    _json(record["block_states"]), _json(record["materials"]), _json(record["layer_materials"]),
                    _json(record["coordinate_runs"]), _json(record["style_tags"]), record["component_status"],
                    record["parameterization_status"], now, _json(record),
                ),
            )
            saved = connection.execute(
                "SELECT * FROM reference_components WHERE component_id = ? AND version = ?",
                (component_id, component_version),
            ).fetchone()
        return _component_from_row(saved)

    def list_reference_components(
        self, *, source_asset_id: str | None = None, component_type: str | None = None
    ) -> tuple[ReferenceComponent, ...]:
        clauses: list[str] = []
        values: list[object] = []
        if source_asset_id is not None:
            clauses.append("source_asset_id = ?")
            values.append(source_asset_id)
        if component_type is not None:
            clauses.append("component_type = ?")
            values.append(component_type)
        query = "SELECT * FROM reference_components"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY source_asset_id, source_asset_version, component_type, component_id, version"
        with self.database.connection() as connection:
            rows = connection.execute(query, values).fetchall()
        return tuple(_component_from_row(row) for row in rows)

    def get_reference_component(self, component_id: str, version: int | None = None) -> ReferenceComponent:
        with self.database.connection() as connection:
            if version is None:
                row = connection.execute(
                    "SELECT * FROM reference_components WHERE component_id = ? ORDER BY version DESC LIMIT 1",
                    (component_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM reference_components WHERE component_id = ? AND version = ?",
                    (component_id, version),
                ).fetchone()
        if row is None:
            raise LibraryLookupError(f"unknown reference component: {component_id!r}")
        return _component_from_row(row)

    def export_component_report(
        self, component_id: str, destination: str | Path, version: int | None = None
    ) -> Path:
        from .reports import export_json_no_overwrite

        component = self.get_reference_component(component_id, version)
        annotation = self.get_annotation(component.annotation_id, component.annotation_revision)
        source = self.get_reference(component.source_asset_id, component.source_asset_version)
        document = {
            "report_type": "verified_reference_component",
            "report_version": 1,
            "component": _component_record(
                component_id=component.component_id,
                version=component.version,
                annotation=annotation,
                summary=self.analyze_annotation(annotation.annotation_id, annotation.revision),
                name=component.name,
                style_tags=component.style_tags,
                parameterization_status=component.parameterization_status,
                created_at=component.created_at,
            ),
            "source": {
                "asset_id": source.asset_id,
                "asset_version": source.version,
                "file": source.source_file,
                "sha256": source.sha256,
                "minecraft_data_version": source.minecraft_data_version,
                "region_assignment_status": source.region_assignment_status,
            },
            "review": {
                "annotation_id": annotation.annotation_id,
                "annotation_revision": annotation.revision,
                "reviewer": annotation.reviewer,
                "reviewed_at": annotation.reviewed_at,
                "note": annotation.review_note,
            },
            "usage_rights": dict(source.usage_rights),
            "limitations": [
                "This is a static Minecraft reference component, not a parameterized generator.",
                "The reference region and historical provenance remain unverified unless explicitly sourced.",
            ],
        }
        path = Path(destination)
        if not path.is_absolute():
            path = self.project_root / path
        try:
            return export_json_no_overwrite(document, path)
        except FileExistsError:
            raise
        except OSError as exc:
            raise AssetIntegrityError(f"could not export component report to {path}: {exc}") from exc

    def create_style_analysis(
        self,
        profile_id: str,
        *,
        profile_version: int | None = None,
        source_assets: Sequence[tuple[str, int]] | None = None,
        analysis_id: str | None = None,
    ) -> StyleAnalysis:
        with self.database.connection() as connection:
            if profile_version is None:
                profile = connection.execute(
                    "SELECT * FROM style_profiles WHERE profile_id = ? ORDER BY version DESC LIMIT 1", (profile_id,)
                ).fetchone()
            else:
                profile = connection.execute(
                    "SELECT * FROM style_profiles WHERE profile_id = ? AND version = ?",
                    (profile_id, profile_version),
                ).fetchone()
            if profile is None:
                raise LibraryLookupError(f"unknown style profile: {profile_id!r}")
            pinned_rows = connection.execute(
                """SELECT asset_id, asset_version FROM style_reference_assets
                   WHERE profile_id = ? AND profile_version = ? ORDER BY asset_id, asset_version""",
                (profile_id, int(profile["version"])),
            ).fetchall()
        pinned_sources = tuple((str(row["asset_id"]), int(row["asset_version"])) for row in pinned_rows)
        if source_assets is None:
            selected_sources = pinned_sources
        else:
            selected_sources = tuple(sorted((str(asset_id), _positive_int(version, "source asset version")) for asset_id, version in source_assets))
            if len(set(selected_sources)) != len(selected_sources):
                raise ValueError("style analysis source assets must be unique")
            missing = sorted(set(selected_sources) - set(pinned_sources))
            if missing:
                raise LibraryLookupError(
                    f"style profile {profile_id!r}@{profile['version']} does not pin requested source(s): {missing}"
                )
        if not selected_sources:
            raise LibraryLookupError(
                f"style profile {profile_id!r}@{profile['version']} has no imported, version-pinned reference assets"
            )

        asset_reports: list[dict[str, Any]] = []
        for source_asset_id, source_asset_version in selected_sources:
            document, _path = self._read_verified_document(source_asset_id, source_asset_version)
            asset = self.get_reference(source_asset_id, source_asset_version)
            analysis = analyze_litematic(document)
            states_by_material: dict[str, int] = {}
            for state_key, count in analysis.palette_counts.items():
                material = state_key.split("[", 1)[0]
                states_by_material[material] = states_by_material.get(material, 0) + count
            regions: list[dict[str, Any]] = []
            for region in document.regions:
                region_document = LitematicDocument(
                    schematic_version=document.schematic_version,
                    minecraft_data_version=document.minecraft_data_version,
                    name=document.name,
                    author=document.author,
                    regions=(region,),
                    source_metadata=document.source_metadata,
                )
                try:
                    region_analysis = analyze_litematic(region_document)
                except LitematicFormatError as exc:
                    if str(exc) != "Litematic contains no occupied non-air block positions":
                        raise
                    regions.append(
                        {
                            "region_name": region.name,
                            "signed_size": list(region.signed_size),
                            "dimensions": list(region.size),
                            "bounding_box": None,
                            "block_count": 0,
                            "layer_profile": {},
                            "block_palette": {},
                        }
                    )
                    continue
                regions.append(
                    {
                        "region_name": region.name,
                        "signed_size": list(region.signed_size),
                        "dimensions": list(region_analysis.dimensions),
                        "bounding_box": [list(region_analysis.bounding_box[0]), list(region_analysis.bounding_box[1])],
                        "block_count": region_analysis.block_count,
                        "layer_profile": {
                            str(y): dict(states) for y, states in region_analysis.layer_material_counts.items()
                        },
                        "block_palette": dict(region_analysis.palette_counts),
                    }
                )

            annotations = self.list_annotations(asset_id=source_asset_id, version=source_asset_version)
            verified: list[dict[str, Any]] = []
            candidates: list[dict[str, Any]] = []
            rejected: list[dict[str, Any]] = []
            covered: set[tuple[str, int, int, int]] = set()
            for annotation in annotations:
                base = {
                    "annotation_id": annotation.annotation_id,
                    "revision": annotation.revision,
                    "region_name": annotation.region_name,
                    "component_type": annotation.component_type,
                    "source_kind": annotation.source_kind,
                    "rule_id": annotation.rule_id,
                    "confidence": annotation.confidence,
                    "geometry_type": annotation.geometry_type,
                    "geometry": dict(annotation.geometry),
                    "reviewer": annotation.reviewer,
                    "review_note": annotation.review_note,
                }
                if annotation.status == "verified":
                    summary = self.analyze_annotation(annotation.annotation_id, annotation.revision)
                    summary_json = _summary_record(summary)
                    verified.append({**base, "summary": summary_json})
                    for run in summary.coordinate_runs:
                        y, z, x_start, x_end = run
                        origin = summary.local_origin
                        covered.update(
                            (summary.region_name, origin[0] + x, origin[1] + y, origin[2] + z)
                            for x in range(x_start, x_end)
                        )
                elif annotation.status == "candidate":
                    candidates.append(base)
                elif annotation.status == "rejected":
                    rejected.append(base)

            occupied: set[tuple[str, int, int, int]] = {
                (region.name, *position)
                for region in document.regions
                for position, _state in region.iter_non_air_blocks()
            }
            assets_counted = len(occupied)
            proportions = {
                "width_to_height": round(analysis.dimensions[0] / analysis.dimensions[1], 6),
                "depth_to_height": round(analysis.dimensions[2] / analysis.dimensions[1], 6),
                "basis": "measured Minecraft block extents; creative scale convention is 1 block approximately 1 meter",
            }
            asset_reports.append(
                {
                    "asset_id": asset.asset_id,
                    "asset_version": asset.version,
                    "name": asset.name,
                    "sha256": asset.sha256,
                    "minecraft_data_version": asset.minecraft_data_version,
                    "region_profile_id": asset.region_profile_id,
                    "regional_attribution": "unverified" if asset.region_profile_id is None else asset.region_assignment_status,
                    "measurement_status": "measured",
                    "dimensions": list(analysis.dimensions),
                    "bounding_box": [list(analysis.bounding_box[0]), list(analysis.bounding_box[1])],
                    "block_count": analysis.block_count,
                    "proportions": proportions,
                    "materials": dict(sorted(states_by_material.items())),
                    "block_states": dict(analysis.palette_counts),
                    "regions": regions,
                    "annotations": {
                        "verified": verified,
                        "candidates": candidates,
                        "rejected": rejected,
                        "unclassified_occupied_blocks": max(0, assets_counted - len(covered)),
                        "unclassified_count_basis": (
                            "occupied blocks not covered by current verified annotations, counted per Region and coordinate"
                        ),
                    },
                }
            )
        report = {
            "schema": "minecraft-style-analysis/v1",
            "profile": {"profile_id": profile_id, "version": int(profile["version"])},
            "classification": "minecraft_visual_style",
            "regional_attribution": "unverified",
            "historical_standard_claim": "none",
            "scale_convention": {"meters_per_block": 1.0, "status": "creative_design_convention"},
            "assets": asset_reports,
            "style_features": {
                "building_outline": "measured from occupied block bounds",
                "roof_shape_and_layers": "unverified until reviewed semantic annotations exist",
                "palette_and_color": "measured Minecraft block identities; visual color grouping remains a design interpretation",
                "wall_and_timber_relationship": "unverified until reviewed semantic annotations exist",
                "ornament_density": "unverified until decoration regions are manually annotated",
                "construction_relationships": "unknown unless supported by verified annotations",
            },
            "limitations": [
                "The sources are Minecraft creative references; no regional or historical provenance is inferred.",
                "The original Minecraft DataVersion is recorded as source metadata; no version conversion was performed.",
                "Candidate annotations are excluded from verified component measurements.",
            ],
        }
        if analysis_id is None:
            identity = _json([profile_id, int(profile["version"]), selected_sources])
            analysis_id = "style-analysis." + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        else:
            analysis_id = _nonempty(analysis_id, "analysis_id")

        report_json = _json(report)
        with self.database.connection() as connection:
            latest = connection.execute(
                "SELECT * FROM style_analysis_revisions WHERE analysis_id = ? ORDER BY revision DESC LIMIT 1",
                (analysis_id,),
            ).fetchone()
        if latest is not None and latest["analysis_json"] == report_json:
            return self.get_style_analysis(analysis_id, int(latest["revision"]))
        with self.database.transaction() as connection:
            latest_revision = connection.execute(
                "SELECT MAX(revision) FROM style_analysis_revisions WHERE analysis_id = ?", (analysis_id,)
            ).fetchone()[0]
            revision = 1 if latest_revision is None else int(latest_revision) + 1
            now = _utc_now()
            record = {
                "analysis_id": analysis_id, "revision": revision, "profile_id": profile_id,
                "profile_version": int(profile["version"]), "status": "candidate", "analysis": report,
                "reviewer": None, "reviewed_at": None, "review_note": None, "created_at": now,
            }
            connection.execute(
                """INSERT INTO style_analysis_revisions(
                       analysis_id, revision, profile_id, profile_version, status, analysis_json,
                       reviewer, reviewed_at, review_note, created_at, record_json
                   ) VALUES (?, ?, ?, ?, 'candidate', ?, NULL, NULL, NULL, ?, ?)""",
                (analysis_id, revision, profile_id, int(profile["version"]), report_json, now, _json(record)),
            )
            for source_asset_id, source_asset_version in selected_sources:
                connection.execute(
                    """INSERT INTO style_analysis_sources(
                           analysis_id, analysis_revision, asset_id, asset_version, source_role
                       ) VALUES (?, ?, ?, ?, 'visual_reference')""",
                    (analysis_id, revision, source_asset_id, source_asset_version),
                )
        return self.get_style_analysis(analysis_id, revision)

    def list_style_analyses(
        self, *, profile_id: str | None = None, status: str | None = None, include_history: bool = False
    ) -> tuple[StyleAnalysis, ...]:
        clauses: list[str] = []
        values: list[object] = []
        if not include_history:
            clauses.append("(a.analysis_id, a.revision) IN (SELECT analysis_id, MAX(revision) FROM style_analysis_revisions GROUP BY analysis_id)")
        if profile_id is not None:
            clauses.append("a.profile_id = ?")
            values.append(profile_id)
        if status is not None:
            clauses.append("a.status = ?")
            values.append(status)
        query = "SELECT a.* FROM style_analysis_revisions a"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY a.profile_id, a.analysis_id, a.revision"
        with self.database.connection() as connection:
            rows = connection.execute(query, values).fetchall()
        return tuple(self._style_analysis_from_row(row) for row in rows)

    def get_style_analysis(self, analysis_id: str, revision: int | None = None) -> StyleAnalysis:
        with self.database.connection() as connection:
            if revision is None:
                row = connection.execute(
                    "SELECT * FROM style_analysis_revisions WHERE analysis_id = ? ORDER BY revision DESC LIMIT 1",
                    (analysis_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM style_analysis_revisions WHERE analysis_id = ? AND revision = ?",
                    (analysis_id, revision),
                ).fetchone()
            if row is None:
                raise LibraryLookupError(f"unknown style analysis: {analysis_id!r}")
            sources = connection.execute(
                """SELECT asset_id, asset_version FROM style_analysis_sources
                   WHERE analysis_id = ? AND analysis_revision = ? ORDER BY asset_id, asset_version""",
                (analysis_id, int(row["revision"])),
            ).fetchall()
        return self._style_analysis_from_row(row, tuple((str(item["asset_id"]), int(item["asset_version"])) for item in sources))

    def review_style_analysis(
        self, analysis_id: str, *, reviewer: str, decision: str, note: str | None = None
    ) -> StyleAnalysis:
        current = self.get_style_analysis(analysis_id)
        if decision not in {"verified", "rejected"}:
            raise ValueError("review decision must be 'verified' or 'rejected'")
        reviewer = _nonempty(reviewer, "reviewer")
        for asset_id, asset_version in current.source_assets:
            self._read_verified_document(asset_id, asset_version)
        with self.database.transaction() as connection:
            latest = connection.execute(
                "SELECT MAX(revision) FROM style_analysis_revisions WHERE analysis_id = ?", (analysis_id,)
            ).fetchone()[0]
            if latest != current.revision:
                raise ValueError(
                    f"style analysis {analysis_id!r} changed while being reviewed; reload it before deciding"
                )
            revision = int(latest) + 1
            now = _utc_now()
            record = {
                "analysis_id": current.analysis_id, "revision": revision, "profile_id": current.profile_id,
                "profile_version": current.profile_version, "status": decision, "analysis": dict(current.analysis),
                "reviewer": reviewer, "reviewed_at": now, "review_note": note, "created_at": now,
            }
            connection.execute(
                """INSERT INTO style_analysis_revisions(
                       analysis_id, revision, profile_id, profile_version, status, analysis_json,
                       reviewer, reviewed_at, review_note, created_at, record_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    analysis_id, revision, current.profile_id, current.profile_version, decision,
                    _json(dict(current.analysis)), reviewer, now, note, now, _json(record),
                ),
            )
            for asset_id, asset_version in current.source_assets:
                connection.execute(
                    """INSERT INTO style_analysis_sources(
                           analysis_id, analysis_revision, asset_id, asset_version, source_role
                       ) VALUES (?, ?, ?, ?, 'visual_reference')""",
                    (analysis_id, revision, asset_id, asset_version),
                )
        return self.get_style_analysis(analysis_id, revision)

    def export_style_analysis(self, analysis_id: str, destination: str | Path) -> Path:
        from .reports import export_json_no_overwrite, style_analysis_document

        report = self.get_style_analysis(analysis_id)
        path = Path(destination)
        if not path.is_absolute():
            path = self.project_root / path
        try:
            return export_json_no_overwrite(style_analysis_document(report), path)
        except FileExistsError:
            raise
        except OSError as exc:
            raise AssetIntegrityError(f"could not export style analysis to {path}: {exc}") from exc

    def _style_analysis_from_row(
        self, row: sqlite3.Row, sources: tuple[tuple[str, int], ...] | None = None
    ) -> StyleAnalysis:
        if sources is None:
            with self.database.connection() as connection:
                rows = connection.execute(
                    """SELECT asset_id, asset_version FROM style_analysis_sources
                       WHERE analysis_id = ? AND analysis_revision = ? ORDER BY asset_id, asset_version""",
                    (row["analysis_id"], row["revision"]),
                ).fetchall()
            sources = tuple((str(item["asset_id"]), int(item["asset_version"])) for item in rows)
        return StyleAnalysis(
            analysis_id=str(row["analysis_id"]),
            revision=int(row["revision"]),
            profile_id=str(row["profile_id"]),
            profile_version=int(row["profile_version"]),
            status=str(row["status"]),
            source_assets=sources,
            analysis=_loads(row["analysis_json"]),
            reviewer=row["reviewer"],
            reviewed_at=row["reviewed_at"],
            review_note=row["review_note"],
            created_at=str(row["created_at"]),
        )

    def _append_annotation(
        self,
        *,
        annotation_id: str,
        asset_id: str,
        asset_version: int,
        region_name: str,
        component_type: str,
        geometry_type: str,
        geometry: Mapping[str, object],
        source_kind: str,
        rule_id: str | None,
        confidence: float | None,
        status: str,
        reviewer: str | None,
        reviewed_at: str | None,
        review_note: str | None,
        explanation: str | None = None,
        expected_revision: int | None = None,
    ) -> SemanticAnnotation:
        if status == "verified" and (not reviewer or not reviewed_at):
            raise ValueError("verified annotations require a human reviewer and review time")
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT MAX(revision) FROM semantic_annotation_revisions WHERE annotation_id = ?", (annotation_id,)
            ).fetchone()
            latest_revision = 0 if row[0] is None else int(row[0])
            if expected_revision is not None and latest_revision != expected_revision:
                raise ValueError(
                    f"annotation {annotation_id!r} changed from revision {expected_revision} to {latest_revision}; reload before editing"
                )
            revision = latest_revision + 1
            created_at = _utc_now()
            record = {
                "annotation_id": annotation_id, "revision": revision, "asset_id": asset_id,
                "asset_version": asset_version, "region_name": region_name, "component_type": component_type,
                "geometry_type": geometry_type, "geometry": dict(geometry), "source_kind": source_kind,
                "rule_id": rule_id, "confidence": confidence, "status": status, "reviewer": reviewer,
                "reviewed_at": reviewed_at, "review_note": review_note, "created_at": created_at,
            }
            if explanation is not None:
                record["rule_explanation"] = explanation
            connection.execute(
                """INSERT INTO semantic_annotation_revisions(
                       annotation_id, revision, asset_id, asset_version, region_name, component_type,
                       geometry_type, geometry_json, source_kind, rule_id, confidence, status,
                       reviewer, reviewed_at, review_note, created_at, record_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    annotation_id, revision, asset_id, asset_version, region_name, component_type,
                    geometry_type, _json(dict(geometry)), source_kind, rule_id, confidence, status,
                    reviewer, reviewed_at, review_note, created_at, _json(record),
                ),
            )
            saved = connection.execute(
                "SELECT * FROM semantic_annotation_revisions WHERE annotation_id = ? AND revision = ?",
                (annotation_id, revision),
            ).fetchone()
        return _annotation_from_row(saved)

    def _asset_file_row_for_reference(self, asset_id: str, version: int | None) -> dict[str, object]:
        with self.database.connection() as connection:
            asset = self._asset_file_row(connection, asset_id, version)
            file_row = connection.execute(
                "SELECT sha256 FROM reference_files WHERE file_id = ?", (asset["file_id"],)
            ).fetchone()
        if file_row is None:
            raise LibraryLookupError(f"reference asset has no source file record: {asset_id!r}")
        return {"version": asset["version"], "source_file": asset["source_file"], "sha256": file_row["sha256"]}

    def _read_verified_document(self, asset_id: str, version: int) -> tuple[LitematicDocument, Path]:
        asset = self._asset_file_row_for_reference(asset_id, version)
        path = self._resolve_source_path(str(asset["source_file"]))
        if not path.is_file():
            raise AssetIntegrityError(f"reference source file is missing: {path}")
        expected = str(asset["sha256"])
        before, byte_count = _sha256(path)
        if before != expected:
            raise AssetIntegrityError(f"SHA-256 mismatch for {asset_id}@{version}: expected {expected}, got {before}")
        try:
            document = read_litematic(path)
        except ValueError as exc:
            raise AssetIntegrityError(f"could not parse reference source {asset_id}@{version}: {exc}") from exc
        after, after_size = _sha256(path)
        if after != before or after_size != byte_count:
            raise AssetIntegrityError(f"reference source changed while being analyzed: {path}")
        return document, path

    def material_counts(self, asset_id: str, version: int | None = None) -> dict[str, int]:
        with self.database.connection() as connection:
            row = self._asset_file_row(connection, asset_id, version)
            counts = connection.execute(
                "SELECT block_state, block_count FROM reference_material_counts WHERE file_id = ? ORDER BY block_state",
                (row["file_id"],),
            ).fetchall()
            return {str(item["block_state"]): int(item["block_count"]) for item in counts}

    def material_totals(self, asset_id: str, version: int | None = None) -> dict[str, int]:
        """Aggregate state variants (for example stair directions) by block ID."""

        state_counts = self.material_counts(asset_id, version)
        totals: dict[str, int] = {}
        for block_state, count in state_counts.items():
            block_id = block_state.partition("[")[0]
            totals[block_id] = totals.get(block_id, 0) + count
        return dict(sorted(totals.items()))

    def layer_material_counts(self, asset_id: str, version: int | None = None) -> dict[int, dict[str, int]]:
        with self.database.connection() as connection:
            row = self._asset_file_row(connection, asset_id, version)
            counts = connection.execute(
                """SELECT y, block_state, block_count FROM reference_layer_counts
                   WHERE file_id = ? ORDER BY y, block_state""",
                (row["file_id"],),
            ).fetchall()
            result: dict[int, dict[str, int]] = {}
            for item in counts:
                result.setdefault(int(item["y"]), {})[str(item["block_state"])] = int(item["block_count"])
            return result

    def register_preview_files(
        self, asset_id: str, files: Sequence[str | Path], version: int | None = None
    ) -> ReferenceAsset:
        if not files:
            raise ValueError("at least one preview file is required")
        normalized: list[str] = []
        for value in files:
            path = Path(value).resolve()
            if not path.is_file():
                raise AssetIntegrityError(f"preview file does not exist: {path}")
            normalized.append(self._stored_source_path(path))
        if len(normalized) != len(set(normalized)):
            raise ValueError("preview file paths must be unique")
        with self.database.transaction() as connection:
            row = self._asset_file_row(connection, asset_id, version)
            existing = _loads(row["preview_files_json"])
            combined = list(dict.fromkeys([*existing, *normalized]))
            connection.execute(
                "UPDATE reference_assets SET preview_files_json = ? WHERE asset_id = ? AND version = ?",
                (_json(combined), asset_id, row["version"]),
            )
            return self._reference_by_version(connection, asset_id, int(row["version"]))

    def list_regions(self, *, active_only: bool = False) -> tuple[dict[str, Any], ...]:
        current_version = self._current_knowledge_version()
        query = "SELECT * FROM region_profiles WHERE registry_version = ?"
        parameters: tuple[object, ...] = (current_version,)
        if active_only:
            query += " AND status = 'active'"
        query += " ORDER BY region_id"
        with self.database.connection() as connection:
            return tuple(
                {
                    "region_id": row["region_id"],
                    "registry_version": int(row["registry_version"]),
                    "label": row["label"],
                    "status": row["status"],
                    "scope": row["scope"],
                    "notes": row["notes"],
                    "source_ids": _loads(row["record_json"]).get("source_ids", []),
                }
                for row in connection.execute(query, parameters).fetchall()
            )

    def list_sources(self) -> tuple[dict[str, Any], ...]:
        current_version = self._current_knowledge_version()
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT record_json FROM knowledge_sources WHERE registry_version = ? ORDER BY source_id",
                (current_version,),
            ).fetchall()
            return tuple(_loads(row["record_json"]) for row in rows)

    def list_modules(self, *, include_planned: bool = False) -> tuple[dict[str, Any], ...]:
        query = "SELECT * FROM module_assets"
        if not include_planned:
            query += " WHERE status = 'implemented'"
        query += " ORDER BY kind"
        with self.database.connection() as connection:
            rows = connection.execute(query).fetchall()
            return tuple(self._module_record(connection, row) for row in rows)

    def get_module_definition(self, asset_id: str, version: int | None = None) -> dict[str, Any]:
        with self.database.connection() as connection:
            if version is None:
                row = connection.execute(
                    "SELECT * FROM module_assets WHERE asset_id = ? ORDER BY version DESC LIMIT 1", (asset_id,)
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM module_assets WHERE asset_id = ? AND version = ?", (asset_id, version)
                ).fetchone()
            if row is None:
                raise LibraryLookupError(f"unknown module definition: {asset_id!r}")
            return self._module_record(connection, row)

    def list_parameter_schemas(self) -> tuple[dict[str, Any], ...]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT schema_id, version, asset_id, kind, definition_path FROM parameter_schemas ORDER BY schema_id, version"
            ).fetchall()
            keys = ("schema_id", "version", "asset_id", "kind", "definition_path")
            return tuple({key: row[key] for key in keys} for row in rows)

    def get_parameter_schema(self, schema_id: str, version: int | None = None) -> dict[str, Any]:
        with self.database.connection() as connection:
            if version is None:
                row = connection.execute(
                    "SELECT * FROM parameter_schemas WHERE schema_id = ? ORDER BY version DESC LIMIT 1",
                    (schema_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM parameter_schemas WHERE schema_id = ? AND version = ?",
                    (schema_id, version),
                ).fetchone()
            if row is None:
                raise LibraryLookupError(f"unknown parameter schema: {schema_id!r}")
            return {
                "schema_id": row["schema_id"],
                "version": int(row["version"]),
                "asset_id": row["asset_id"],
                "kind": row["kind"],
                "definition_path": row["definition_path"],
                **_loads(row["schema_json"]),
            }

    def _module_record(self, connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        result: dict[str, Any] = {
            "asset_id": row["asset_id"],
            "asset_version": int(row["version"]),
            "kind": row["kind"],
            "status": row["status"],
            "generator_source_id": row["generator_source_id"],
            "parameter_schema_id": row["parameter_schema_id"],
            "parameter_schema_version": row["parameter_schema_version"],
            "definition_path": row["definition_path"],
            "region_association_kind": row["region_association_kind"],
            "anchor_interfaces": _loads(row["anchor_interfaces_json"]),
            "dependencies": _loads(row["dependencies_json"]),
            "preview_files": _loads(row["preview_files_json"]),
            "regions": [
                item["region_id"]
                for item in connection.execute(
                    """SELECT region_id FROM module_asset_regions
                       WHERE asset_id = ? AND asset_version = ? ORDER BY region_id""",
                    (row["asset_id"], row["version"]),
                ).fetchall()
            ],
            "knowledge_rule_ids": [
                item["rule_id"]
                for item in connection.execute(
                    """SELECT rule_id FROM module_knowledge_rules
                       WHERE asset_id = ? AND asset_version = ? ORDER BY rule_id""",
                    (row["asset_id"], row["version"]),
                ).fetchall()
            ],
            "record": _loads(row["record_json"]),
        }
        if row["parameter_schema_id"] is not None:
            schema = connection.execute(
                "SELECT schema_json FROM parameter_schemas WHERE schema_id = ? AND version = ?",
                (row["parameter_schema_id"], row["parameter_schema_version"]),
            ).fetchone()
            if schema is None:
                raise LibraryLookupError(
                    f"module {row['asset_id']!r} references a missing parameter schema"
                )
            result["parameter_schema"] = _loads(schema["schema_json"])
        return result

    def list_knowledge_rules(
        self,
        *,
        region: str | None = None,
        building_type: str | None = None,
        evidence_kind: str | None = None,
        include_pending: bool = False,
    ) -> dict[str, Any]:
        with self.database.connection() as connection:
            registry_version = int(
                connection.execute("SELECT MAX(version) FROM knowledge_registry_versions").fetchone()[0]
            )
            if region is not None:
                profile = connection.execute(
                    "SELECT status FROM region_profiles WHERE region_id = ? AND registry_version = ?",
                    (region, registry_version),
                ).fetchone()
                if profile is None:
                    raise LibraryLookupError(f"unknown region profile: {region!r}")
                if profile["status"] == "catalog_only":
                    return {"knowledge_base_version": registry_version, "region": region, "rules": []}
            where: list[str] = ["kr.registry_version = ?"]
            parameters: list[object] = [registry_version]
            if not include_pending:
                where.append("kr.status = 'active'")
            if evidence_kind is not None:
                where.append("kr.evidence_kind = ?")
                parameters.append(evidence_kind)
            if building_type is not None:
                where.append("EXISTS (SELECT 1 FROM json_each(kr.building_types_json) b WHERE b.value = ? OR b.value = 'any')")
                parameters.append(building_type)
            if region is not None:
                where.append("EXISTS (SELECT 1 FROM knowledge_rule_regions rr WHERE rr.rule_id = kr.rule_id AND rr.region_id = ?)")
                parameters.append(region)
            query = """SELECT kr.*, ks.record_json AS source_json
                       FROM knowledge_rules kr JOIN knowledge_sources ks USING(source_id)"""
            if where:
                query += " WHERE " + " AND ".join(where)
            query += " ORDER BY kr.rule_id"
            rows = connection.execute(query, tuple(parameters)).fetchall()
            return {
                "knowledge_base_version": registry_version,
                "region": region,
                "rules": [
                    _loads(row["record_json"]) | {"source": _loads(row["source_json"])}
                    for row in rows
                ],
            }

    def list_styles(self) -> tuple[dict[str, Any], ...]:
        with self.database.connection() as connection:
            rows = connection.execute("SELECT * FROM style_profiles ORDER BY profile_id, version").fetchall()
            results = []
            for row in rows:
                profile = _loads(row["profile_json"])
                references = profile.get("reference_asset_ids", [])
                resolved = connection.execute(
                    """SELECT asset_id, asset_version FROM style_reference_assets
                       WHERE profile_id = ? AND profile_version = ? ORDER BY asset_id""",
                    (row["profile_id"], row["version"]),
                ).fetchall()
                resolved_versions = {item["asset_id"]: int(item["asset_version"]) for item in resolved}
                missing = sorted(set(references) - set(resolved_versions))
                results.append(
                    {
                        "profile_id": row["profile_id"],
                        "version": int(row["version"]),
                        "label": row["label"],
                        "region_profile_id": row["region_profile_id"],
                        "status": row["status"],
                        "reference_asset_ids": references,
                        "resolved_reference_versions": resolved_versions,
                        "missing_reference_asset_ids": missing,
                        "reference_status": "ready" if not missing else "missing_references",
                    }
                )
            return tuple(results)

    def get_style_profile(
        self, profile_id: str, version: int | None = None, *, require_references: bool = False
    ) -> dict[str, Any]:
        with self.database.connection() as connection:
            if version is None:
                row = connection.execute(
                    "SELECT * FROM style_profiles WHERE profile_id = ? ORDER BY version DESC LIMIT 1", (profile_id,)
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM style_profiles WHERE profile_id = ? AND version = ?", (profile_id, version)
                ).fetchone()
            if row is None:
                raise LibraryLookupError(f"unknown style profile: {profile_id!r}")
            profile = _loads(row["profile_json"])
            refs: dict[str, ReferenceAsset] = {}
            for asset_id in profile.get("reference_asset_ids", []):
                ref = connection.execute(
                    """SELECT ra.*, rf.file_format, rf.sha256, rf.minecraft_data_version
                       FROM style_reference_assets link
                       JOIN reference_assets ra ON ra.asset_id = link.asset_id AND ra.version = link.asset_version
                       JOIN reference_files rf ON rf.file_id = ra.file_id
                       WHERE link.profile_id = ? AND link.profile_version = ? AND link.asset_id = ?""",
                    (row["profile_id"], row["version"], asset_id),
                ).fetchone()
                if ref is not None:
                    refs[asset_id] = _asset_from_row(ref)
            missing = sorted(set(profile.get("reference_asset_ids", [])) - set(refs))
            missing_versions = {
                asset_id: int(profile["reference_asset_versions"][asset_id])
                for asset_id in missing
                if asset_id in profile.get("reference_asset_versions", {})
            }
            if require_references and missing:
                missing_labels = [
                    f"{asset_id}@{missing_versions[asset_id]}" if asset_id in missing_versions else asset_id
                    for asset_id in missing
                ]
                raise LibraryLookupError(
                    f"style profile {profile_id!r} reference asset(s) not imported: {', '.join(missing_labels)}"
                )
            palette_limit = int(profile.get("palette_selection", {}).get("top_material_count", 12))
            candidates: dict[str, list[dict[str, object]]] = {}
            for asset_id, asset in refs.items():
                file_row = self._asset_file_row(connection, asset_id, asset.version)
                counts = connection.execute(
                    """SELECT block_state, block_count FROM reference_material_counts
                       WHERE file_id = ? ORDER BY block_count DESC, block_state LIMIT ?""",
                    (file_row["file_id"], palette_limit),
                ).fetchall()
                candidates[asset_id] = [
                    {"block_state": item["block_state"], "count": int(item["block_count"])} for item in counts
                ]
            return {
                **profile,
                "definition_path": row["definition_path"],
                "reference_status": "ready" if not missing else "missing_references",
                "missing_reference_asset_ids": missing,
                "missing_reference_asset_versions": missing_versions,
                "resolved_reference_versions": {asset_id: asset.version for asset_id, asset in refs.items()},
                "palette_candidates": candidates,
            }

    def verify_files(self, asset_id: str | None = None) -> tuple[dict[str, str], ...]:
        with self.database.connection() as connection:
            if asset_id is None:
                rows = connection.execute("SELECT * FROM reference_assets ORDER BY asset_id, version").fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM reference_assets WHERE asset_id = ? ORDER BY version", (asset_id,)
                ).fetchall()
            if asset_id is not None and not rows:
                raise LibraryLookupError(f"unknown reference asset: {asset_id!r}")
            results: list[dict[str, str]] = []
            for row in rows:
                path = self._resolve_source_path(str(row["source_file"]))
                if not path.is_file():
                    raise AssetIntegrityError(f"reference file is missing for {row['asset_id']}@{row['version']}: {path}")
                actual, _ = _sha256(path)
                file_row = connection.execute(
                    "SELECT sha256 FROM reference_files WHERE file_id = ?", (row["file_id"],)
                ).fetchone()
                expected = str(file_row["sha256"])
                if actual != expected:
                    raise AssetIntegrityError(
                        f"SHA-256 mismatch for {row['asset_id']}@{row['version']}: expected {expected}, got {actual}"
                    )
                for preview in _loads(row["preview_files_json"]):
                    preview_path = self._resolve_source_path(str(preview))
                    if not preview_path.is_file():
                        raise AssetIntegrityError(
                            f"preview file is missing for {row['asset_id']}@{row['version']}: {preview_path}"
                        )
                results.append(
                    {"asset_id": row["asset_id"], "version": str(row["version"]), "status": "ok", "sha256": actual}
                )
            return tuple(results)

    def backup_to(self, destination: str | Path) -> Path:
        return self.database.backup_to(destination)

    def reference_count(self) -> int:
        with self.database.connection() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM reference_assets").fetchone()[0])

    def file_count(self) -> int:
        with self.database.connection() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM reference_files").fetchone()[0])

    def _sync_style_reference_links(
        self, connection: sqlite3.Connection, asset_id: str, asset_version: int
    ) -> None:
        styles = connection.execute("SELECT profile_id, version, profile_json FROM style_profiles").fetchall()
        for style in styles:
            profile = _loads(style["profile_json"])
            if asset_id not in profile.get("reference_asset_ids", []):
                continue
            pinned_version = profile.get("reference_asset_versions", {}).get(asset_id)
            existing_link = connection.execute(
                """SELECT asset_version FROM style_reference_assets
                   WHERE profile_id = ? AND profile_version = ? AND asset_id = ?""",
                (style["profile_id"], style["version"], asset_id),
            ).fetchone()
            if existing_link is not None and (
                pinned_version is None or int(existing_link["asset_version"]) == int(pinned_version)
            ):
                continue
            if pinned_version is not None and int(pinned_version) != asset_version:
                if existing_link is not None:
                    connection.execute(
                        """DELETE FROM style_reference_assets
                           WHERE profile_id = ? AND profile_version = ? AND asset_id = ?""",
                        (style["profile_id"], style["version"], asset_id),
                    )
                continue
            connection.execute(
                """INSERT INTO style_reference_assets(
                       profile_id, profile_version, asset_id, asset_version, reference_role
                   ) VALUES (?, ?, ?, ?, 'visual_reference')""",
                (style["profile_id"], style["version"], asset_id, asset_version),
            )

    def _current_knowledge_version(self) -> int:
        with self.database.connection() as connection:
            row = connection.execute("SELECT MAX(version) FROM knowledge_registry_versions").fetchone()
            if row is None or row[0] is None:
                raise ValueError("knowledge registry has not been seeded")
            return int(row[0])

    def _reference_by_version(self, connection: sqlite3.Connection, asset_id: str, version: int) -> ReferenceAsset:
        row = connection.execute(
            """SELECT ra.*, rf.file_format, rf.sha256, rf.minecraft_data_version
               FROM reference_assets ra JOIN reference_files rf USING(file_id)
               WHERE ra.asset_id = ? AND ra.version = ?""",
            (asset_id, version),
        ).fetchone()
        if row is None:
            raise LibraryLookupError(f"unknown reference asset: {asset_id!r}@{version}")
        return _asset_from_row(row)

    def _asset_file_row(self, connection: sqlite3.Connection, asset_id: str, version: int | None) -> sqlite3.Row:
        if version is None:
            row = connection.execute(
                "SELECT * FROM reference_assets WHERE asset_id = ? ORDER BY version DESC LIMIT 1", (asset_id,)
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT * FROM reference_assets WHERE asset_id = ? AND version = ?", (asset_id, version)
            ).fetchone()
        if row is None:
            raise LibraryLookupError(f"unknown reference asset: {asset_id!r}")
        return row

    def _require_active_region(self, region_id: str) -> None:
        with self.database.connection() as connection:
            row = connection.execute("SELECT status FROM region_profiles WHERE region_id = ?", (region_id,)).fetchone()
            if row is None or row["status"] != "active":
                raise LibraryLookupError(f"reference region must be an active profile: {region_id!r}")

    def _stored_source_path(self, path: Path) -> str:
        try:
            return path.relative_to(self.project_root).as_posix()
        except ValueError:
            return str(path)

    def _resolve_source_path(self, value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else self.project_root / path


def _asset_from_row(row: sqlite3.Row) -> ReferenceAsset:
    return ReferenceAsset(
        asset_id=str(row["asset_id"]),
        version=int(row["version"]),
        name=str(row["name"]),
        source_file=str(row["source_file"]),
        file_format=str(row["file_format"]),
        minecraft_data_version=int(row["minecraft_data_version"]),
        region_profile_id=row["region_profile_id"],
        region_assignment_status=str(row["region_assignment_status"]),
        building_type=str(row["building_type"]),
        dimensions=tuple(_loads(row["dimensions_json"])),  # type: ignore[arg-type]
        block_count=int(row["block_count"]),
        block_palette=_loads(row["block_palette_json"]),
        bounding_box=(tuple(_loads(row["bounding_box_json"])[0]), tuple(_loads(row["bounding_box_json"])[1])),  # type: ignore[arg-type]
        preview_files=tuple(_loads(row["preview_files_json"])),
        sha256=str(row["sha256"]),
        import_status=str(row["import_status"]),
        validation_status=str(row["validation_status"]),
        author=str(row["author"]),
        provenance=_loads(row["provenance_json"]),
        usage_rights=_loads(row["usage_rights_json"]),
        created_at=str(row["created_at"]),
        parser_version=str(row["parser_version"]),
    )


def _annotation_from_row(row: sqlite3.Row) -> SemanticAnnotation:
    return SemanticAnnotation(
        annotation_id=str(row["annotation_id"]),
        revision=int(row["revision"]),
        asset_id=str(row["asset_id"]),
        asset_version=int(row["asset_version"]),
        region_name=str(row["region_name"]),
        component_type=str(row["component_type"]),
        geometry_type=str(row["geometry_type"]),
        geometry=_loads(row["geometry_json"]),
        source_kind=str(row["source_kind"]),
        rule_id=row["rule_id"],
        confidence=row["confidence"],
        status=str(row["status"]),
        reviewer=row["reviewer"],
        reviewed_at=row["reviewed_at"],
        review_note=row["review_note"],
        created_at=str(row["created_at"]),
    )


def _component_from_row(row: sqlite3.Row) -> ReferenceComponent:
    bounds = _loads(row["bounding_box_json"])
    return ReferenceComponent(
        component_id=str(row["component_id"]),
        version=int(row["version"]),
        source_asset_id=str(row["source_asset_id"]),
        source_asset_version=int(row["source_asset_version"]),
        annotation_id=str(row["annotation_id"]),
        annotation_revision=int(row["annotation_revision"]),
        name=str(row["name"]),
        component_type=str(row["component_type"]),
        region_name=str(row["region_name"]),
        local_origin=tuple(_loads(row["origin_json"])),  # type: ignore[arg-type]
        dimensions=tuple(_loads(row["dimensions_json"])),  # type: ignore[arg-type]
        bounding_box=(tuple(bounds[0]), tuple(bounds[1])),  # type: ignore[arg-type]
        block_count=int(row["block_count"]),
        block_states=_loads(row["block_states_json"]),
        materials=_loads(row["materials_json"]),
        layer_materials={int(key): value for key, value in _loads(row["layer_materials_json"]).items()},
        coordinate_runs=tuple(tuple(run) for run in _loads(row["coordinate_runs_json"])),  # type: ignore[arg-type]
        style_tags=tuple(_loads(row["style_tags_json"])),
        component_status=str(row["component_status"]),
        parameterization_status=str(row["parameterization_status"]),
        created_at=str(row["created_at"]),
    )


def _component_record(
    *,
    component_id: str,
    version: int,
    annotation: SemanticAnnotation,
    summary: ComponentSummary,
    name: str,
    style_tags: Sequence[str],
    parameterization_status: str,
    created_at: str,
) -> dict[str, Any]:
    return {
        "component_id": component_id,
        "version": version,
        "source_asset_id": annotation.asset_id,
        "source_asset_version": annotation.asset_version,
        "annotation_id": annotation.annotation_id,
        "annotation_revision": annotation.revision,
        "name": name,
        "component_type": summary.component_type,
        "region_name": summary.region_name,
        "local_origin": list(summary.local_origin),
        "dimensions": list(summary.dimensions),
        "bounding_box": [list(summary.bounding_box[0]), list(summary.bounding_box[1])],
        "block_count": summary.block_count,
        "block_states": dict(summary.block_states),
        "materials": dict(summary.materials),
        "layer_materials": {str(key): dict(value) for key, value in summary.layer_materials.items()},
        "coordinate_runs": [list(run) for run in summary.coordinate_runs],
        "style_tags": list(style_tags),
        "component_status": "static_reference",
        "parameterization_status": parameterization_status,
        "created_at": created_at,
        "source_annotation_status": annotation.status,
        "reviewer": annotation.reviewer,
        "reviewed_at": annotation.reviewed_at,
        "review_note": annotation.review_note,
    }


def _summary_record(summary: ComponentSummary) -> dict[str, Any]:
    return {
        "region_name": summary.region_name,
        "component_type": summary.component_type,
        "local_origin": list(summary.local_origin),
        "dimensions": list(summary.dimensions),
        "bounding_box": [list(summary.bounding_box[0]), list(summary.bounding_box[1])],
        "block_count": summary.block_count,
        "block_states": dict(summary.block_states),
        "materials": dict(summary.materials),
        "layer_materials": {str(key): dict(value) for key, value in summary.layer_materials.items()},
        "coordinate_runs": [list(run) for run in summary.coordinate_runs],
    }


def _find_region(regions: Sequence[LitematicRegion], region_name: str) -> LitematicRegion:
    for region in regions:
        if region.name == region_name:
            return region
    raise LibraryLookupError(f"unknown Litematic region: {region_name!r}")


def _read_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"JSON record must be an object: {path}")
    return raw


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _loads(value: str) -> Any:
    return json.loads(value)


def _validation_status(compatibility_status: str) -> str:
    statuses = {
        "target": "parsed_target_data_version",
        "older_than_target": "parsed_older_data_version_requires_review",
        "newer_than_target": "parsed_newer_data_version_incompatible_with_target",
    }
    try:
        return statuses[compatibility_status]
    except KeyError as exc:
        raise ValueError(f"unknown Litematic compatibility status: {compatibility_status!r}") from exc


def _nonempty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"{field} must be a list of non-empty strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{field} entries must be unique")
    return list(value)


def _relative_record_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(_PACKAGE_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def _sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_size = 0
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
                byte_size += len(chunk)
    except OSError as exc:
        raise AssetIntegrityError(f"could not read reference file {path}: {exc}") from exc
    return digest.hexdigest(), byte_size


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
