# neo4j_loader: upload CSV data into Neo4j

A small Python tool that turns CSV files into Neo4j nodes and relationships. It:

- maps columns to properties, with renames and types (`int`, `float`, `bool`, `date`,
  `datetime`, `time`, `list`, `list:int`, `auto`, …)
- writes in batches (`UNWIND $rows … MERGE`), one managed write transaction per batch, with
  the driver's automatic retry on transient errors
- upserts on a key (`mode: merge`, the default), or always inserts (`mode: create`)
- creates a uniqueness constraint per node key, so `MERGE` uses an index and duplicates are refused
- loads every node file before any relationship file, so relationship endpoints already exist
- reports rows read / written / skipped, and relationship rows whose start or end node wasn't found
- leaves empty cells unset (Neo4j doesn't store nulls), and quotes every label, type and
  property name, so names from a config can't inject Cypher
- has `--dry-run`, which reads and validates every file and prints the Cypher without connecting

## Install

```bash
pip install -r neo4j_loader/requirements.txt     # neo4j driver + PyYAML
export NEO4J_URI=neo4j://localhost:7687 NEO4J_USER=neo4j NEO4J_PASSWORD=secret
# optional: NEO4J_DATABASE=neo4j
```

To run a local server: `docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/secret123 neo4j:5`.

Run it from the repository root (`python -m neo4j_loader …`). Neo4j 5 is the target (4.4 works too).

## 1. Quick: one CSV file from the command line

```bash
# nodes: every column becomes a property (strings unless typed or --infer-types)
python -m neo4j_loader nodes people.csv --label Person --key id --type id=int --type age=int

# only some columns, plus an extra label
python -m neo4j_loader nodes people.csv --label Person --key id --properties id name \
  --extra-label Customer

# relationships between existing nodes: Label:property=column[:type]
python -m neo4j_loader rels follows.csv --rel-type FOLLOWS \
  --from Person:id=follower_id:int --to Person:id=followed_id:int --properties since --type since=date
```

## 2. Full graph: a mapping file

`examples/k_league.yaml` loads the sample K League data in `examples/data/` (leagues, stadiums,
teams, matches) into this graph:

```
(:Team:Club)-[:PLAYS_IN]->(:League)
(:Team)-[:HOME_GROUND]->(:Stadium)
(:Team)-[:HOME_IN {goals}]->(:Match)-[:PART_OF]->(:League)
(:Team)-[:AWAY_IN {goals}]->(:Match)
```

```bash
python -m neo4j_loader load neo4j_loader/examples/k_league.yaml --dry-run   # check first
python -m neo4j_loader load neo4j_loader/examples/k_league.yaml
```

A mapping file can be YAML or JSON:

```yaml
defaults:                 # all optional
  data_dir: data          # CSV paths are relative to this (itself relative to the mapping file)
  batch_size: 1000
  delimiter: ","
  encoding: utf-8-sig     # utf-8, also strips an Excel BOM; use cp949 / euc-kr for Korean Excel exports
  list_separator: ";"
  on_error: fail          # fail | skip (log bad rows and keep going)
  infer_types: false

nodes:
  - file: teams.csv
    label: Team
    labels: [Club]        # extra labels (optional)
    key: code             # or a list for a composite key: [league, code]
    mode: merge           # merge (default) | create
    constraint: true      # create a uniqueness constraint on the key (default)
    properties:           # omit to store every column (as str, or inferred with infer_types)
      code: str
      name: str
      founded: int
      colors: list        # "blue;white" -> ["blue", "white"]
      stadium_name: {column: stadium, type: str}   # rename a column
    all_columns: false    # true: also store the columns not listed above

relationships:
  - file: matches.csv
    type: HOME_IN
    from: {label: Team, key: code, column: home_code}          # match an existing node
    to: {label: Match, key: id, column: match_id, type: str}
    # composite: to: {label: Player, keys: {team: team_code, number: {column: shirt, type: int}}}
    key: [season]         # optional: merge on these too, so two nodes can have several of these rels
    properties:
      goals: {column: home_goals, type: int}
```

The endpoint `type` must match how the node key was stored: a key stored as `int` won't match
a string `"7"`. Rows that match no node are counted as "no matching node" and the CLI exits with
code 3, so check those first when relationships go missing.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | done |
| 1 | bad CSV data, or a connection / auth / Cypher error |
| 2 | bad arguments or mapping file, or no password |
| 3 | done, but some relationship rows had no matching start or end node |

## From Python

```python
from neo4j import GraphDatabase
from neo4j_loader import Neo4jCsvLoader, load_config_file

config = load_config_file("neo4j_loader/examples/k_league.yaml")
with GraphDatabase.driver("neo4j://localhost:7687", auth=("neo4j", "secret")) as driver:
    for stats in Neo4jCsvLoader(driver, database="neo4j", batch_size=config.batch_size).run(config):
        print(stats.summary())
```

## Tests

```bash
pytest neo4j_loader
```

The tests use a fake driver, so they need no Neo4j server.
