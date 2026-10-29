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
from .errors import AssetIntegrityError, LibraryLookupError
from .litematic import PARSER_VERSION, TARGET_MINECRAFT_DATA_VERSION, analyze_litematic, read_litematic
from .models import ReferenceAsset

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
        return version

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
        connection.execute(
            "DELETE FROM style_reference_assets WHERE profile_id = ? AND profile_version = ?",
            (profile_id, version),
        )
        for asset_id in references:
            pinned_version = reference_versions.get(asset_id)
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
        compatibility_to_validation = {
            "target": "parsed_target_data_version",
            "older_than_target": "parsed_older_data_version_requires_review",
            "newer_than_target": "parsed_newer_data_version_incompatible_with_target",
        }
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
                    compatibility_to_validation[analysis.compatibility_status],
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
            if pinned_version is not None and int(pinned_version) != asset_version:
                continue
            connection.execute(
                """DELETE FROM style_reference_assets
                   WHERE profile_id = ? AND profile_version = ? AND asset_id = ?""",
                (style["profile_id"], style["version"], asset_id),
            )
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


def _read_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"JSON record must be an object: {path}")
    return raw


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _loads(value: str) -> Any:
    return json.loads(value)


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
