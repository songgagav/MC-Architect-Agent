"""Validated parameter schemas and deterministic generator adapters."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any

from ..assets.registry import get_asset
from ..generators.hall import CorridorParameters, HallParameters
from ..generators.roof_profiles import (
    EaveProfile,
    MaterialPalette,
    RidgeProfile,
    RoofPreset,
    RoofProfile,
    eave_profile_from_mapping as _eave_profile_from_mapping,
    material_palette_from_mapping as _material_palette_from_mapping,
    ridge_profile_from_mapping as _ridge_profile_from_mapping,
    roof_profile_from_mapping as _roof_profile_from_mapping,
)
from ..knowledge import ConfidenceLevel, EvidenceKind, KnowledgeBase, load_knowledge_base


class ParameterConflictError(ValueError):
    """Raised when supplied values disagree or contradict derived geometry."""


class ProvenanceCategory(StrEnum):
    USER_INPUT = "user_input"
    LITERATURE_REFERENCE = "literature_reference"
    SURVEY_DATA = "survey_data"
    DERIVED = "derived"
    MINECRAFT_ADAPTATION = "minecraft_adaptation"


_ROOF_PRESET_FILE = Path(__file__).parent / "v3" / "roof_profiles.json"


def list_roof_presets() -> tuple[str, ...]:
    """Return stable IDs of the versioned Minecraft roof-creation presets."""

    data = json.loads(_ROOF_PRESET_FILE.read_text(encoding="utf-8"))
    if data.get("version") != 3:
        raise ValueError("roof preset registry version mismatch")
    presets = data.get("presets")
    if not isinstance(presets, list):
        raise ValueError("roof preset registry must contain a presets array")
    ids = [item.get("preset_id") for item in presets if isinstance(item, Mapping)]
    if len(ids) != len(presets) or any(not isinstance(item, str) or not item for item in ids):
        raise ValueError("roof presets must have non-empty preset IDs")
    if len(ids) != len(set(ids)):
        raise ValueError("roof preset IDs must be unique")
    return tuple(sorted(ids))


def load_roof_preset(preset_id: str) -> RoofPreset:
    """Load and validate one versioned Minecraft roof-creation preset."""

    if not isinstance(preset_id, str) or not preset_id:
        raise ValueError("preset_id must be a non-empty string")
    data = json.loads(_ROOF_PRESET_FILE.read_text(encoding="utf-8"))
    if data.get("version") != 3:
        raise ValueError("roof preset registry version mismatch")
    matches = [item for item in data.get("presets", []) if item.get("preset_id") == preset_id]
    if not matches:
        raise ValueError(f"unknown roof preset: {preset_id!r}")
    item = matches[0]
    try:
        return RoofPreset(
            preset_id=preset_id,
            roof_profile=_roof_profile_from_mapping(item["roof_profile"]),
            eave_profile=_eave_profile_from_mapping(item["eave_profile"]),
            ridge_profile=_ridge_profile_from_mapping(item["ridge_profile"]),
            material_palette=_material_palette_from_mapping(item["material_palette"]),
        )
    except KeyError as exc:
        raise ValueError(f"roof preset {preset_id!r} is missing {exc.args[0]!r}") from exc


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def _nonempty(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class ParameterSchema:
    schema_id: str
    version: int
    asset_id: str
    kind: str
    defaults: Mapping[str, object]
    independent_fields: tuple[str, ...]
    derived_fields: Mapping[str, str]
    generator_fields: Mapping[str, str]
    adapter_fields: Mapping[str, str]
    legacy_aliases: Mapping[str, str]
    hard_constraints: tuple[Mapping[str, object], ...]
    soft_constraints: tuple[Mapping[str, object], ...]
    provenance_categories: tuple[str, ...] = tuple(item.value for item in ProvenanceCategory)
    field_provenance: Mapping[str, Mapping[str, object]] = field(default_factory=dict)
    derived_provenance: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("schema_id", "asset_id", "kind"):
            _nonempty(getattr(self, name), name)
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError("parameter schema version must be a positive integer")
        if not self.independent_fields or set(self.independent_fields) != set(self.defaults):
            raise ValueError("independent_fields must list every default parameter exactly once")
        if len(self.independent_fields) != len(set(self.independent_fields)):
            raise ValueError("independent_fields must be unique")
        for constraint in (*self.hard_constraints, *self.soft_constraints):
            if not isinstance(constraint, Mapping):
                raise ValueError("parameter constraints must be JSON objects")
        allowed_provenance_categories = {item.value for item in ProvenanceCategory}
        if set(self.provenance_categories) != allowed_provenance_categories:
            raise ValueError("provenance_categories must enumerate all supported parameter source categories")
        field_provenance = self.field_provenance
        if not field_provenance:
            field_provenance = {
                name: {
                    "default_category": ProvenanceCategory.MINECRAFT_ADAPTATION.value,
                    "accepted_categories": [
                        ProvenanceCategory.USER_INPUT.value,
                        ProvenanceCategory.MINECRAFT_ADAPTATION.value,
                    ],
                    "source_ids": [],
                    "note": "Legacy schema model constructed without provenance metadata.",
                }
                for name in self.independent_fields
            }
        if set(field_provenance) != set(self.independent_fields):
            raise ValueError("field_provenance must define every independent field exactly once")
        for name, policy in field_provenance.items():
            if not isinstance(policy, Mapping):
                raise ValueError(f"field provenance policy for {name!r} must be a JSON object")
            default_category = policy.get("default_category")
            accepted_categories = policy.get("accepted_categories")
            source_ids = policy.get("source_ids")
            if default_category not in allowed_provenance_categories:
                raise ValueError(f"field provenance policy for {name!r} has an unsupported default category")
            if not isinstance(accepted_categories, (list, tuple)) or not accepted_categories:
                raise ValueError(f"field provenance policy for {name!r} needs accepted_categories")
            if any(item not in allowed_provenance_categories for item in accepted_categories):
                raise ValueError(f"field provenance policy for {name!r} has an unsupported accepted category")
            if default_category not in accepted_categories:
                raise ValueError(f"field provenance policy for {name!r} must accept its default category")
            if not isinstance(source_ids, (list, tuple)) or any(not isinstance(item, str) or not item for item in source_ids):
                raise ValueError(f"field provenance policy for {name!r} must have valid source_ids")
        object.__setattr__(self, "defaults", _freeze(self.defaults))
        object.__setattr__(self, "derived_fields", _freeze(self.derived_fields))
        object.__setattr__(self, "generator_fields", _freeze(self.generator_fields))
        object.__setattr__(self, "adapter_fields", _freeze(self.adapter_fields))
        object.__setattr__(self, "legacy_aliases", _freeze(self.legacy_aliases))
        object.__setattr__(self, "hard_constraints", tuple(_freeze(item) for item in self.hard_constraints))
        object.__setattr__(self, "soft_constraints", tuple(_freeze(item) for item in self.soft_constraints))
        object.__setattr__(self, "provenance_categories", tuple(self.provenance_categories))
        object.__setattr__(self, "field_provenance", _freeze(field_provenance))
        object.__setattr__(self, "derived_provenance", _freeze(self.derived_provenance))


@dataclass(frozen=True)
class ParameterWarning:
    rule_id: str
    message: str
    evidence_kind: EvidenceKind
    confidence: ConfidenceLevel


@dataclass(frozen=True)
class ResolvedParameters:
    asset_id: str
    schema_version: int
    normalized_inputs: Mapping[str, object]
    derived_parameters: Mapping[str, object]
    generator_parameters: HallParameters | CorridorParameters
    adapter_options: Mapping[str, object]
    warnings: tuple[ParameterWarning, ...]
    parameter_provenance: Mapping[str, Mapping[str, object]] = field(default_factory=dict)
    derived_provenance: Mapping[str, Mapping[str, object]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameter_provenance", _freeze(self.parameter_provenance))
        object.__setattr__(self, "derived_provenance", _freeze(self.derived_provenance))


def load_parameter_schema(
    asset_id: str,
    version: int | None = None,
    *,
    asset_version: int | None = None,
) -> ParameterSchema:
    asset = get_asset(asset_id, asset_version)
    schema_version = asset.parameter_schema_version if version is None else version
    if isinstance(schema_version, bool) or not isinstance(schema_version, int) or schema_version < 1:
        raise ValueError("parameter schema version must be a positive integer")
    if schema_version != asset.parameter_schema_version:
        raise ValueError(f"unsupported parameter schema version {schema_version} for {asset_id!r}")
    path = Path(__file__).parent / f"v{schema_version}" / f"{asset.parameter_schema_id}.json"
    if not path.is_file():
        raise ValueError(f"unsupported parameter schema version {schema_version} for {asset_id!r}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if (
        data.get("version") != schema_version
        or data.get("asset_id") != asset_id
        or data.get("schema_id") != asset.parameter_schema_id
        or data.get("kind") != asset.kind
    ):
        raise ValueError(f"parameter schema asset/version/kind mismatch in {path}")
    knowledge = load_knowledge_base(asset.knowledge_base_version)
    provenance_categories = tuple(
        data.get("provenance_categories", [item.value for item in ProvenanceCategory])
    )
    legacy_field_provenance = {
        field_name: {
            "default_category": ProvenanceCategory.MINECRAFT_ADAPTATION.value,
            "accepted_categories": [
                ProvenanceCategory.USER_INPUT.value,
                ProvenanceCategory.MINECRAFT_ADAPTATION.value,
            ],
            "source_ids": [asset.source_id],
            "note": "Legacy schema default; not a historical measurement.",
        }
        for field_name in data["independent_fields"]
    }
    field_provenance = data.get("field_provenance", legacy_field_provenance)
    derived_provenance = data.get(
        "derived_provenance",
        {
            "category": ProvenanceCategory.DERIVED.value,
            "source_id": asset.source_id,
            "note": "Calculated deterministically by the legacy parameter resolver.",
        },
    )
    if not isinstance(field_provenance, Mapping):
        raise ValueError("field_provenance must be a JSON object")
    for field_name, policy in field_provenance.items():
        if not isinstance(policy, Mapping):
            raise ValueError(f"field provenance policy for {field_name!r} must be a JSON object")
        missing_sources = set(policy.get("source_ids", [])) - set(knowledge.sources)
        if missing_sources:
            raise ValueError(
                f"parameter provenance for {field_name!r} references unknown sources: "
                f"{', '.join(sorted(missing_sources))}"
            )
        if policy.get("default_category") == ProvenanceCategory.MINECRAFT_ADAPTATION.value:
            for source_id in policy.get("source_ids", []):
                if knowledge.sources[source_id].source_type != "project_code":
                    raise ValueError(
                        f"Minecraft adaptation default for {field_name!r} must cite project code"
                    )
    if not isinstance(derived_provenance, Mapping) or derived_provenance.get("category") != ProvenanceCategory.DERIVED.value:
        raise ValueError("derived_provenance must use the derived category")
    derived_source_id = derived_provenance.get("source_id")
    if not isinstance(derived_source_id, str) or derived_source_id not in knowledge.sources:
        raise ValueError("derived provenance must cite a registered knowledge source")
    return ParameterSchema(
        schema_id=data["schema_id"],
        version=data["version"],
        asset_id=data["asset_id"],
        kind=data["kind"],
        defaults=data["defaults"],
        independent_fields=tuple(data["independent_fields"]),
        derived_fields=data["derived_fields"],
        generator_fields=data["generator_fields"],
        adapter_fields=data["adapter_fields"],
        legacy_aliases=data["legacy_aliases"],
        hard_constraints=tuple(data["hard_constraints"]),
        soft_constraints=tuple(data["soft_constraints"]),
        provenance_categories=provenance_categories,
        field_provenance=field_provenance,
        derived_provenance=derived_provenance,
    )


def _top_level_parameter(schema: ParameterSchema, name: str) -> str:
    canonical_path = schema.legacy_aliases.get(name, name)
    if canonical_path == "derived" or not isinstance(canonical_path, str):
        raise ValueError(f"provenance must reference an independent parameter, got {name!r}")
    field_name = canonical_path.split(".", 1)[0]
    if field_name not in schema.independent_fields:
        raise ValueError(f"provenance references unknown parameter: {name!r}")
    return field_name


def _provided_top_level_parameters(schema: ParameterSchema, values: Mapping[str, object] | None) -> set[str]:
    if values is None:
        return set()
    if not isinstance(values, Mapping):
        raise ValueError("parameters must be a JSON object")
    result: set[str] = set()
    for name in values:
        if not isinstance(name, str):
            raise ValueError("parameter names must be strings")
        if name == "derived":
            continue
        if schema.version >= 3 and name == "materials" and isinstance(values[name], Mapping):
            material_values = values[name]
            if {"roof", "eaves"}.intersection(material_values):
                result.add("material_palette")
            if set(material_values) - {"roof", "eaves"}:
                result.add("materials")
            continue
        result.add(_top_level_parameter(schema, name))
    return result


def _provenance_record(
    schema: ParameterSchema,
    field_name: str,
    value: Mapping[str, object],
    *,
    knowledge: KnowledgeBase,
) -> dict[str, object]:
    category_value = value.get("category")
    try:
        category = ProvenanceCategory(category_value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(item.value for item in ProvenanceCategory)
        raise ValueError(f"unsupported provenance category; expected one of: {allowed}") from exc
    policy = schema.field_provenance[field_name]
    accepted = policy["accepted_categories"]
    if category.value not in accepted:
        raise ValueError(
            f"{category.value!r} is not an accepted provenance category for parameter {field_name!r}"
        )
    unexpected = set(value) - {"category", "source_id", "source_ids", "rule_id", "rule_ids"}
    if unexpected:
        raise ValueError(f"unknown provenance field: {sorted(unexpected)[0]}")
    raw_source_ids = value.get("source_ids", ())
    if not isinstance(raw_source_ids, (list, tuple)):
        raise ValueError("provenance source_ids must be a list of source IDs")
    source_ids = list(raw_source_ids)
    if "source_id" in value:
        source_id = value["source_id"]
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("provenance source_id must be a non-empty string")
        source_ids.append(source_id)
    if any(not isinstance(item, str) or not item for item in source_ids):
        raise ValueError("provenance source_ids must contain non-empty strings")
    source_ids = sorted(set(source_ids))
    raw_rule_ids = value.get("rule_ids", ())
    if not isinstance(raw_rule_ids, (list, tuple)):
        raise ValueError("provenance rule_ids must be a list of rule IDs")
    rule_ids = list(raw_rule_ids)
    if "rule_id" in value:
        rule_id = value["rule_id"]
        if not isinstance(rule_id, str) or not rule_id:
            raise ValueError("provenance rule_id must be a non-empty string")
        rule_ids.append(rule_id)
    if any(not isinstance(item, str) or not item for item in rule_ids):
        raise ValueError("provenance rule_ids must contain non-empty strings")
    rule_ids = sorted(set(rule_ids))

    if category is ProvenanceCategory.USER_INPUT:
        if source_ids or rule_ids:
            raise ValueError("user_input provenance must not claim a literature or survey source")
    elif category is ProvenanceCategory.MINECRAFT_ADAPTATION:
        if not source_ids:
            source_ids = list(policy["source_ids"])
        if not source_ids or rule_ids:
            raise ValueError("minecraft_adaptation provenance must cite registered generator source IDs")
        if not set(source_ids) <= set(policy["source_ids"]):
            raise ValueError(f"minecraft_adaptation uses a source not allowed for parameter {field_name!r}")
        for source_id in source_ids:
            source = knowledge.sources.get(source_id)
            if source is None or source.source_type != "project_code":
                raise ValueError(f"minecraft_adaptation references an unregistered generator source: {source_id!r}")
    elif category is ProvenanceCategory.LITERATURE_REFERENCE:
        if not source_ids or not rule_ids:
            raise ValueError("literature_reference provenance requires source_id and rule_id references")
        rules = {rule.rule_id: rule for rule in knowledge.rules}
        for rule_id in rule_ids:
            rule = rules.get(rule_id)
            if rule is None or rule.status != "active" or rule.source_id not in source_ids:
                raise ValueError(f"literature_reference has no matching active source rule: {rule_id!r}")
            if rule.evidence_kind is not EvidenceKind.LITERATURE_FACT:
                raise ValueError(f"literature_reference rule is not a literature fact: {rule_id!r}")
    elif category is ProvenanceCategory.SURVEY_DATA:
        if not source_ids or rule_ids:
            raise ValueError("survey_data provenance requires a registered survey source ID")
        for source_id in source_ids:
            source = knowledge.sources.get(source_id)
            if source is None or source.source_type != "survey_data":
                raise ValueError(f"survey_data references an unregistered survey source: {source_id!r}")
    return {
        "category": category.value,
        "source_ids": tuple(source_ids),
        "rule_ids": tuple(rule_ids),
    }


def _resolve_provenance(
    schema: ParameterSchema,
    knowledge: KnowledgeBase,
    *,
    base_config: Mapping[str, object] | None,
    values: Mapping[str, object] | None,
    provenance: Mapping[str, Mapping[str, object]] | None,
    base_provenance: Mapping[str, Mapping[str, object]] | None,
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    if provenance is not None and not isinstance(provenance, Mapping):
        raise ValueError("provenance must be a JSON object")
    if base_provenance is not None and not isinstance(base_provenance, Mapping):
        raise ValueError("base_provenance must be a JSON object")
    explicit_fields = _provided_top_level_parameters(schema, values)
    base_fields = _provided_top_level_parameters(schema, base_config)
    default_records: dict[str, dict[str, object]] = {}
    for field_name, policy in schema.field_provenance.items():
        default_records[field_name] = {
            "category": policy["default_category"],
            "source_ids": tuple(policy["source_ids"]),
            "rule_ids": (),
        }

    for field_name in base_fields:
        default_records[field_name] = {"category": "user_input", "source_ids": (), "rule_ids": ()}
    if base_provenance is not None:
        for input_name, record in base_provenance.items():
            if not isinstance(input_name, str) or not isinstance(record, Mapping):
                raise ValueError("base_provenance entries must map parameter names to objects")
            field_name = _top_level_parameter(schema, input_name)
            if field_name not in base_fields:
                raise ValueError(f"base_provenance references a parameter not present in base_config: {input_name!r}")
            default_records[field_name] = _provenance_record(schema, field_name, record, knowledge=knowledge)

    for field_name in explicit_fields:
        default_records[field_name] = {"category": "user_input", "source_ids": (), "rule_ids": ()}
    if provenance is not None:
        seen_fields: set[str] = set()
        for input_name, record in provenance.items():
            if not isinstance(input_name, str) or not isinstance(record, Mapping):
                raise ValueError("provenance entries must map parameter names to objects")
            field_name = _top_level_parameter(schema, input_name)
            if field_name not in explicit_fields:
                raise ValueError(f"provenance references a parameter not supplied in values: {input_name!r}")
            if field_name in seen_fields:
                raise ValueError(f"provenance specifies parameter {field_name!r} more than once")
            seen_fields.add(field_name)
            default_records[field_name] = _provenance_record(schema, field_name, record, knowledge=knowledge)

    derived_records = {
        name: {
            "category": ProvenanceCategory.DERIVED.value,
            "expression": expression,
            "source_ids": (schema.derived_provenance["source_id"],),
        }
        for name, expression in schema.derived_fields.items()
    }
    return default_records, derived_records


def _read_path(data: Mapping[str, object], path: str) -> object:
    value: object = data
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            raise ValueError(f"invalid parameter path in schema: {path}")
        value = value[part]
    return value


def _write_path(data: dict[str, object], path: str, value: object) -> None:
    parts = path.split(".")
    target = data
    for part in parts[:-1]:
        current = target.get(part)
        if not isinstance(current, dict):
            raise ValueError(f"parameter {path!r} must target an object field")
        target = current
    target[parts[-1]] = deepcopy(value)


def _validate_nested(schema: ParameterSchema, key: str, value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be a JSON object")
    default = schema.defaults[key]
    if not isinstance(default, Mapping):
        raise ValueError(f"{key} is not an object parameter in this schema")
    legacy_nested_keys = {
        alias.removeprefix(f"{key}.")
        for alias in schema.legacy_aliases
        if alias.startswith(f"{key}.")
    }
    unknown = set(value) - set(default) - legacy_nested_keys
    if key == "material_palette":
        invalid_roles = {name for name in value if not isinstance(name, str) or not name.strip()}
        if invalid_roles:
            raise ValueError("material_palette role names must be non-empty strings")
        unknown = set()
    if unknown:
        raise ValueError(f"unknown parameter {key}.{sorted(unknown)[0]!s}")
    return value


def _apply_values(
    schema: ParameterSchema,
    target: dict[str, object],
    values: Mapping[str, object],
    *,
    conflicts: dict[str, tuple[object, str]] | None = None,
    derived_assertions: dict[str, object] | None = None,
) -> None:
    defaults = schema.defaults
    aliases = schema.legacy_aliases
    for input_key, value in values.items():
        if not isinstance(input_key, str):
            raise ValueError("parameter names must be strings")
        if input_key == "derived":
            if derived_assertions is None or not isinstance(value, Mapping):
                raise ValueError("derived must be a JSON object of assertions")
            derived_assertions.update(value)
            continue
        if schema.version >= 3 and input_key == "roof_section":
            if not isinstance(value, Mapping) or value.get("profile") != "symmetric_gable":
                raise ValueError("legacy roof_section is supported only for profile 'symmetric_gable'")
            unknown = set(value) - {"profile", "rise"}
            if unknown:
                raise ValueError(f"unknown legacy roof_section field: {sorted(unknown)[0]}")
            if "rise" in value:
                _record_and_write(
                    target,
                    "roof_profile.ridge_height",
                    value["rise"],
                    "roof_section.rise",
                    conflicts,
                )
            continue
        if schema.version >= 3 and input_key == "eaves":
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("eaves must be a non-negative integer")
            treatment = "hard_gable" if value == 0 else "overhanging_gable"
            for path, normalized in (
                ("eave_profile.side_overhang", value),
                ("eave_profile.gable_end_projection", value),
                ("eave_profile.gable_end_treatment", treatment),
            ):
                _record_and_write(target, path, normalized, "eaves", conflicts)
            continue
        if input_key in aliases:
            canonical_path = aliases[input_key]
        elif input_key in schema.independent_fields:
            canonical_path = input_key
        else:
            raise ValueError(f"unknown parameter: {input_key}")

        nested_fields = {
            "roof_section",
            "interfaces",
            "materials",
            "roof_profile",
            "eave_profile",
            "ridge_profile",
            "material_palette",
        }
        if input_key not in aliases and canonical_path in nested_fields:
            nested = _validate_nested(schema, canonical_path, value)
            for nested_key, nested_value in nested.items():
                nested_path = f"{canonical_path}.{nested_key}"
                normalized_path = aliases.get(nested_path, nested_path)
                _record_and_write(target, normalized_path, nested_value, f"{input_key}.{nested_key}", conflicts)
            continue
        _record_and_write(target, canonical_path, value, input_key, conflicts)


def _record_and_write(
    target: dict[str, object],
    path: str,
    value: object,
    input_name: str,
    conflicts: dict[str, tuple[object, str]] | None,
) -> None:
    if conflicts is not None:
        previous = conflicts.get(path)
        if previous is not None and previous[0] != value:
            raise ParameterConflictError(
                f"conflicting parameter values for {previous[1]!r} and {input_name!r}"
            )
        conflicts[path] = (deepcopy(value), input_name)
    _write_path(target, path, value)


def _derived_values(schema: ParameterSchema, config: Mapping[str, object]) -> dict[str, object]:
    if schema.kind == "hall":
        bay_count = config["bay_count"]
        bay_spacing = config["bay_spacing"]
        depth = config["depth"]
        if not isinstance(bay_count, int) or isinstance(bay_count, bool):
            raise ValueError("bay_count must be an integer")
        if not isinstance(bay_spacing, int) or isinstance(bay_spacing, bool):
            raise ValueError("bay_spacing must be an integer")
        if not isinstance(depth, int) or isinstance(depth, bool):
            raise ValueError("depth must be an integer")
        plinth_width = bay_count * bay_spacing + 1
        if schema.version >= 3:
            eave_profile = config["eave_profile"]
            assert isinstance(eave_profile, Mapping)
            gable_projection = eave_profile["gable_end_projection"]
            side_overhang = eave_profile["side_overhang"]
            if any(isinstance(value, bool) or not isinstance(value, int) for value in (gable_projection, side_overhang)):
                raise ValueError("eave projection values must be integers")
        else:
            eaves = config["eaves"]
            if not isinstance(eaves, int) or isinstance(eaves, bool):
                raise ValueError("eaves must be an integer")
            gable_projection = side_overhang = eaves
        return {
            "plinth_width": plinth_width,
            "plinth_depth": depth,
            "bounds_width": plinth_width + 2 * gable_projection,
            "bounds_depth": depth + 2 * side_overhang,
        }
    if schema.kind == "corridor":
        length = config["length"]
        width = config["width"]
        spacing = config["column_spacing"]
        if any(isinstance(value, bool) or not isinstance(value, int) for value in (length, width, spacing)):
            raise ValueError("corridor length, width, and column_spacing must be integers")
        positions = tuple(sorted(set(range(0, length, spacing)) | {length - 1}))
        interfaces = config["interfaces"]
        assert isinstance(interfaces, Mapping)
        passage_width = interfaces["passage_width"]
        effective_passage_width = max(1, width - 2) if passage_width is None else passage_width
        return {
            "platform_length": length,
            "platform_width": width,
            "post_x_positions": positions,
            "post_count_per_side": len(positions),
            "effective_passage_width": effective_passage_width,
        }
    raise ValueError(f"no deterministic derived-parameter rules for {schema.kind!r}")


def _resolve_generator_parameters(schema: ParameterSchema, config: Mapping[str, object]):
    if config.get("building_type") != schema.kind:
        raise ParameterConflictError(
            f"building_type {config.get('building_type')!r} conflicts with asset kind {schema.kind!r}"
        )
    if config.get("roof_type") != "gable":
        raise ValueError("unsupported roof_type; v1 supports only 'gable'")
    if schema.version < 3:
        roof_section = config.get("roof_section")
        if not isinstance(roof_section, Mapping) or roof_section.get("profile") != "symmetric_gable":
            raise ValueError("unsupported roof_section.profile; v1 supports only 'symmetric_gable'")
    _nonempty(config.get("style"), "style")

    generator_values = {
        parameter_name: _read_path(config, input_path)
        for input_path, parameter_name in schema.generator_fields.items()
    }
    if schema.version >= 3:
        generator_values["roof_profile"] = _roof_profile_from_mapping(generator_values["roof_profile"])
        generator_values["eave_profile"] = _eave_profile_from_mapping(generator_values["eave_profile"])
        generator_values["ridge_profile"] = _ridge_profile_from_mapping(generator_values["ridge_profile"])
        generator_values["material_palette"] = _material_palette_from_mapping(
            generator_values["material_palette"]
        )
    generator_type = HallParameters if schema.kind == "hall" else CorridorParameters
    generator_parameters = generator_type(**generator_values)
    adapter_options = {
        option_name: _read_path(config, input_path)
        for input_path, option_name in schema.adapter_fields.items()
    }
    if schema.kind == "hall":
        if not isinstance(adapter_options.get("through_passage"), bool):
            raise ValueError("interfaces.through_passage must be a boolean")
    else:
        interfaces = config.get("interfaces")
        assert isinstance(interfaces, Mapping)
        passage_width = adapter_options.get("passage_width")
        if passage_width is not None and (
            isinstance(passage_width, bool)
            or not isinstance(passage_width, int)
            or not 1 <= passage_width <= int(config["width"]) - 2
        ):
            raise ValueError("interfaces.passage_width must fit the corridor's clear width")
    return generator_parameters, adapter_options


def resolve_parameters(
    asset_id: str,
    values: Mapping[str, object] | None = None,
    *,
    schema_version: int | None = None,
    base_config: Mapping[str, object] | None = None,
    asset_version: int | None = None,
    provenance: Mapping[str, Mapping[str, object]] | None = None,
    base_provenance: Mapping[str, Mapping[str, object]] | None = None,
) -> ResolvedParameters:
    """Resolve canonical/legacy inputs into a versioned, validated generator configuration."""

    asset = get_asset(asset_id, asset_version)
    schema = load_parameter_schema(asset_id, schema_version, asset_version=asset.version)
    if values is not None and not isinstance(values, Mapping):
        raise ValueError("parameters must be a JSON object")
    if base_config is not None and not isinstance(base_config, Mapping):
        raise ValueError("base_config must be a JSON object")
    config = _thaw(schema.defaults)
    assert isinstance(config, dict)
    if base_config is not None:
        thawed_base = _thaw(base_config)
        assert isinstance(thawed_base, dict)
        _apply_values(schema, config, thawed_base)
    explicit_conflicts: dict[str, tuple[object, str]] = {}
    derived_assertions: dict[str, object] = {}
    _apply_values(schema, config, values or {}, conflicts=explicit_conflicts, derived_assertions=derived_assertions)
    generator_parameters, adapter_options = _resolve_generator_parameters(schema, config)
    derived = _derived_values(schema, config)
    for key, requested in derived_assertions.items():
        if key not in derived:
            raise ValueError(f"unknown derived parameter: {key}")
        if derived[key] != requested:
            raise ParameterConflictError(
                f"derived parameter {key!r} is {derived[key]!r}, not the supplied {requested!r}"
            )
    knowledge = load_knowledge_base(asset.knowledge_base_version)
    parameter_provenance, derived_provenance = _resolve_provenance(
        schema,
        knowledge,
        base_config=base_config,
        values=values,
        provenance=provenance,
        base_provenance=base_provenance,
    )
    rules = {rule.rule_id: rule for rule in knowledge.rules}
    warnings: list[ParameterWarning] = []
    for constraint in schema.soft_constraints:
        rule_id = constraint.get("rule_id")
        field = constraint.get("field")
        operator = constraint.get("operator")
        threshold = constraint.get("value")
        value = config.get(field) if isinstance(field, str) else None
        triggers = operator == "lt" and isinstance(value, (int, float)) and not isinstance(value, bool) and value < threshold
        if triggers:
            rule = rules.get(rule_id)
            if rule is None:
                raise ValueError(f"soft constraint references unknown knowledge rule: {rule_id!r}")
            warnings.append(ParameterWarning(rule.rule_id, rule.statement, rule.evidence_kind, rule.confidence))

    return ResolvedParameters(
        asset_id=asset_id,
        schema_version=schema.version,
        normalized_inputs=_freeze(config),
        derived_parameters=_freeze(derived),
        generator_parameters=generator_parameters,
        adapter_options=_freeze(adapter_options),
        warnings=tuple(warnings),
        parameter_provenance=parameter_provenance,
        derived_provenance=derived_provenance,
    )
