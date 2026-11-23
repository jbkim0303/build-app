"""Command line: `python -m neo4j_loader {load,nodes,rels} ...`.

Connection settings come from flags or the NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD /
NEO4J_DATABASE environment variables.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from .loader import CsvDataError, Neo4jCsvLoader
from .spec import (CsvOptions, Endpoint, LoadConfig, NodeSpec, Prop, RelSpec, SpecError,
                   load_config_file)

log = logging.getLogger("neo4j_loader")


def _parse_types(items: list[str]) -> dict[str, str]:
    """`--type capacity=int --type founded=int` -> {"capacity": "int", "founded": "int"}."""
    types = {}
    for item in items or []:
        name, sep, type_name = item.partition("=")
        if not sep or not name or not type_name:
            raise SpecError(f"--type expects COLUMN=TYPE, got {item!r}")
        types[name.strip()] = type_name.strip()
    return types


def parse_endpoint_arg(text: str, types: dict[str, str]) -> Endpoint:
    """`Team:id=home_team_id[:int]` or `Team:code=home_code,season=season:int`.

    A bare `Team:id` means property `id` read from column `id`.
    """
    label, sep, rest = text.partition(":")
    if not sep or not label or not rest:
        raise SpecError(f"endpoint must look like Label:prop=column[:type], got {text!r}")
    keys = []
    for part in rest.split(","):
        prop, eq, column = part.partition("=")
        column = column if eq else prop
        column, colon, type_name = column.partition(":")
        prop, column = prop.strip(), column.strip()
        keys.append(Prop(prop, column, type_name.strip() if colon else types.get(column, "str")))
    return Endpoint(label.strip(), keys)


def _props(columns: list[str] | None, types: dict[str, str]) -> list[Prop]:
    """Listed columns; without a list, the --type'd columns (the rest come from all_columns)."""
    if columns is None:
        return [Prop(c, c, t) for c, t in types.items()]
    return [Prop(c, c, types.get(c, "str")) for c in columns]


def _csv_opts(args) -> CsvOptions:
    return CsvOptions(delimiter=args.delimiter, encoding=args.encoding,
                      list_separator=args.list_separator, on_error=args.on_error)


def build_config(args) -> LoadConfig:
    if args.command == "load":
        config = load_config_file(args.config)
        if args.batch_size:
            config.batch_size = args.batch_size
        return config

    types = _parse_types(args.type)
    batch_size = args.batch_size or 1000
    keys = [k.strip() for k in args.key.split(",")] if getattr(args, "key", None) else []
    explicit = args.properties is not None
    if args.command == "nodes":
        props = _props(args.properties, types)
        spec = NodeSpec(
            file=Path(args.csv), label=args.label,
            key=_props(keys, types),
            properties=[p for p in props if p.name not in keys],
            extra_labels=args.extra_label or [], mode=args.mode,
            all_columns=not explicit, infer_types=args.infer_types,
            constraint=not args.no_constraints, csv=_csv_opts(args),
        )
        return LoadConfig(nodes=[spec], batch_size=batch_size)

    start, end = parse_endpoint_arg(args.start, types), parse_endpoint_arg(args.end, types)
    endpoint_cols = {p.column for p in start.keys + end.keys}
    props = _props(args.properties, types) if explicit or args.all_columns else []
    props = [p for p in props if explicit or p.column not in endpoint_cols]
    spec = RelSpec(
        file=Path(args.csv), type=args.rel_type, start=start, end=end,
        key=_props(keys, types), properties=[p for p in props if p.name not in keys],
        mode=args.mode, all_columns=args.all_columns, infer_types=args.infer_types,
        csv=_csv_opts(args),
    )
    return LoadConfig(relationships=[spec], batch_size=batch_size)


