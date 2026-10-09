#!/usr/bin/env python3
"""Apply only the generated issuer delta, with execution metadata in the job summary."""
import re
import sqlite3
import sys
from d1_client import ROOT, execute, issuer_id, usage


def validate(sql, issuer):
    # Parse statement boundaries with SQLite so quotes/newlines in official data
    # cannot disguise another statement. Only the builder's exact shapes are allowed.
    statements, buffer = [], ''
    for ch in sql:
        buffer += ch
        if ch == ';' and sqlite3.complete_statement(buffer):
            clean = re.sub(r'^--[^\n]*\n', '', buffer, flags=re.MULTILINE).strip()
            if clean:
                statements.append(clean)
            buffer = ''
    if buffer.strip():
        raise ValueError('Incomplete generated SQL')
    target = "'" + issuer + "'"
    for statement in statements:
        if re.fullmatch(r"DELETE FROM (stores|reference_stores|store_raw) WHERE issuer_id=" + re.escape(target) + r" AND store_id='(?:[^']|'')*';", statement):
            continue
        match = re.fullmatch(r'INSERT INTO (stores|reference_stores|store_raw|issuer_state|issuer_search_config) \(([^)]+)\) VALUES \((.*)\) ON CONFLICT\(issuer_id(?:,store_id)?\) DO UPDATE SET (.*);', statement, flags=re.S)
        if not match or not match[2].startswith('issuer_id,') or not match[3].startswith(target + ','):
            raise ValueError('SQL outside selected issuer delta')
        # No nested queries, expressions or external table access in VALUES/SET.
        unquoted = re.sub(r"'(?:[^']|'')*'", "'literal'", match[3])
        if not re.fullmatch(r"(?:'literal'|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)(?:,(?:'literal'|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?))*", unquoted):
            raise ValueError('Unexpected SQL values')
        assignments = match[4].split(',')
        if any(not re.fullmatch(r'([a-z_]+)=excluded\.\1', x) or x.startswith('issuer_id=') or x.startswith('store_id=') for x in assignments):
            raise ValueError('Unexpected SQL assignment')
    if not statements:
        raise ValueError('Empty sync')


def main():
    issuer = issuer_id(sys.argv[1])
    path = ROOT / 'cloudflare' / 'generated' / f'sync_{issuer}.sql'
    validate(path.read_text(), issuer)
    usage('sync:' + issuer, execute('--file', str(path)))


if __name__ == '__main__':
    main()
