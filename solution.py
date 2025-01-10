from typing import Dict, List, Any, Set, Tuple

class SemanticLayerEngine:
    """
    A semantic layer engine that translates high-level query definitions into SQL.
    This engine supports:
      - Metrics and dimensions defined in a semantic layer
      - Automatic table joins based on predefined relationships
      - Filtering, ordering, and limiting results
      - Time-based dimension processing (e.g., truncating dates to month/year)
    """

    def __init__(self, semantic_layer: Dict[str, Any]):
        """
        Initializes the engine with a given semantic layer definition.
        The semantic layer is expected to have:
          - metrics (list[dict])
          - dimensions (list[dict]) (optional)
          - joins (list[dict]) (optional)
        """
        self.semantic_layer = semantic_layer
        
        # Build lookup maps for metrics and dimensions by name
        self.metrics_map = {
            metric["name"]: metric
            for metric in semantic_layer.get("metrics", [])
        }
        self.dimensions_map = {
            dim["name"]: dim
            for dim in semantic_layer.get("dimensions", [])
        }
        self.joins = semantic_layer.get("joins", [])

    def generate_sql(self, query: Dict[str, Any]) -> str:
        """
        Generates a BigQuery-compatible SQL statement based on the query definition and semantic layer.
        Required query fields:
          - metrics: List[str] of metric names
        Optional query fields:
          - dimensions: List[str] of dimension names
          - filters: List[dict] of filters (field, operator, value)
          - order_by: dict with 'field' and optional 'direction'
          - limit: int
        """

        # Extract query details
        metrics = query.get("metrics", [])
        dimensions = query.get("dimensions", [])
        filters = query.get("filters", [])
        order_by = query.get("order_by")
        limit = query.get("limit")

        # Validate metrics
        if not metrics:
            raise ValueError("Query must contain at least one metric.")

        #Determine which tables are required
        required_tables = self._get_tables_for_query(metrics, dimensions, filters)
        #Identify a base table
        base_table = self._get_base_table(metrics)
        # Build SELECT expressions
        select_clause = self._build_select_clause(metrics, dimensions)
        #Build FROM + potential JOIN clauses
        from_and_joins_clause = self._build_from_and_joins(base_table, required_tables)
        #Build WHERE/HAVING filters
        where_conditions, having_conditions = self._split_filters_into_where_and_having(filters)
        #Build GROUP BY expressions
        group_by_expressions = self._build_group_by_expressions(dimensions)
        # Assemble everything into the final query
        sql_parts = []
        # SELECT ...
        sql_parts.append("SELECT " + ",\n       ".join(select_clause))
        # FROM ...
        sql_parts.append("FROM " + from_and_joins_clause[0])
        # JOIN ...
        if len(from_and_joins_clause) > 1:
            sql_parts.extend(from_and_joins_clause[1:])
        # WHERE ...
        if where_conditions:
            sql_parts.append("WHERE " + " AND ".join(where_conditions))
        # GROUP BY ...
        if group_by_expressions:
            sql_parts.append("GROUP BY " + ", ".join(group_by_expressions))
        # HAVING ...
        if having_conditions:
            sql_parts.append("HAVING " + " AND ".join(having_conditions))
        # ORDER BY ...
        if order_by:
            direction = order_by.get("direction", "ASC").upper()
            if direction not in ["ASC", "DESC"]:
                raise ValueError("Order by direction must be 'ASC' or 'DESC'.")
            order_field = order_by["field"]
            sql_parts.append(f"ORDER BY {order_field} {direction}")
        # LIMIT ...
        if limit is not None:
            if not isinstance(limit, int) or limit < 1:
                raise ValueError("Limit must be a positive integer.")
            sql_parts.append(f"LIMIT {limit}")

        return "\n".join(sql_parts)

    # ===============
    # HELPER METHODS
    # ===============

    def _lookup_field(self, field: str) -> Tuple[Dict[str, Any], str]:
        """
        Attempts to find whether 'field' corresponds to:
         - A dimension name in self.dimensions_map
         - A metric name in self.metrics_map
         - The raw 'sql' value of a dimension
         - The raw 'sql' value of a metric
        Returns (definition_dict, "dimension"/"metric") if found,
        else (None, None).
        """
        # dimension name
        if field in self.dimensions_map:
            return self.dimensions_map[field], "dimension"
        # metric name
        if field in self.metrics_map:
            return self.metrics_map[field], "metric"
        # if field matches a dimension's sql column
        for dim_def in self.dimensions_map.values():
            if dim_def["sql"] == field:
                return dim_def, "dimension"
        # if field matches a metric's sql expression
        for met_def in self.metrics_map.values():
            if met_def["sql"] == field:
                return met_def, "metric"
        
        return None, None

    def _get_tables_for_query(self, metrics: List[str], dimensions: List[str], filters: List[Dict[str, Any]]) -> Set[str]:
        """
        Looks up which tables are needed based on metrics, dimensions, and filters.
        """
        tables = set()

        # Metrics -> add table
        for m in metrics:
            if m not in self.metrics_map:
                raise ValueError(f"Unknown metric: {m}")
            tables.add(self.metrics_map[m]["table"])

        # Dimensions -> add table
        for d in dimensions:
            base_d = d.split("__")[0] # remove any time truncation
            if base_d not in self.dimensions_map:
                raise ValueError(f"Unknown dimension: {base_d}")
            tables.add(self.dimensions_map[base_d]["table"])

        # Filters -> dimension or metric or raw column
        for f in filters:
            field = f["field"].split("__")[0] 
            defn, defn_type = self._lookup_field(field)
            if defn and defn_type in ["dimension", "metric"]:
                tables.add(defn["table"])
            else:
                raise ValueError(f"Unknown field in filter: {f['field']}")

        return tables

    def _get_base_table(self, metrics: List[str]) -> str:
        """
        Returns the table associated with the first metric—used as the base in FROM.
        """
        first_metric = metrics[0]
        return self.metrics_map[first_metric]["table"]

    def _build_select_clause(self, metrics: List[str], dimensions: List[str]) -> List[str]:
        """
        Builds the list of SELECT expressions for metrics and dimensions.
        Each expression includes an alias with 'AS'.
        """
        select_expressions = []

        # Dimensions
        for d in dimensions:
            base_dim = d.split("__")[0]
            dim_def = self.dimensions_map[base_dim]
            dim_sql = self._process_time_dimension(d, dim_def["table"], dim_def["sql"])
            select_expressions.append(f"{dim_sql} AS {d}")

        # Metrics
        for m in metrics:
            metric_def = self.metrics_map[m]
            select_expressions.append(f"{metric_def['sql']} AS {m}")

        return select_expressions

    def _build_from_and_joins(self, base_table: str, required_tables: Set[str]) -> List[str]:
        """
        Builds a list where the first entry is the base table, and subsequent entries are JOIN clauses if needed.
        """
        if len(required_tables) <= 1:
            return [base_table]

        join_clauses = []
        processed_tables = {base_table}
        needed_tables = required_tables - processed_tables

        # attach each needed table via the configured joins
        while needed_tables:
            joined_something = False

            for join_def in self.joins:
                one_side = join_def["one"]
                many_side = join_def["many"]
                on_clause = join_def["join"]

                if one_side in processed_tables and many_side in needed_tables:
                    join_clauses.append(f"JOIN {many_side} ON {on_clause}")
                    processed_tables.add(many_side)
                    needed_tables.remove(many_side)
                    joined_something = True
                elif many_side in processed_tables and one_side in needed_tables:
                    join_clauses.append(f"JOIN {one_side} ON {on_clause}")
                    processed_tables.add(one_side)
                    needed_tables.remove(one_side)
                    joined_something = True

            if not joined_something:
                raise ValueError(
                    f"Cannot resolve joins for tables: {', '.join(needed_tables)}."
                )

        return [base_table] + join_clauses

    def _process_time_dimension(self, dim_name: str, table: str, raw_sql: str) -> str:
        """
        If the dimension ends in __week, __month, or __year, do DATE_TRUNC(...).
        Otherwise, just qualify the dimension as table.raw_sql.
        """
        if "__week" in dim_name:
            return f"DATE_TRUNC({table}.{raw_sql}, WEEK)"
        elif "__month" in dim_name:
            return f"DATE_TRUNC({table}.{raw_sql}, MONTH)"
        elif "__year" in dim_name:
            return f"DATE_TRUNC({table}.{raw_sql}, YEAR)"
        return f"{table}.{raw_sql}"

    def _split_filters_into_where_and_having(self, filters: List[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
        """
        Returns two lists: [where_conditions], [having_conditions]
        - if filter is on a dimension => goes to WHERE
        - if filter is on a metric => goes to HAVING
        - if filter references a dimension's raw column => treat as dimension
        """
        where_conditions = []
        having_conditions = []

        for f in filters:
            raw_field = f["field"]
            operator = f["operator"]
            value = f["value"]
            base_field = raw_field.split("__")[0]

            defn, defn_type = self._lookup_field(base_field)
            if not defn:
                raise ValueError(f"Unknown filter field '{raw_field}'")

            if defn_type == "metric":
                # Filter on a metric => HAVING
                condition = f"{defn['sql']} {operator} {self._format_value(value)}"
                having_conditions.append(condition)
            elif defn_type == "dimension":
                # Filter on a dimension => WHERE
                # raw table.column comparison, ignoring any date trunc
                # because filtering often needs exact column check.
                col = f"{defn['table']}.{defn['sql']}"
                condition = f"{col} {operator} {self._format_value(value)}"
                where_conditions.append(condition)
            else:
                raise ValueError(f"Unable to process filter for '{raw_field}'")

        return where_conditions, having_conditions

    def _build_group_by_expressions(self, dimensions: List[str]) -> List[str]:
        """
        For each dimension, returns the expression that should appear in GROUP BY.
        This typically matches the SELECT expression (minus the alias).
        - For time-based dimensions, replicate the DATE_TRUNC
        - For normal dimensions, just table.column
        """
        group_by_exps = []
        for d in dimensions:
            base_dim = d.split("__")[0]
            dim_def = self.dimensions_map[base_dim]

            if "__week" in d:
                group_by_exps.append(f"DATE_TRUNC({dim_def['table']}.{dim_def['sql']}, WEEK)")
            elif "__month" in d:
                group_by_exps.append(f"DATE_TRUNC({dim_def['table']}.{dim_def['sql']}, MONTH)")
            elif "__year" in d:
                group_by_exps.append(f"DATE_TRUNC({dim_def['table']}.{dim_def['sql']}, YEAR)")
            else:
                group_by_exps.append(f"{dim_def['table']}.{dim_def['sql']}")
        return group_by_exps

    def _format_value(self, value: Any) -> str:
        """
        Simple formatting of filter values. If it's a string, wrap in quotes.
        For list-like values (e.g. for IN), a comma-separated list in parentheses.
        """
        if isinstance(value, str):
            return f"'{value}'"
        elif isinstance(value, list):
            joined = ",".join(f"'{v}'" if isinstance(v, str) else str(v) for v in value)
            return f"({joined})"
        else:
            return str(value)


def process_query(semantic_layer: Dict[str, Any], query: Dict[str, Any]) -> str:
    """
    Function to generate SQL from a given semantic layer and a query.
    """
    engine = SemanticLayerEngine(semantic_layer)
    return engine.generate_sql(query)
