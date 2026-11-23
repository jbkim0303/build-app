"""Tests for neo4j_loader. They use a fake driver, so no Neo4j server is needed."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from neo4j_loader import (CsvDataError, Neo4jCsvLoader, NodeSpec, Prop, SpecError,
                          load_config_file, node_query, parse_config, rel_query)
from neo4j_loader.cli import main, parse_endpoint_arg
from neo4j_loader.loader import constraint_query, q
from neo4j_loader.spec import CsvOptions

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "k_league.yaml"


# --- a tiny in-memory stand-in for the driver ------------------------------------------------

class FakeGraph:
    """Records every query and simulates MATCH for relationship batches.

    Nodes are stored as {label: [key dict, ...]}; a relationship row is "written" only when both
    endpoints exist, like the real MATCH would do.
    """

    def __init__(self):
        self.queries: list[tuple[str, list | None]] = []
        self.nodes: dict[str, list[dict]] = {}
        self.rels: list[tuple] = []

    def run(self, query: str, rows=None):
        self.queries.append((query, rows))
        written = 0
        if rows is not None and "MATCH (a:" in query:
            start = query.split("MATCH (a:`")[1].split("`")[0]
            end = query.split("MATCH (b:`")[1].split("`")[0]
            rel_type = query.split("[r:`")[1].split("`")[0]
            for row in rows:
                if row["a"] in self.nodes.get(start, []) and row["b"] in self.nodes.get(end, []):
                    self.rels.append((start, row["a"], rel_type, end, row["b"], row["p"]))
                    written += 1
        elif rows is not None:
            label = query.split("(n:`")[1].split("`")[0]
            for row in rows:
                if row["k"] not in self.nodes.setdefault(label, []):
                    self.nodes[label].append(row["k"])
                written += 1
        counters = SimpleNamespace(nodes_created=written if "(n:" in query else 0,
                                   relationships_created=written if "[r:" in query else 0)
        record = {"written": written}
        return SimpleNamespace(single=lambda: record, consume=lambda: SimpleNamespace(counters=counters))


class FakeSession:
    def __init__(self, graph):
        self.graph = graph

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query, **params):
        return self.graph.run(query, params.get("rows"))

    def execute_write(self, fn, *args):
        return fn(self.graph, *args)


class FakeDriver:
    def __init__(self):
        self.graph = FakeGraph()
        self.databases = []

    def session(self, database=None):
        self.databases.append(database)
        return FakeSession(self.graph)


def write_csv(path: Path, text: str) -> Path:
    path.write_text(text.lstrip(), encoding="utf-8")
    return path


# --- type conversion -------------------------------------------------------------------------

@pytest.mark.parametrize("type_name,raw,expected", [
    ("str", "  hi ", "hi"),
    ("int", "42", 42),
    ("float", "2.5", 2.5),
    ("bool", "Yes", True),
    ("bool", "0", False),
    ("date", "2026-03-07", date(2026, 3, 7)),
    ("datetime", "2026-03-07T19:00:00+09:00",
     datetime(2026, 3, 7, 19, tzinfo=timezone(timedelta(hours=9)))),
    ("list", "a; b;;c", ["a", "b", "c"]),
    ("list:int", "1;2;3", [1, 2, 3]),
    ("auto", "12", 12),
    ("auto", "1.5", 1.5),
    ("auto", "true", True),
    ("auto", "007", "007"),
    ("auto", "nan", "nan"),
    ("auto", "Seoul", "Seoul"),
    ("int", "", None),
    ("int", "   ", None),
])
def test_convert(type_name, raw, expected):
    assert Prop("x", "x", type_name).convert(raw) == expected


def test_unknown_type_rejected():
    with pytest.raises(SpecError, match="unknown type"):
        Prop("x", "x", "number")


def test_bad_bool():
    with pytest.raises(ValueError):
        Prop("x", "x", "bool").convert("maybe")


# --- Cypher ----------------------------------------------------------------------------------

def test_identifiers_are_quoted():
    assert q("Team") == "`Team`"
    assert q("we`ird") == "`we``ird`"


def test_node_query_shape():
    spec = NodeSpec(file=Path("x.csv"), label="Team", key=[Prop("code", "code")],
                    extra_labels=["Club"])
    assert node_query(spec) == (
        "UNWIND $rows AS row\n"
        "MERGE (n:`Team` {`code`: row.k.`code`})\n"
        "SET n += row.p\n"
        "SET n:`Club`\n"
        "RETURN count(*) AS written")
    spec.mode = "create"
    assert "CREATE (n:`Team`" in node_query(spec)


def test_rel_query_and_constraints():
    config = parse_config({
        "nodes": [{"file": "t.csv", "label": "Team", "key": ["league", "code"]}],
        "relationships": [{"file": "m.csv", "type": "PLAYED", "key": "match_id",
                           "from": {"label": "Team", "key": "code", "column": "home"},
                           "to": {"label": "Team", "keys": {"code": "away"}}}],
    })
    query = rel_query(config.relationships[0])
    assert "MATCH (a:`Team` {`code`: row.a.`code`})" in query
    assert "MERGE (a)-[r:`PLAYED` {`match_id`: row.rk.`match_id`}]->(b)" in query
    assert constraint_query(config.nodes[0]) == (
        "CREATE CONSTRAINT `csv_Team_league_code` IF NOT EXISTS "
        "FOR (n:`Team`) REQUIRE (n.`league`, n.`code`) IS UNIQUE")


# --- config parsing --------------------------------------------------------------------------

def test_example_config_parses():
    config = load_config_file(EXAMPLE)
    assert config.batch_size == 500
    assert [n.label for n in config.nodes] == ["League", "Stadium", "Team", "Match"]
    match = config.nodes[3]
    assert match.key == [Prop("id", "match_id", "str")]
    assert all(p.name != "id" for p in match.properties)
    assert config.nodes[0].file == EXAMPLE.parent / "data" / "leagues.csv"
    home_in = config.relationships[3]
    assert home_in.start.keys == [Prop("code", "home_code")]
    assert home_in.properties == [Prop("goals", "home_goals", "int")]


@pytest.mark.parametrize("raw,message", [
    ({}, "no 'nodes'"),
    ({"nodes": [{"file": "a.csv", "label": "A"}]}, "missing 'key'"),
    ({"nodes": [{"file": "a.csv", "label": "A", "key": "id", "colour": 1}]}, "unknown option"),
    ({"nodes": [{"file": "a.csv", "label": "A", "key": "id", "mode": "upsert"}]}, "mode"),
    ({"relationships": [{"file": "a.csv", "type": "R", "from": {"label": "A"},
                         "to": {"label": "B", "key": "id"}}]}, "needs 'key'"),
])
def test_bad_configs(raw, message):
    with pytest.raises(SpecError, match=message):
        parse_config(raw)


def test_json_config(tmp_path):
    write_csv(tmp_path / "p.csv", "id,name\n1,Ann\n")
    (tmp_path / "map.json").write_text(json.dumps(
        {"nodes": [{"file": "p.csv", "label": "Person", "key": "id",
                    "properties": {"id": "int", "name": "str"}}]}))
    driver = FakeDriver()
    [stats] = Neo4jCsvLoader(driver).run(load_config_file(tmp_path / "map.json"))
    assert stats.rows_written == 1
    assert driver.graph.nodes == {"Person": [{"id": 1}]}


# --- loading ---------------------------------------------------------------------------------

def test_load_example_into_fake_graph():
    driver = FakeDriver()
    config = load_config_file(EXAMPLE)
    results = Neo4jCsvLoader(driver, database="football", batch_size=10).run(config)
    by_name = {s.name: s for s in results}

    graph = driver.graph
    assert len(graph.nodes["Team"]) == 26
    assert len(graph.nodes["Match"]) == 39
    assert by_name["(:Team)-[:HOME_IN]->(:Match)"].rows_written == 39
    assert all(s.rows_unmatched == 0 for s in results)
    assert set(driver.databases) == {"football"}

    constraints = [query for query, rows in graph.queries if rows is None]
    assert len(constraints) == 4 and all("CREATE CONSTRAINT" in c for c in constraints)

    # 39 match rows in batches of 10 -> 4 transactions
    match_batches = [rows for query, rows in graph.queries if rows and "(n:`Match`" in query]
    assert [len(b) for b in match_batches] == [10, 10, 10, 9]
    first = match_batches[0][0]
    assert first["k"] == {"id": "K1-0001"}
    assert first["p"]["round"] == 1 and isinstance(first["p"]["kickoff"], datetime)
    # unplayed matches have no score properties at all (not nulls)
    last = match_batches[-1][-1]
    assert "home_goals" not in last["p"] and "attendance" not in last["p"]


def test_unmatched_relationships_are_counted(tmp_path):
    nodes = write_csv(tmp_path / "people.csv", "id,name\n1,Ann\n2,Bob\n")
    knows = write_csv(tmp_path / "knows.csv", "src,dst,since\n1,2,2020\n1,9,2021\n")
    config = parse_config({
        "nodes": [{"file": str(nodes), "label": "Person", "key": "id",
                   "properties": {"id": "int", "name": "str"}}],
        "relationships": [{"file": str(knows), "type": "KNOWS",
                           "from": {"label": "Person", "key": "id", "column": "src", "type": "int"},
                           "to": {"label": "Person", "key": "id", "column": "dst", "type": "int"},
                           "properties": {"since": "int"}}],
    })
    driver = FakeDriver()
    _, rels = Neo4jCsvLoader(driver).run(config)
    assert (rels.rows_read, rels.rows_written, rels.rows_unmatched) == (2, 1, 1)
    assert driver.graph.rels == [("Person", {"id": 1}, "KNOWS", "Person", {"id": 2}, {"since": 2020})]


def test_all_columns_and_type_inference(tmp_path):
    path = write_csv(tmp_path / "s.csv", "name,capacity,roofed,zip\nArena,5000,true,01234\n")
    spec = NodeSpec(file=path, label="Stadium", key=[Prop("name", "name")],
                    all_columns=True, infer_types=True)
    driver = FakeDriver()
    Neo4jCsvLoader(driver).load(spec)
    [(query, rows)] = driver.graph.queries
    assert rows == [{"k": {"name": "Arena"},
                     "p": {"capacity": 5000, "roofed": True, "zip": "01234"}}]


def test_missing_column_reported_with_header(tmp_path):
    path = write_csv(tmp_path / "s.csv", "name,city\nA,B\n")
    spec = NodeSpec(file=path, label="Stadium", key=[Prop("name", "name")],
                    properties=[Prop("capacity", "capacity", "int")])
    with pytest.raises(CsvDataError, match=r"column\(s\) capacity not in header \(name, city\)"):
        Neo4jCsvLoader(FakeDriver()).load(spec)


def test_bad_value_fails_with_line_number(tmp_path):
    path = write_csv(tmp_path / "s.csv", "name,capacity\nA,100\nB,lots\n")
    spec = NodeSpec(file=path, label="Stadium", key=[Prop("name", "name")],
                    properties=[Prop("capacity", "capacity", "int")])
    with pytest.raises(CsvDataError, match=r"s\.csv:3: column 'capacity'"):
        Neo4jCsvLoader(FakeDriver()).load(spec)


def test_skip_bad_rows_and_empty_keys(tmp_path):
    path = write_csv(tmp_path / "s.csv", "name,capacity\nA,100\nB,lots\n,5\nC,\n")
    spec = NodeSpec(file=path, label="Stadium", key=[Prop("name", "name")],
                    properties=[Prop("capacity", "capacity", "int")],
                    csv=CsvOptions(on_error="skip"))
    driver = FakeDriver()
    stats = Neo4jCsvLoader(driver).load(spec)
    assert (stats.rows_read, stats.rows_skipped, stats.rows_written) == (4, 2, 2)
    assert driver.graph.nodes["Stadium"] == [{"name": "A"}, {"name": "C"}]


def test_semicolon_delimiter_and_bom(tmp_path):
    path = tmp_path / "s.csv"
    path.write_bytes("﻿name;capacity\nA;100\n".encode("utf-8"))
    spec = NodeSpec(file=path, label="Stadium", key=[Prop("name", "name")],
                    properties=[Prop("capacity", "capacity", "int")],
                    csv=CsvOptions(delimiter=";"))
    driver = FakeDriver()
    Neo4jCsvLoader(driver).load(spec)
    assert driver.graph.queries[0][1] == [{"k": {"name": "A"}, "p": {"capacity": 100}}]


def test_dry_run_needs_no_driver():
    stats = Neo4jCsvLoader(dry_run=True).run(load_config_file(EXAMPLE))
    assert sum(s.rows_written for s in stats) == 2 + 26 + 26 + 39 + 26 + 26 + 39 * 3
    with pytest.raises(ValueError):
        Neo4jCsvLoader()


# --- CLI -------------------------------------------------------------------------------------

def test_endpoint_arg():
    ep = parse_endpoint_arg("Team:code=home_code", {})
    assert (ep.label, ep.keys) == ("Team", [Prop("code", "home_code")])
    ep = parse_endpoint_arg("Person:id=src:int,org=org", {})
    assert ep.keys == [Prop("id", "src", "int"), Prop("org", "org")]
    assert parse_endpoint_arg("Person:id", {"id": "int"}).keys == [Prop("id", "id", "int")]
    with pytest.raises(SpecError):
        parse_endpoint_arg("Person", {})


def test_cli_dry_run(capsys):
    assert main(["load", str(EXAMPLE), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "MERGE (n:`Team` {`code`: row.k.`code`})" in out
    assert "dry run, nothing written" in out


def test_cli_nodes_and_rels(tmp_path, monkeypatch, capsys):
    people = write_csv(tmp_path / "people.csv", "id,name,age\n1,Ann,30\n2,Bob,41\n")
    knows = write_csv(tmp_path / "knows.csv", "src,dst\n1,2\n")
    driver = FakeDriver()
    driver.verify_connectivity = lambda: None
    driver.close = lambda: None
    import neo4j
    monkeypatch.setattr(neo4j.GraphDatabase, "driver", lambda uri, auth: driver)

    assert main(["nodes", str(people), "--label", "Person", "--key", "id",
                 "--type", "id=int", "--type", "age=int", "--password", "pw"]) == 0
    assert driver.graph.queries[-1][1][0] == {"k": {"id": 1}, "p": {"name": "Ann", "age": 30}}

    assert main(["rels", str(knows), "--rel-type", "KNOWS", "--from", "Person:id=src:int",
                 "--to", "Person:id=dst:int", "--password", "pw"]) == 0
    assert len(driver.graph.rels) == 1
    assert "written 1" in capsys.readouterr().out


def test_cli_requires_password(monkeypatch):
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    assert main(["load", str(EXAMPLE)]) == 2
