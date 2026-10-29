"""Validated parameter schemas and deterministic generator adapters."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any

from ..assets.registry import get_asset
from ..generators.hall import CorridorParameters, HallParameters
from ..knowledge import ConfidenceLevel, EvidenceKind, load_knowledge_base


class ParameterConflictError(ValueError):
    """Raised when supplied values disagree or contradict derived geometry."""


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
        object.__setattr__(self, "defaults", _freeze(self.defaults))
        object.__setattr__(self, "derived_fields", _freeze(self.derived_fields))
        object.__setattr__(self, "generator_fields", _freeze(self.generator_fields))
        object.__setattr__(self, "adapter_fields", _freeze(self.adapter_fields))
        object.__setattr__(self, "legacy_aliases", _freeze(self.legacy_aliases))
        object.__setattr__(self, "hard_constraints", tuple(_freeze(item) for item in self.hard_constraints))
        object.__setattr__(self, "soft_constraints", tuple(_freeze(item) for item in self.soft_constraints))


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
    )


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
    unknown = set(value) - set(default)
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
        if input_key in aliases:
            canonical_path = aliases[input_key]
        elif input_key in schema.independent_fields:
            canonical_path = input_key
        else:
            raise ValueError(f"unknown parameter: {input_key}")

        if input_key not in aliases and canonical_path in ("roof_section", "interfaces", "materials"):
            nested = _validate_nested(schema, canonical_path, value)
            for nested_key, nested_value in nested.items():
                nested_path = f"{canonical_path}.{nested_key}"
                _record_and_write(target, nested_path, nested_value, f"{input_key}.{nested_key}", conflicts)
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
        eaves = config["eaves"]
        if not isinstance(eaves, int) or isinstance(eaves, bool):
            raise ValueError("eaves must be an integer")
        plinth_width = bay_count * bay_spacing + 1
        return {
            "plinth_width": plinth_width,
            "plinth_depth": depth,
            "bounds_width": plinth_width + 2 * eaves,
            "bounds_depth": depth + 2 * eaves,
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
    roof_section = config.get("roof_section")
    if not isinstance(roof_section, Mapping) or roof_section.get("profile") != "symmetric_gable":
        raise ValueError("unsupported roof_section.profile; v1 supports only 'symmetric_gable'")
    _nonempty(config.get("style"), "style")

    generator_values = {
        parameter_name: _read_path(config, input_path)
        for input_path, parameter_name in schema.generator_fields.items()
    }
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
        _apply_values(schema, config, base_config)
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
    )
