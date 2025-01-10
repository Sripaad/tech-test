# Semantic Layer Engine

This project contains a SemanticLayerEngine class that generates BigQuery SQL statements from a semantic layer definition and a user query (both provided as JSON objects).

## How It Works

### Semantic Layer

Defines metrics (e.g., SUM() or COUNT()) and dimensions (columns used for grouping or filtering). Optionally includes join configurations if data spans multiple tables.

### Query

Specifies:
    - metrics: Which aggregations to select.
    - dimensions: Fields to group by.
    - filters: Conditions on dimensions or metrics.
    - order_by and limit.

### Output

A complete BigQuery SQL string, including:
    - SELECT (with aggregates and columns)
    - FROM and JOIN
    - WHERE and HAVING
    - GROUP BY
    - Optional ORDER BY and LIMIT

### Useage

Run with `poetry run python sql_runner.py`. This runs the tests queries mentioned in the notion-site.

----------------------------------------------------------------------------------------------------------------------------------------------------------------
# Below is the original README file.
----------------------------------------------------------------------------------------------------------------------------------------------------------------

# Fluent Software Engineering Tech Test Tools

## `sql_runner.py`

Use this function to run a SQL snippet on BigQuery

### Setup

You will need to add a `.env` file with:

* `DEFAULT_DATASET` - the BigQuery dataset you want to run queries on
* `SERVICE_ACCOUNT_JSON` - the JSON key for the BigQuery service account that has permissions to run jobs

Install dependencies with poetry:

1. Run `poetry install`

### Usage

Either run with `poetry run python sql_runner.py`, or import into your code