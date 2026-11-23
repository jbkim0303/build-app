"""Batched CSV -> Neo4j writer (UNWIND + MERGE/CREATE in managed write transactions)."""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from typing import Any, Iterator

from .spec import LoadConfig, NodeSpec, Prop, RelSpec

log = logging.getLogger("neo4j_loader")


class CsvDataError(ValueError):
    """A CSV file is missing columns or holds a value that can't be converted."""


def q(name: str) -> str:
    """Backtick-quote a label, relationship type or property name for Cypher.

    Labels and types can't be passed as query parameters, so every identifier that comes from
    the config is quoted (with embedded backticks doubled) rather than pasted in raw.
    """
    if not name:
        raise ValueError("empty identifier")
    return "`" + name.replace("`", "``") + "`"


def _key_map(props: list[Prop], source: str) -> str:
    """`{`id`: row.k.`id`, ...}` — keys are matched by value from the row payload."""
    return "{" + ", ".join(f"{q(p.name)}: row.{source}.{q(p.name)}" for p in props) + "}"


def node_query(spec: NodeSpec) -> str:
    verb = "MERGE" if spec.mode == "merge" else "CREATE"
    lines = [
        "UNWIND $rows AS row",
        f"{verb} (n:{q(spec.label)} {_key_map(spec.key, 'k')})",
        "SET n += row.p",
    ]
    if spec.extra_labels:
        lines.append("SET n:" + ":".join(q(label) for label in spec.extra_labels))
    lines.append("RETURN count(*) AS written")
    return "\n".join(lines)


def rel_query(spec: RelSpec) -> str:
    verb = "MERGE" if spec.mode == "merge" else "CREATE"
    rel_key = " " + _key_map(spec.key, "rk") if spec.key else ""
    return "\n".join([
        "UNWIND $rows AS row",
        f"MATCH (a:{q(spec.start.label)} {_key_map(spec.start.keys, 'a')})",
        f"MATCH (b:{q(spec.end.label)} {_key_map(spec.end.keys, 'b')})",
        f"{verb} (a)-[r:{q(spec.type)}{rel_key}]->(b)",
        "SET r += row.p",
        "RETURN count(*) AS written",
    ])


def constraint_query(spec: NodeSpec) -> str:
    """Uniqueness constraint on the node key (Neo4j 5 syntax; also makes MERGE use an index)."""
    name = "csv_" + "_".join([spec.label, *[p.name for p in spec.key]])
    name = "".join(c if c.isalnum() or c == "_" else "_" for c in name)
    if len(spec.key) == 1:
        target = f"n.{q(spec.key[0].name)}"
    else:
        target = "(" + ", ".join(f"n.{q(p.name)}" for p in spec.key) + ")"
    return (f"CREATE CONSTRAINT {q(name)} IF NOT EXISTS "
            f"FOR (n:{q(spec.label)}) REQUIRE {target} IS UNIQUE")


@dataclass
class LoadStats:
    kind: str
    name: str
    file: str
    rows_read: int = 0
    rows_written: int = 0
    rows_skipped: int = 0  # empty key or bad value (with on_error: skip)
    rows_unmatched: int = 0  # relationships whose start or end node was not found
    counters: dict[str, int] = field(default_factory=dict)

    def add_counters(self, counters: dict[str, int]) -> None:
        for name, value in counters.items():
            if value:
                self.counters[name] = self.counters.get(name, 0) + value

    def summary(self) -> str:
        parts = [f"read {self.rows_read}", f"written {self.rows_written}"]
        if self.rows_skipped:
            parts.append(f"skipped {self.rows_skipped}")
        if self.rows_unmatched:
            parts.append(f"no matching node {self.rows_unmatched}")
        parts += [f"{k.replace('_', ' ')} {v}" for k, v in sorted(self.counters.items())]
        return f"{self.name} from {self.file}: " + ", ".join(parts)


COUNTER_FIELDS = ("nodes_created", "nodes_deleted", "relationships_created",
                  "relationships_deleted", "properties_set", "labels_added")


def _write_batch(tx, query: str, rows: list[dict]) -> tuple[int, dict[str, int]]:
    result = tx.run(query, rows=rows)
    record = result.single()
    summary = result.consume()
    counters = {name: getattr(summary.counters, name, 0) for name in COUNTER_FIELDS}
    return (record["written"] if record else 0), counters


