"""Upload CSV files into Neo4j as nodes and relationships.

Library use::

    from neo4j import GraphDatabase
    from neo4j_loader import Neo4jCsvLoader, load_config_file

    config = load_config_file("mapping.yaml")
    with GraphDatabase.driver("neo4j://localhost:7687", auth=("neo4j", "secret")) as driver:
        for stats in Neo4jCsvLoader(driver, batch_size=config.batch_size).run(config):
            print(stats.summary())
"""
from .loader import CsvDataError, LoadStats, Neo4jCsvLoader, node_query, rel_query
from .spec import (Endpoint, LoadConfig, NodeSpec, Prop, RelSpec, SpecError, load_config_file,
                   parse_config)

__all__ = [
    "CsvDataError", "Endpoint", "LoadConfig", "LoadStats", "Neo4jCsvLoader", "NodeSpec", "Prop",
    "RelSpec", "SpecError", "load_config_file", "node_query", "parse_config", "rel_query",
]
