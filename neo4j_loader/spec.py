"""Mapping specs: how CSV columns become Neo4j nodes, relationships and typed properties."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Callable

TRUE_VALUES = {"true", "t", "yes", "y", "1"}
FALSE_VALUES = {"false", "f", "no", "n", "0"}


class SpecError(ValueError):
    """The mapping config is invalid."""


def _to_bool(value: str) -> bool:
    lowered = value.lower()
    if lowered in TRUE_VALUES:
        return True
    if lowered in FALSE_VALUES:
        return False
    raise ValueError(f"not a boolean: {value!r}")


def _to_auto(value: str) -> Any:
    """Best-effort type: int, float, bool, else the original string.

    Values with a leading zero ("007") stay strings so codes and postcodes keep their digits.
    """
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    stripped = value.lstrip("+-")
    if stripped.isdigit() and not (len(stripped) > 1 and stripped.startswith("0")):
        return int(value)
    try:
        number = float(value)
    except ValueError:
        return value
    if not math.isfinite(number):  # "nan", "inf" are more likely text than numbers
        return value
    if stripped.startswith("0") and not stripped.startswith("0."):
        return value
    return number


CONVERTERS: dict[str, Callable[[str], Any]] = {
    "str": str,
    "string": str,
    "int": int,
    "integer": int,
    "float": float,
    "bool": _to_bool,
    "boolean": _to_bool,
    "date": date.fromisoformat,
    "datetime": datetime.fromisoformat,
    "time": time.fromisoformat,
    "auto": _to_auto,
}


def _check_type(type_name: str) -> str:
    base = type_name[5:] if type_name.startswith("list:") else type_name
    if type_name != "list" and base not in CONVERTERS:
        allowed = ", ".join(sorted(CONVERTERS)) + ", list, list:<type>"
        raise SpecError(f"unknown type {type_name!r} (allowed: {allowed})")
    return type_name


@dataclass(frozen=True)
class Prop:
    """One Neo4j property, read from one CSV column and converted to a type."""

    name: str
    column: str
    type: str = "str"

    def __post_init__(self) -> None:
        _check_type(self.type)

    def convert(self, raw: str | None, list_separator: str = ";") -> Any:
        """Convert a raw CSV value; returns None for empty cells (the property is then not set)."""
        if raw is None:
            return None
        raw = raw.strip()
        if raw == "":
            return None
        if self.type == "list" or self.type.startswith("list:"):
            convert = CONVERTERS[self.type[5:] if self.type.startswith("list:") else "str"]
            return [convert(part.strip()) for part in raw.split(list_separator) if part.strip()]
        return CONVERTERS[self.type](raw)


def parse_prop(name: str, value: Any) -> Prop:
    """`name: int`, `name: {column: csv_col, type: int}`, or `name: null` (string, same column)."""
    if value is None:
        return Prop(name, name)
    if isinstance(value, str):
        return Prop(name, name, value)
    if isinstance(value, dict):
        unknown = set(value) - {"column", "type"}
        if unknown:
            raise SpecError(f"property {name!r}: unknown option(s) {sorted(unknown)}")
        return Prop(name, value.get("column", name), value.get("type", "str"))
    raise SpecError(f"property {name!r}: expected a type name or a mapping, got {value!r}")


def parse_props(value: Any) -> list[Prop]:
    if value is None:
        return []
    if isinstance(value, list):  # list of column names, all strings
        return [Prop(str(name), str(name)) for name in value]
    if isinstance(value, dict):
        return [parse_prop(str(name), spec) for name, spec in value.items()]
    raise SpecError(f"properties must be a list or a mapping, got {value!r}")


@dataclass
class CsvOptions:
    delimiter: str = ","
    encoding: str = "utf-8-sig"  # also strips an Excel BOM
    list_separator: str = ";"
    on_error: str = "fail"  # fail | skip: what to do with a row whose value can't be converted

    def __post_init__(self) -> None:
        if self.on_error not in ("fail", "skip"):
            raise SpecError(f"on_error must be 'fail' or 'skip', got {self.on_error!r}")
        if len(self.delimiter) != 1:
            raise SpecError(f"delimiter must be one character, got {self.delimiter!r}")


@dataclass
class NodeSpec:
    """Each CSV row becomes (or updates) one node, identified by its key properties."""

    file: Path
    label: str
    key: list[Prop]
    properties: list[Prop] = field(default_factory=list)  # non-key properties
    extra_labels: list[str] = field(default_factory=list)
    mode: str = "merge"  # merge (upsert on key) | create (always insert)
    all_columns: bool = False  # also store every column not mapped explicitly
    infer_types: bool = False  # type for those extra columns: auto (True) or str (False)
    constraint: bool = True  # create a uniqueness constraint on the key
    csv: CsvOptions = field(default_factory=CsvOptions)

    @property
    def kind(self) -> str:
        return "nodes"

    @property
    def name(self) -> str:
        return f"(:{self.label})"


@dataclass
class Endpoint:
    """How a relationship row finds an existing node: label + key property values from columns."""

    label: str
    keys: list[Prop]


@dataclass
class RelSpec:
    """Each CSV row becomes one relationship between two existing nodes."""

    file: Path
    type: str
    start: Endpoint
    end: Endpoint
    key: list[Prop] = field(default_factory=list)  # props that tell parallel relationships apart
    properties: list[Prop] = field(default_factory=list)
    mode: str = "merge"
    all_columns: bool = False
    infer_types: bool = False
    csv: CsvOptions = field(default_factory=CsvOptions)

    @property
    def kind(self) -> str:
        return "relationships"

    @property
    def name(self) -> str:
        return f"(:{self.start.label})-[:{self.type}]->(:{self.end.label})"


@dataclass
class LoadConfig:
    nodes: list[NodeSpec] = field(default_factory=list)
    relationships: list[RelSpec] = field(default_factory=list)
    batch_size: int = 1000


def _split_key(key: Any, props: list[Prop], where: str) -> tuple[list[Prop], list[Prop]]:
    """Pull key props out of the property list (adding them as strings when not listed)."""
    if key is None:
        return [], props
    names = [key] if isinstance(key, str) else list(key)
    if not names or not all(isinstance(n, str) for n in names):
        raise SpecError(f"{where}: key must be a property name or a list of names")
    by_name = {p.name: p for p in props}
    key_props = [by_name.get(n, Prop(n, n)) for n in names]
    rest = [p for p in props if p.name not in names]
    return key_props, rest


def parse_endpoint(value: Any, where: str) -> Endpoint:
    """`{label: Team, key: id, column: home_team_id, type: int}` or
    `{label: Team, keys: {code: home_code, season: {column: season, type: int}}}`."""
    if not isinstance(value, dict) or "label" not in value:
        raise SpecError(f"{where}: needs a mapping with 'label' and 'key'/'keys'")
    if "keys" in value:
        # in endpoint keys a plain string value is the column name, not a type
        if isinstance(value["keys"], dict):
            keys = [
                Prop(name, spec) if isinstance(spec, str) else parse_prop(name, spec)
                for name, spec in value["keys"].items()
            ]
        else:
            keys = parse_props(value["keys"])
    elif "key" in value:
        keys = [Prop(value["key"], value.get("column", value["key"]), value.get("type", "str"))]
    else:
        raise SpecError(f"{where}: needs 'key' (with optional 'column', 'type') or 'keys'")
    if not keys:
        raise SpecError(f"{where}: 'keys' is empty")
    return Endpoint(str(value["label"]), keys)


def _csv_options(entry: dict, defaults: dict) -> CsvOptions:
    merged = {**defaults, **entry}
    return CsvOptions(
        delimiter=merged.get("delimiter", ","),
        encoding=merged.get("encoding", "utf-8-sig"),
        list_separator=merged.get("list_separator", ";"),
        on_error=merged.get("on_error", "fail"),
    )


def _mode(entry: dict, where: str) -> str:
    mode = entry.get("mode", "merge")
    if mode not in ("merge", "create"):
        raise SpecError(f"{where}: mode must be 'merge' or 'create', got {mode!r}")
    return mode


NODE_KEYS = {"file", "label", "labels", "key", "properties", "mode", "all_columns", "infer_types",
             "constraint", "delimiter", "encoding", "list_separator", "on_error"}
REL_KEYS = {"file", "type", "from", "to", "key", "properties", "mode", "all_columns", "infer_types",
            "delimiter", "encoding", "list_separator", "on_error"}


def parse_config(raw: dict, base_dir: Path | str = ".") -> LoadConfig:
    """Build a LoadConfig from a dict (the parsed YAML/JSON config file)."""
    if not isinstance(raw, dict):
        raise SpecError("config must be a mapping with 'nodes' and/or 'relationships'")
    base_dir = Path(base_dir)
    defaults = dict(raw.get("defaults") or {})
    data_dir = base_dir / defaults.pop("data_dir", ".")
    batch_size = int(defaults.pop("batch_size", raw.get("batch_size", 1000)))
    if batch_size < 1:
        raise SpecError("batch_size must be at least 1")

    config = LoadConfig(batch_size=batch_size)
    for i, entry in enumerate(raw.get("nodes") or []):
        where = f"nodes[{i}]"
        unknown = set(entry) - NODE_KEYS
        if unknown:
            raise SpecError(f"{where}: unknown option(s) {sorted(unknown)}")
        for required in ("file", "label", "key"):
            if required not in entry:
                raise SpecError(f"{where}: missing {required!r}")
        props = parse_props(entry.get("properties"))
        key, rest = _split_key(entry["key"], props, where)
        all_columns = entry.get("all_columns", "properties" not in entry)
        config.nodes.append(NodeSpec(
            file=data_dir / entry["file"],
            label=str(entry["label"]),
            key=key,
            properties=rest,
            extra_labels=[str(label) for label in entry.get("labels") or []],
            mode=_mode(entry, where),
            all_columns=bool(all_columns),
            infer_types=bool(entry.get("infer_types", defaults.get("infer_types", False))),
            constraint=bool(entry.get("constraint", True)),
            csv=_csv_options(entry, defaults),
        ))

    for i, entry in enumerate(raw.get("relationships") or []):
        where = f"relationships[{i}]"
        unknown = set(entry) - REL_KEYS
        if unknown:
            raise SpecError(f"{where}: unknown option(s) {sorted(unknown)}")
        for required in ("file", "type", "from", "to"):
            if required not in entry:
                raise SpecError(f"{where}: missing {required!r}")
        props = parse_props(entry.get("properties"))
        key, rest = _split_key(entry.get("key"), props, where)
        config.relationships.append(RelSpec(
            file=data_dir / entry["file"],
            type=str(entry["type"]),
            start=parse_endpoint(entry["from"], f"{where}.from"),
            end=parse_endpoint(entry["to"], f"{where}.to"),
            key=key,
            properties=rest,
            mode=_mode(entry, where),
            all_columns=bool(entry.get("all_columns", False)),
            infer_types=bool(entry.get("infer_types", defaults.get("infer_types", False))),
            csv=_csv_options(entry, defaults),
        ))

    if not config.nodes and not config.relationships:
        raise SpecError("config has no 'nodes' or 'relationships' entries")
    return config


def load_config_file(path: Path | str) -> LoadConfig:
    """Read a .yaml/.yml or .json mapping file; CSV paths are relative to the file's folder."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover
            raise SpecError("YAML configs need PyYAML: pip install pyyaml") from exc
        raw = yaml.safe_load(text)
    else:
        raw = json.loads(text)
    return parse_config(raw, path.parent)