class CsvRows:
    """Reads one CSV file into row payloads ({"k": key props, "p": other props, ...})."""

    def __init__(self, spec: NodeSpec | RelSpec):
        self.spec = spec

    def _groups(self) -> dict[str, list[Prop]]:
        spec = self.spec
        if isinstance(spec, NodeSpec):
            return {"k": spec.key, "p": spec.properties}
        groups = {"a": spec.start.keys, "b": spec.end.keys, "p": spec.properties}
        if spec.key:
            groups["rk"] = spec.key
        return groups

    def _required_groups(self) -> set[str]:
        return {"k", "a", "b", "rk"}

    def iter_rows(self, stats: LoadStats) -> Iterator[dict[str, Any]]:
        spec = self.spec
        opts = spec.csv
        groups = self._groups()
        try:
            handle = open(spec.file, newline="", encoding=opts.encoding)
        except FileNotFoundError:
            raise CsvDataError(f"{spec.file}: file not found") from None
        with handle:
            reader = csv.DictReader(handle, delimiter=opts.delimiter)
            header = [h.strip() for h in (reader.fieldnames or [])]
            if not header:
                raise CsvDataError(f"{spec.file}: file is empty or has no header row")
            reader.fieldnames = header
            mapped = {p.column for props in groups.values() for p in props}
            missing = sorted(mapped - set(header))
            if missing:
                raise CsvDataError(
                    f"{spec.file}: column(s) {', '.join(missing)} not in header ({', '.join(header)})")
            if spec.all_columns:
                taken = {p.name for props in groups.values() for p in props}
                extra_type = "auto" if spec.infer_types else "str"
                groups["p"] = groups["p"] + [
                    Prop(col, col, extra_type) for col in header
                    if col and col not in mapped and col not in taken
                ]

            required = self._required_groups()
            for record in reader:
                stats.rows_read += 1
                line = reader.line_num
                try:
                    row = {}
                    for group, props in groups.items():
                        values = {}
                        for prop in props:
                            try:
                                value = prop.convert(record.get(prop.column), opts.list_separator)
                            except ValueError as exc:
                                raise CsvDataError(
                                    f"{spec.file}:{line}: column {prop.column!r}: can't convert "
                                    f"{record.get(prop.column)!r} to {prop.type} ({exc})") from None
                            if value is None:
                                if group in required:
                                    raise CsvDataError(
                                        f"{spec.file}:{line}: key column {prop.column!r} is empty")
                                continue
                            values[prop.name] = value
                        row[group] = values
                except CsvDataError as exc:
                    if opts.on_error == "skip":
                        log.warning("skipping row: %s", exc)
                        stats.rows_skipped += 1
                        continue
                    raise
                yield row


def _batches(rows: Iterator[dict], size: int) -> Iterator[list[dict]]:
    batch: list[dict] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


class Neo4jCsvLoader:
    """Loads NodeSpecs and RelSpecs into Neo4j.

    `driver` is a `neo4j.Driver` (or anything with the same `session()` API). With
    `dry_run=True` no driver is needed: files are read and validated, and the Cypher is logged.
    """

    def __init__(self, driver=None, database: str | None = None, batch_size: int = 1000,
                 dry_run: bool = False):
        if driver is None and not dry_run:
            raise ValueError("a Neo4j driver is required unless dry_run=True")
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        self.driver = driver
        self.database = database
        self.batch_size = batch_size
        self.dry_run = dry_run

    def _session(self):
        return self.driver.session(database=self.database) if self.database else self.driver.session()

    def create_constraints(self, specs: list[NodeSpec]) -> list[str]:
        queries = [constraint_query(s) for s in specs if s.constraint and s.mode == "merge"]
        queries = list(dict.fromkeys(queries))  # same label+key listed twice -> one constraint
        for query in queries:
            log.info("constraint: %s", query)
            if not self.dry_run:
                with self._session() as session:
                    session.run(query).consume()
        return queries

    def load(self, spec: NodeSpec | RelSpec) -> LoadStats:
        query = node_query(spec) if isinstance(spec, NodeSpec) else rel_query(spec)
        stats = LoadStats(spec.kind, spec.name, str(spec.file))
        log.info("loading %s from %s", spec.name, spec.file)
        log.debug("cypher:\n%s", query)
        rows = CsvRows(spec).iter_rows(stats)

        if self.dry_run:
            for i, row in enumerate(rows):
                if i == 0:
                    log.info("first row payload: %s", row)
            stats.rows_written = stats.rows_read - stats.rows_skipped
            return stats

        with self._session() as session:
            for batch in _batches(rows, self.batch_size):
                written, counters = session.execute_write(_write_batch, query, batch)
                stats.rows_written += written
                stats.add_counters(counters)
                if isinstance(spec, RelSpec):
                    stats.rows_unmatched += len(batch) - written
                log.debug("batch of %d rows: %d written", len(batch), written)
        if stats.rows_unmatched:
            log.warning("%s: %d row(s) had no matching start/end node", spec.name,
                        stats.rows_unmatched)
        return stats

    def run(self, config: LoadConfig, constraints: bool = True) -> list[LoadStats]:
        """Constraints first, then all nodes, then all relationships (so endpoints exist)."""
        if constraints:
            self.create_constraints(config.nodes)
        results = []
        for spec in [*config.nodes, *config.relationships]:
            stats = self.load(spec)
            log.info(stats.summary())
            results.append(stats)
        return results