def make_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    conn = common.add_argument_group("connection")
    conn.add_argument("--uri", default=os.environ.get("NEO4J_URI", "neo4j://localhost:7687"))
    conn.add_argument("--user", default=os.environ.get("NEO4J_USER", "neo4j"))
    conn.add_argument("--password", default=os.environ.get("NEO4J_PASSWORD"),
                      help="default: $NEO4J_PASSWORD")
    conn.add_argument("--database", default=os.environ.get("NEO4J_DATABASE"),
                      help="default: $NEO4J_DATABASE or the server's default database")
    run = common.add_argument_group("run")
    run.add_argument("--batch-size", type=int, help="rows per transaction (default 1000)")
    run.add_argument("--dry-run", action="store_true",
                     help="read and validate the CSV files and print the Cypher; don't connect")
    run.add_argument("--no-constraints", action="store_true",
                     help="don't create uniqueness constraints on node keys")
    run.add_argument("-v", "--verbose", action="count", default=0)

    csv_opts = argparse.ArgumentParser(add_help=False)
    g = csv_opts.add_argument_group("csv")
    g.add_argument("--delimiter", default=",")
    g.add_argument("--encoding", default="utf-8-sig")
    g.add_argument("--list-separator", default=";")
    g.add_argument("--on-error", choices=["fail", "skip"], default="fail",
                   help="bad rows: stop (default) or skip with a warning")
    g.add_argument("--type", action="append", metavar="COLUMN=TYPE",
                   help="column type: str int float bool date datetime time auto list list:<type>")
    g.add_argument("--properties", nargs="*", metavar="COLUMN",
                   help="columns to store (default for nodes: all columns)")
    g.add_argument("--infer-types", action="store_true",
                   help="guess int/float/bool for columns without --type")
    g.add_argument("--mode", choices=["merge", "create"], default="merge")

    parser = argparse.ArgumentParser(prog="python -m neo4j_loader",
                                     description="Upload CSV data into Neo4j.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("load", parents=[common], help="load everything in a YAML/JSON mapping file")
    p.add_argument("config", help="mapping file (.yaml, .yml or .json)")

    p = sub.add_parser("nodes", parents=[common, csv_opts], help="one CSV file -> nodes")
    p.add_argument("csv")
    p.add_argument("--label", required=True)
    p.add_argument("--key", required=True, help="key column(s), comma separated")
    p.add_argument("--extra-label", action="append")

    p = sub.add_parser("rels", parents=[common, csv_opts], help="one CSV file -> relationships")
    p.add_argument("csv")
    p.add_argument("--rel-type", dest="rel_type", required=True,
                   help="relationship type, e.g. PLAYS_AT")
    p.add_argument("--from", dest="start", required=True, metavar="LABEL:PROP=COLUMN[:TYPE]")
    p.add_argument("--to", dest="end", required=True, metavar="LABEL:PROP=COLUMN[:TYPE]")
    p.add_argument("--key", help="relationship key column(s), for parallel relationships")
    p.add_argument("--all-columns", action="store_true",
                   help="store every column not used for matching as a property")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    level = logging.DEBUG if args.verbose > 1 else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(message)s")
    if args.verbose:
        log.setLevel(logging.DEBUG)

    try:
        config = build_config(args)
    except (SpecError, FileNotFoundError, ValueError) as exc:
        log.error("%s", exc)
        return 2

    driver = None
    if not args.dry_run:
        if not args.password:
            log.error("no password: pass --password or set NEO4J_PASSWORD")
            return 2
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    try:
        if driver is not None:
            driver.verify_connectivity()
        loader = Neo4jCsvLoader(driver, database=args.database, batch_size=config.batch_size,
                                dry_run=args.dry_run)
        if args.dry_run:
            from .loader import node_query, rel_query
            for spec in config.nodes:
                print(f"-- {spec.name}  <- {spec.file}\n{node_query(spec)}\n")
            for spec in config.relationships:
                print(f"-- {spec.name}  <- {spec.file}\n{rel_query(spec)}\n")
        results = loader.run(config, constraints=not args.no_constraints)
    except (CsvDataError, SpecError) as exc:
        log.error("%s", exc)
        return 1
    except Exception as exc:  # connection/auth/Cypher errors from the driver
        log.error("%s: %s", type(exc).__name__, exc)
        return 1
    finally:
        if driver is not None:
            driver.close()

    print("\nSummary" + (" (dry run, nothing written)" if args.dry_run else ""))
    for stats in results:
        print("  " + stats.summary())
    return 0 if not any(s.rows_unmatched for s in results) else 3


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
