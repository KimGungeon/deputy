"""Scripted rehearsal answers, never copied to the live workspace.

These are not agent-generated fixes. They verify the acceptance oracle itself.
"""
ALPHA = '''import csv
import io
import re


def clean_name(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("empty name")
    return value.strip().lower()


def parse_count(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+", value.strip()):
        raise ValueError("invalid count")
    return int(value.strip())


def parse_csv(text):
    reader = csv.reader(io.StringIO(text), strict=True)
    if next(reader, None) != ["name", "count"]:
        raise ValueError("invalid header")
    result = []
    for row in reader:
        if not row:
            continue
        if len(row) != 2:
            raise ValueError("invalid row")
        result.append({"name": clean_name(row[0]), "count": parse_count(row[1])})
    return result


def combine(rows):
    totals = {}
    for row in rows:
        totals[row["name"]] = totals.get(row["name"], 0) + row["count"]
    return [{"name": name, "count": count} for name, count in totals.items()]
'''

BETA = '''import json


def summarize(rows):
    counts = [row["count"] for row in rows]
    return {"records": len(rows), "total": sum(counts), "maximum": max(counts, default=0)}


def top_names(rows, limit):
    if limit < 0:
        raise ValueError("negative limit")
    return [r["name"] for r in sorted(rows, key=lambda r: (-r["count"], r["name"]))[:limit]]


def render(summary):
    return json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\\n"


def from_csv(text):
    from alpha.normalize import parse_csv, combine
    return render(summarize(combine(parse_csv(text))))
'''
