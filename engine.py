import re

OPERATORS_BY_TYPE = {
    "string":   ["==", "!=", "in", "!in", "contains", "!contains", "has", "!has",
                 "startswith", "endswith", "matches regex"],
    "datetime": ["ago()", ">", "<", ">=", "<=", "between"],
    "int":      ["==", "!=", "in", "!in", ">", "<", ">=", "<=", "between"],
    "bool":     ["==", "!="],
    "dynamic":  ["contains", "has", "!has", "array_length() >"],
}

_AGO_PATTERN = re.compile(r"^\d+[mhdw]$")


def get_operators_for_type(dtype):
    return OPERATORS_BY_TYPE.get(dtype, OPERATORS_BY_TYPE["string"])


def _escape_kql_string(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _format_value(dtype, operator, value):
    if not value.strip():
        return None

    if dtype == "bool":
        return value.lower()

    if dtype == "int":
        if operator in ("in", "!in"):
            items = [p.strip() for p in value.split(",")]
            return f"({', '.join(items)})"
        if operator == "between":
            parts = [p.strip() for p in value.split("..")]
            if len(parts) == 2:
                return f"{parts[0]} .. {parts[1]}"
            return None
        return value.strip()

    if dtype == "datetime":
        if operator == "ago()":
            v = value.strip()
            if _AGO_PATTERN.match(v):
                return f"ago({v})"
            return None
        if operator == "between":
            parts = [p.strip() for p in value.split("..")]
            if len(parts) == 2:
                return f"datetime({parts[0]}) .. datetime({parts[1]})"
            return None
        return f"datetime({value.strip()})"

    if dtype == "string":
        if operator in ("in", "!in"):
            items = [f'"{_escape_kql_string(p.strip())}"' for p in value.split(",")]
            return f"({', '.join(items)})"
        if operator == "matches regex":
            return f'@"{_escape_kql_string(value)}"'
        return f'"{_escape_kql_string(value)}"'

    if dtype == "dynamic":
        if operator == "array_length() >":
            return value.strip()
        return f'"{_escape_kql_string(value)}"'

    return f'"{_escape_kql_string(value)}"'


def _build_filter_line(col, operator, value, dtype):
    formatted = _format_value(dtype, operator, value)
    if formatted is None:
        return None

    if dtype == "dynamic" and operator == "array_length() >":
        return f"| where array_length({col}) > {formatted}"

    if dtype == "datetime" and operator == "ago()":
        return f"| where {col} > {formatted}"

    if operator == "between":
        return f"| where {col} between ({formatted})"

    return f"| where {col} {operator} {formatted}"


def _get_time_column(table):
    try:
        from schemas import TABLE_SCHEMAS
        cols = TABLE_SCHEMAS.get(table, {}).get("columns", {})
        for candidate in ("Timestamp", "TimeGenerated", "timestamp"):
            if candidate in cols:
                return candidate
    except ImportError:
        pass
    return "Timestamp"


def build_query(table, filters=None, time_range=None, project_cols=None,
                sort_col=None, sort_dir="desc", limit=None):
    lines = [table]

    if time_range:
        v = time_range.strip()
        if _AGO_PATTERN.match(v):
            ts_col = _get_time_column(table)
            lines.append(f"| where {ts_col} > ago({v})")

    if filters:
        for f in filters:
            col = f.get("column", "")
            op = f.get("operator", "")
            val = f.get("value", "")
            dtype = f.get("dtype", "string")
            if col and op and val.strip():
                line = _build_filter_line(col, op, val, dtype)
                if line:
                    lines.append(line)

    if project_cols:
        lines.append(f"| project {', '.join(project_cols)}")

    if sort_col:
        lines.append(f"| sort by {sort_col} {sort_dir}")

    if limit and limit > 0:
        lines.append(f"| take {limit}")

    return "\n".join(lines)
