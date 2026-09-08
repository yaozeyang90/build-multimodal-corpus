#!/usr/bin/env python3
"""Portable canonical-corpus tooling. Standard library only; no OCR/API calls."""
import argparse
import collections
import hashlib
import json
import math
import mimetypes
from pathlib import Path, PurePosixPath
import re
import sqlite3
import struct
import sys
import tempfile
import zlib

VERSION = 'msc-skill-0.1'
KEYS = dict(textbooks='textbook_id', source_documents='document_id',
            parse_runs='parse_run_id', pages='page_id', parse_records='parse_record_id',
            structure_nodes='node_id', node_members='membership_id', blocks='block_id',
            block_fragments='fragment_id', media_assets='asset_id',
            media_occurrences='occurrence_id', spans='span_id', structural_links='link_id',
            annotation_records='annotation_id', qc_records='qc_id',
            revisions='revision_id', table_cells='cell_id',
            continuation_candidates='candidate_id')
AUX = dict(book_catalog='book_alias', file_blobs='sha256', file_entries='path',
           asset_files='asset_id', page_files='page_id')
TYPES = {'block': 'blocks', 'node': 'structure_nodes', 'fragment': 'block_fragments',
         'media_occurrence': 'media_occurrences', 'span': 'spans'}


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def qi(name):
    return '"' + name.replace('"', '""') + '"'


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, obj):
    with Path(path).open('x', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def relative(name):
    if not isinstance(name, str) or not name or '\\' in name or ':' in name:
        raise ValueError(f'Unsafe relative path: {name!r}')
    p = PurePosixPath(name)
    if p.is_absolute() or any(x in ('', '.', '..') for x in name.split('/')):
        raise ValueError(f'Unsafe relative path: {name!r}')
    return p


def safe_file(root, name):
    p = root
    for part in relative(name).parts:
        p = p / part
        if p.is_symlink():
            raise ValueError(f'Symlink not allowed: {name}')
    if not p.is_file() or not p.resolve().is_relative_to(root.resolve()):
        raise ValueError(f'Missing/escaped file: {name}')
    return p


def read_tables(book):
    tables = {}
    for name in KEYS:
        path = safe_file(book, f'data/{name}.jsonl')
        rows = []
        for i, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f'{name}:{i}: expected JSON object')
            rows.append(row)
        tables[name] = rows
    return tables


def check_tables(t):
    errors = []
    idx = {}
    def check(condition, message):
        if not condition:
            errors.append(message)
    for name, key in KEYS.items():
        idx[name] = {}
        for row in t[name]:
            value = row.get(key)
            check(isinstance(value, str) and bool(value), f'{name}: missing/string ID')
            if not isinstance(value, str):
                continue
            check(value not in idx[name], f'{name}: duplicate {value}')
            idx[name][value] = row
    if errors:
        return errors
    def ref(name, ident, context, book=None):
        row = idx[name].get(ident)
        check(row is not None, f'{context}: missing {name}/{ident}')
        if row is not None and book is not None and 'textbook_id' in row:
            check(row['textbook_id'] == book, f'{context}: cross-book reference')
        return row
    def pos(value):
        if not isinstance(value, dict):
            return None
        p, y = value.get('physical_page'), value.get('y')
        if not isinstance(p, int) or p < 1 or not isinstance(y, (int, float)) or not 0 <= y <= 1:
            return None
        return p, y
    for name, rows in t.items():
        for row in rows:
            if 'textbook_id' in row:
                ref('textbooks', row['textbook_id'], name)
            if name in {'pages', 'structure_nodes', 'blocks', 'media_assets', 'media_occurrences'}:
                check(row.get('textbook_id') in idx['textbooks'], f'{name}: missing book identity')
    for a in t['media_assets']:
        check(isinstance(a.get('sha256'), str) and bool(re.fullmatch(r'[0-9a-f]{64}', a['sha256'])), f'{a["asset_id"]}: missing/invalid asset SHA-256')
    nodes, blocks = idx['structure_nodes'], idx['blocks']
    for book in idx['textbooks']:
        roots = [n for n in nodes.values() if n.get('textbook_id') == book and n.get('parent_id') is None]
        check(len(roots) == 1 and roots[0].get('node_kind') == 'book', f'{book}: expected one book root')
    for nid, node in nodes.items():
        if node.get('parent_id'):
            ref('structure_nodes', node['parent_id'], nid, node.get('textbook_id'))
        seen, current = set(), nid
        while current in nodes:
            if current in seen:
                check(False, f'{nid}: tree cycle')
                break
            seen.add(current)
            current = nodes[current].get('parent_id')
        start, end = pos(node.get('boundary_start')), pos(node.get('boundary_end_exclusive'))
        if node.get('boundary_start') is not None or node.get('boundary_end_exclusive') is not None:
            check(start is not None and end is not None and start < end, f'{nid}: invalid interval')
        parent = nodes.get(node.get('parent_id'), {})
        ps, pe = pos(parent.get('boundary_start')), pos(parent.get('boundary_end_exclusive'))
        if all(x is not None for x in (start, end, ps, pe)):
            check(ps <= start < end <= pe, f'{nid}: outside parent interval')
        for bid in node.get('heading_block_ids', []):
            b = ref('blocks', bid, nid, node.get('textbook_id'))
            if b:
                check(b.get('owner_node_id') == nid, f'{nid}: heading not owned by node')
    seen_pages = set()
    for page in t['pages']:
        pair = page.get('textbook_id'), page.get('physical_page')
        check(isinstance(pair[1], int) and pair[1] > 0, f'{page["page_id"]}: invalid physical page')
        check(pair not in seen_pages, f'{pair}: duplicate physical page')
        seen_pages.add(pair)
    covered = set()
    for bid, block in blocks.items():
        ref('structure_nodes', block.get('owner_node_id'), bid, block.get('textbook_id'))
        check((block.get('textbook_id'), block.get('physical_page')) in seen_pages, f'{bid}: missing physical page')
        for rid in block.get('source_record_ids', []):
            ref('parse_records', rid, bid, block.get('textbook_id'))
            covered.add(rid)
    for rid in idx['parse_records']:
        check(rid in covered, f'{rid}: unmapped parse record')
    members = collections.Counter()
    for m in t['node_members']:
        parent = ref('structure_nodes', m.get('node_id'), m['membership_id'])
        table = {'node': 'structure_nodes', 'block': 'blocks'}.get(m.get('member_type'))
        check(table is not None, f'{m["membership_id"]}: invalid member type')
        if table:
            child = ref(table, m.get('member_id'), m['membership_id'], (parent or {}).get('textbook_id'))
            members[m['member_type'], m.get('member_id')] += 1
            if child:
                owner = child.get('parent_id' if table == 'structure_nodes' else 'owner_node_id')
                check(owner == m.get('node_id'), f'{m["membership_id"]}: wrong member owner')
    for bid in blocks:
        check(members['block', bid] == 1, f'{bid}: expected one direct membership')
    for nid, node in nodes.items():
        check(members['node', nid] == (1 if node.get('parent_id') else 0), f'{nid}: node membership mismatch')
    for table in ('block_fragments', 'spans'):
        for f in t[table]:
            fid = f[KEYS[table]]
            b = ref('blocks', f.get('block_id'), fid)
            if table == 'block_fragments':
                ref('pages', f.get('page_id'), fid, (b or {}).get('textbook_id'))
                box = f.get('bbox')
                check(box is None or (isinstance(box, list) and len(box) == 4
                      and all(isinstance(x, (float, int)) and math.isfinite(x) and 0 <= x <= 1 for x in box)
                      and box[0] < box[2] and box[1] < box[3]), f'{fid}: invalid bbox')
            if f.get('text_start') is not None or f.get('text_end') is not None:
                start, end = f.get('text_start'), f.get('text_end')
                layer = f.get('text_layer', 'text_raw')
                text = (b or {}).get(layer)
                check(isinstance(text, str) and isinstance(start, int) and isinstance(end, int)
                      and 0 <= start <= end <= len(text), f'{fid}: invalid codepoint span')
    for o in t['media_occurrences']:
        ref('blocks', o.get('block_id'), o['occurrence_id'], o.get('textbook_id'))
        ref('media_assets', o.get('asset_id'), o['occurrence_id'], o.get('textbook_id'))
        if o.get('parent_occurrence_id'):
            ref('media_occurrences', o['parent_occurrence_id'], o['occurrence_id'], o.get('textbook_id'))
        seen, current = set(), o['occurrence_id']
        while current in idx['media_occurrences']:
            if current in seen:
                check(False, f'{o["occurrence_id"]}: occurrence cycle')
                break
            seen.add(current)
            current = idx['media_occurrences'][current].get('parent_occurrence_id')
    for link in t['structural_links']:
        for side in ('source', 'target'):
            typ, ident = link.get(side + '_type'), link.get(side + '_id')
            if side == 'target' and ident is None:
                check(link.get('review_status') in ('unresolved', 'needs_adjudication'), f'{link["link_id"]}: null target must be unresolved')
                continue
            table = TYPES.get(typ)
            check(table is not None, f'{link["link_id"]}: invalid {side} type')
            if table:
                ref(table, ident, link['link_id'], link.get('textbook_id'))
        for ident in link.get('candidate_target_ids', []):
            # This release's candidate lists are figure occurrences, not semantic entities.
            ref('media_occurrences', ident, link['link_id'], link.get('textbook_id'))
        if link.get('relation_type') == 'caption_of':
            check(link.get('source_type') == 'block', f'{link["link_id"]}: caption source must be block')
            source = blocks.get(link.get('source_id'), {})
            check(source.get('block_type') == 'caption', f'{link["link_id"]}: source not caption')
            if link.get('target_id'):
                check(link.get('target_type') == 'media_occurrence', f'{link["link_id"]}: invalid caption target')
    for cell in t['table_cells']:
        b = ref('blocks', cell.get('table_block_id'), cell['cell_id'])
        check((b or {}).get('block_type') == 'table', f'{cell["cell_id"]}: cell outside table')
    return errors


def encode(value):
    return dumps(value) if isinstance(value, (dict, list)) else value


def create_table(c, name, pk, rows):
    cols = list(dict.fromkeys([pk] + [k for r in rows for k in r]))
    c.execute(f'CREATE TABLE {qi(name)} (' + ','.join(qi(k) + ' TEXT' + (' PRIMARY KEY NOT NULL' if k == pk else '') for k in cols) + ')')
    for row in rows:
        c.execute(f'INSERT INTO {qi(name)} VALUES ({",".join("?" for _ in cols)})', [encode(row.get(k)) for k in cols])


def readonly(path):
    c = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    c.row_factory = sqlite3.Row
    return c


def db_tables(c):
    result = {}
    # Only structured JSON fields are decoded; original text beginning with '[' is untouched.
    json_fields = {'source_record_ids', 'heading_block_ids', 'boundary_start', 'boundary_end_exclusive',
                   'bbox', 'alternate_paths', 'candidate_target_ids', 'fragment_ids', 'evidence_refs'}
    int_fields = {'physical_page', 'text_start', 'text_end'}
    for name in KEYS:
        result[name] = []
        for r in c.execute(f'SELECT * FROM {qi(name)}'):
            row = dict(r)
            for key in json_fields & row.keys():
                if row[key] is not None:
                    row[key] = json.loads(row[key])
            for key in int_fields & row.keys():
                if row[key] is not None:
                    row[key] = int(row[key])
            result[name].append(row)
    return result


def stage_output(out):
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError(f'Refuse overwrite: {out}')
    out.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='.' + out.name + '.partial-', dir=out.parent))
    return out, work / out.name


def publish(temp, out):
    # Exclusive destination creation, including filesystems without hardlink support.
    with temp.open('rb') as src, out.open('xb') as dst:
        while data := src.read(1024 * 1024):
            dst.write(data)
    temp.unlink()
    temp.parent.rmdir()


def pack(manifest, output):
    manifest = Path(manifest).resolve()
    cfg = read_json(manifest)
    if not cfg.get('books') or not cfg.get('release_id'):
        raise ValueError('Manifest needs release_id and nonempty books')
    tables = {k: [] for k in KEYS}
    books, aliases = [], set()
    for spec in cfg['books']:
        alias = spec['alias']
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', alias) or alias in aliases:
            raise ValueError(f'Duplicate/unsafe alias: {alias}')
        aliases.add(alias)
        relative(spec['directory'])
        book = manifest.parent / spec['directory']
        if book.is_symlink() or not book.resolve().is_relative_to(manifest.parent):
            raise ValueError('Book directory escapes manifest root')
        bt = read_tables(book)
        if len(bt['textbooks']) != 1:
            raise ValueError('Each book directory needs exactly one textbook')
        for key in tables:
            tables[key].extend(bt[key])
        declared = set()
        for entry in spec['files']:
            name = entry['path']
            if name in declared:
                raise ValueError(f'Duplicate file path: {name}')
            safe_file(book, name)
            declared.add(name)
        required = []
        for a in bt['media_assets']:
            required.extend([a['path']] + a.get('alternate_paths', []))
        required += [p['preview_path'] for p in bt['pages'] if p.get('preview_path')]
        required += [d['path'] for d in bt['source_documents'] if d.get('path')]
        if set(required) - declared:
            raise ValueError(f'Unlisted required files: {sorted(set(required) - declared)}')
        books.append((spec, book, bt))
    errors = check_tables(tables)
    if errors:
        raise ValueError(dumps(errors[:30]))
    out, temp = stage_output(output)
    c = sqlite3.connect(temp, uri=True)
    try:
        for name, key in KEYS.items():
            create_table(c, name, key, tables[name])
        c.executescript('''
        CREATE TABLE collection_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE book_catalog(book_alias TEXT PRIMARY KEY,textbook_id TEXT UNIQUE,series TEXT,volume TEXT,path_prefix TEXT,component_release_id TEXT);
        CREATE TABLE file_blobs(sha256 TEXT PRIMARY KEY,bytes INTEGER,mime_type TEXT,content BLOB NOT NULL);
        CREATE TABLE file_entries(path TEXT PRIMARY KEY,book_alias TEXT,role TEXT,sha256 TEXT NOT NULL REFERENCES file_blobs(sha256));
        CREATE TABLE asset_files(asset_id TEXT PRIMARY KEY,path TEXT NOT NULL REFERENCES file_entries(path));
        CREATE TABLE page_files(page_id TEXT PRIMARY KEY,path TEXT NOT NULL REFERENCES file_entries(path));
        ''')
        for spec, root, bt in books:
            tb, prefix = bt['textbooks'][0], 'books/' + spec['alias'] + '/'
            c.execute('INSERT INTO book_catalog VALUES (?,?,?,?,?,?)', (spec['alias'], tb['textbook_id'], tb.get('series'), tb.get('volume'), prefix, cfg['release_id']))
            for entry in spec['files']:
                p = safe_file(root, entry['path'])
                raw = p.read_bytes()
                sha = digest(raw)
                if entry.get('sha256') and entry['sha256'] != sha:
                    raise ValueError(f'Manifest hash mismatch: {entry["path"]}')
                c.execute('INSERT OR IGNORE INTO file_blobs VALUES (?,?,?,?)', (sha, len(raw), mimetypes.guess_type(p.name)[0] or 'application/octet-stream', raw))
                c.execute('INSERT INTO file_entries VALUES (?,?,?,?)', (prefix + entry['path'], spec['alias'], entry.get('role', 'source'), sha))
            for a in bt['media_assets']:
                c.execute('INSERT INTO asset_files VALUES (?,?)', (a['asset_id'], prefix + a['path']))
            for p in bt['pages']:
                if p.get('preview_path'):
                    c.execute('INSERT INTO page_files VALUES (?,?)', (p['page_id'], prefix + p['preview_path']))
        metadata = dict(schema_version=VERSION, release_id=cfg['release_id'],
                        candidate_only=True, semantic_accuracy=None, human_gold=False,
                        manifest_sha256=digest(manifest.read_bytes()),
                        file_scope='explicit manifest whitelist; external inventory coverage requires separate check')
        for key, value in metadata.items():
            c.execute('INSERT INTO collection_metadata VALUES (?,?)', (key, dumps(value)))
        c.commit()
    finally:
        c.close()
    result = validate(temp)
    if not result['passed']:
        raise ValueError(dumps(result))
    publish(temp, out)
    result['file'] = str(out)
    return result


def validate(path):
    errors = []
    with readonly(path) as c:
        if c.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            errors.append('SQLite integrity check failed')
        t = db_tables(c)
        errors.extend(check_tables(t))
        entries = {r['path']: dict(r) for r in c.execute('SELECT * FROM file_entries')}
        hashes = set()
        for row in c.execute('SELECT * FROM file_blobs'):
            hashes.add(row['sha256'])
            if digest(row['content']) != row['sha256'] or len(row['content']) != row['bytes']:
                errors.append('BLOB hash/size mismatch: ' + row['sha256'])
        for name, entry in entries.items():
            relative(name)
            if entry['sha256'] not in hashes:
                errors.append('Missing BLOB: ' + name)
        catalog = {r['textbook_id']: dict(r) for r in c.execute('SELECT * FROM book_catalog')}
        if set(catalog) != {b['textbook_id'] for b in t['textbooks']}:
            errors.append('Book catalog coverage mismatch')
        af = dict(c.execute('SELECT asset_id,path FROM asset_files'))
        pf = dict(c.execute('SELECT page_id,path FROM page_files'))
        for table, field, mapping, key in [('media_assets', 'path', af, 'asset_id'), ('pages', 'preview_path', pf, 'page_id'), ('source_documents', 'path', None, 'document_id')]:
            for row in t[table]:
                if not row.get(field):
                    if table == 'media_assets':
                        errors.append('Asset missing path: ' + row[key])
                    continue
                prefix = catalog.get(row.get('textbook_id'), {}).get('path_prefix', '')
                expected = prefix + str(relative(row[field]))
                entry = entries.get(expected)
                if not entry or (mapping is not None and mapping.get(row[key]) != expected):
                    errors.append('Missing/mismatched file mapping: ' + row[key])
                if row.get('sha256') and entry and entry['sha256'] != row['sha256']:
                    errors.append('Object hash mismatch: ' + row[key])
                if table == 'media_assets':
                    for alternate in row.get('alternate_paths') or []:
                        ae = entries.get(prefix + str(relative(alternate)))
                        if not ae or not entry or ae['sha256'] != entry['sha256']:
                            errors.append('Alternate asset mismatch: ' + row[key])
        result = dict(file=str(path), passed=not errors, errors=errors,
                      counts={k: len(v) for k, v in t.items()}, embedded_blobs_checked=len(hashes),
                      unresolved_captions=sum(l.get('relation_type') == 'caption_of' and l.get('target_id') is None for l in t['structural_links']),
                      validation_type='technical_integrity_not_semantic_accuracy')
    return result


def merge(inputs, output, release_id):
    if len(inputs) < 2:
        raise ValueError('Merge requires at least two components')
    for path in inputs:
        r = validate(path)
        if not r['passed']:
            raise ValueError(dumps(r))
        with readonly(path) as source:
            v = source.execute("SELECT value FROM collection_metadata WHERE key='schema_version'").fetchone()
            if v is None or json.loads(v[0]) != VERSION:
                raise ValueError('Unsupported schema; explicit migration required')
    out, temp = stage_output(output)
    c = sqlite3.connect(temp, uri=True)
    checks = []
    try:
        with readonly(inputs[0]) as source:
            source.backup(c)
        for path in inputs[1:]:
            c.execute('ATTACH DATABASE ? AS component', (Path(path).resolve().as_uri() + '?mode=ro',))
            for table in list(KEYS) + list(AUX):
                destcols = [r[1] for r in c.execute(f'PRAGMA main.table_info({qi(table)})')]
                srccols = [r[1] for r in c.execute(f'PRAGMA component.table_info({qi(table)})')]
                for col in srccols:
                    if col not in destcols:
                        c.execute(f'ALTER TABLE {qi(table)} ADD COLUMN {qi(col)} TEXT')
                cols = ','.join(map(qi, srccols))
                verb = 'INSERT OR IGNORE' if table == 'file_blobs' else 'INSERT'
                c.execute(f'{verb} INTO main.{qi(table)} ({cols}) SELECT {cols} FROM component.{qi(table)}')
            c.commit()
            c.execute('DETACH DATABASE component')
        # Every component's original columns and values must survive exactly.
        expected = collections.Counter()
        for path in inputs:
            c.execute('ATTACH DATABASE ? AS component', (Path(path).resolve().as_uri() + '?mode=ro',))
            for table in list(KEYS) + list(AUX):
                cols = ','.join(qi(r[1]) for r in c.execute(f'PRAGMA component.table_info({qi(table)})'))
                missing = c.execute(f'SELECT count(*) FROM (SELECT {cols} FROM component.{qi(table)} EXCEPT SELECT {cols} FROM main.{qi(table)})').fetchone()[0]
                if missing:
                    raise ValueError(f'Exact-union failure: {table}')
                if table != 'file_blobs':
                    expected[table] += c.execute(f'SELECT count(*) FROM component.{qi(table)}').fetchone()[0]
            checks.append(dict(component=Path(path).name, original_columns_exact=True))
            c.execute('DETACH DATABASE component')
        for table, count in expected.items():
            if c.execute(f'SELECT count(*) FROM {qi(table)}').fetchone()[0] != count:
                raise ValueError('Union count mismatch: ' + table)
        metas = []
        for path in inputs:
            with readonly(path) as src:
                metas.append(dict(src.execute('SELECT key,value FROM collection_metadata')))
        c.execute('DELETE FROM collection_metadata')
        for key, value in dict(schema_version=VERSION, release_id=release_id, components=metas,
                               exact_union_checks=checks, candidate_only=True, semantic_accuracy=None, human_gold=False).items():
            c.execute('INSERT INTO collection_metadata VALUES (?,?)', (key, dumps(value)))
        c.commit()
    finally:
        c.close()
    result = validate(temp)
    if not result['passed']:
        raise ValueError(dumps(result))
    publish(temp, out)
    result.update(file=str(out), exact_union_checks=checks)
    return result


def search(path, query, limit):
    if not 1 <= limit <= 1000:
        raise ValueError('limit must be 1..1000')
    # instr gives literal substring semantics, including one-character Chinese and %/_ characters.
    with readonly(path) as c:
        return [dict(r) for r in c.execute('SELECT b.block_id,b.textbook_id,t.series,t.volume,b.physical_page,b.owner_node_id,b.text_clean FROM blocks b JOIN textbooks t USING(textbook_id) WHERE instr(b.text_clean,?)>0 LIMIT ?', (query, limit))]


def extract(path, asset_id, output):
    with readonly(path) as c:
        row = c.execute('SELECT b.content,b.sha256 FROM asset_files a JOIN file_entries e ON a.path=e.path JOIN file_blobs b ON b.sha256=e.sha256 WHERE a.asset_id=?', (asset_id,)).fetchone()
        if row is None:
            raise ValueError('Unknown asset ID')
        if digest(row['content']) != row['sha256']:
            raise ValueError('Asset hash mismatch')
        with Path(output).open('xb') as f:
            f.write(row['content'])
    return dict(file=str(output), sha256=row['sha256'])


def export(path, output):
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    with readonly(path) as c:
        t = db_tables(c)
        errors = check_tables(t)
        if errors:
            raise ValueError(dumps(errors[:30]))
        nodes = {n['node_id']: n for n in t['structure_nodes']}
        blocks = {b['block_id']: b for b in t['blocks']}
        members = collections.defaultdict(list)
        for m in t['node_members']:
            members[m['node_id']].append(m)
        occ = collections.defaultdict(list)
        for o in t['media_occurrences']:
            occ[o['block_id']].append(o)
        media = out / 'media'
        media.mkdir()
        names = {}
        for a in t['media_assets']:
            ext = Path(a['path']).suffix.lower()
            ext = ext if re.fullmatch(r'\.[a-z0-9]{1,8}', ext) else '.bin'
            # Filenames never derived from unconstrained object IDs.
            filename = digest(a['asset_id'].encode()) + ext
            extract(path, a['asset_id'], media / filename)
            names[a['asset_id']] = 'media/' + filename
        for root in (n for n in nodes.values() if n.get('parent_id') is None):
            lines = ['<!-- Candidate structural view; source text is not HTML-escaped. Do not render untrusted HTML. -->', '']
            def visit(nid, depth):
                n = nodes[nid]
                title = ' '.join(str(x) for x in (n.get('raw_column_label'), n.get('raw_title')) if x)
                lines.extend(['#' * min(depth, 6) + ' ' + (title or n['node_kind']), '', '<!-- node: ' + nid.replace('--', '') + ' -->', ''])
                for m in sorted(members[nid], key=lambda r: str(r.get('order_key', ''))):
                    if m['member_type'] == 'node':
                        visit(m['member_id'], depth + 1)
                    else:
                        b = blocks[m['member_id']]
                        lines.extend(['<!-- block: ' + b['block_id'].replace('--', '') + ' -->', b.get('text_clean') or '', ''])
                        for o in occ[b['block_id']]:
                            lines.extend(['![source image](' + names[o['asset_id']] + ')', ''])
            visit(root['node_id'], 1)
            filename = digest(root['textbook_id'].encode())[:20] + '.md'
            with (out / filename).open('x', encoding='utf-8') as f:
                f.write('\n'.join(lines))
        write_json(out / 'caption_links.json', t['structural_links'])
        write_json(out / 'asset_index.json', names)
    return dict(directory=str(out), books=len(t['textbooks']), images=len(names), note='Markdown preserves member order; caption truth remains in caption_links.json, not inferred from adjacency')


def demo(output):
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    # Original synthetic PNG, generated without external assets or copyrighted text.
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    raw = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 8, 8, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress((b'\x00' + b'\x20\x80\xc0' * 8) * 8)) + chunk(b'IEND', b'')
    specs = []
    for alias, stage in [('junior_demo', '初中'), ('senior_demo', '高中')]:
        book = root / alias
        (book / 'data').mkdir(parents=True)
        (book / 'images').mkdir()
        (book / 'images/demo.png').write_bytes(raw)
        (book / 'images/unreferenced.png').write_bytes(raw)
        tables = {k: [] for k in KEYS}
        def ident(x):
            return alias + ':' + x
        tid = ident('book')
        tables['textbooks'] = [dict(textbook_id=tid, stage=stage, series='合成示例版', volume='示例册', synthetic=True)]
        tables['pages'] = [dict(page_id=ident('page1'), textbook_id=tid, physical_page=1, printed_page_raw='1', preview_path='images/demo.png')]
        tables['parse_runs'] = [dict(parse_run_id=ident('parse'), textbook_id=tid, parser='synthetic_fixture')]
        parents = [('root', None, 'book', '合成教材'), ('chapter', 'root', 'organizational_unit', '第一单元 示例'), ('activity', 'chapter', 'pedagogical_container', '观察示例图')]
        for local, parent, kind, title in parents:
            tables['structure_nodes'].append(dict(node_id=ident(local), textbook_id=tid, parent_id=ident(parent) if parent else None, node_kind=kind, level_role='unit' if local == 'chapter' else None, raw_title=title, raw_column_label='活动' if local == 'activity' else None, heading_block_ids=[], boundary_start=dict(physical_page=1, y=0), boundary_end_exclusive=dict(physical_page=2, y=0), review_status='unreviewed'))
            if parent:
                tables['node_members'].append(dict(membership_id=ident('member-' + local), node_id=ident(parent), member_type='node', member_id=ident(local), order_key='000', order_status='display_only'))
        for i, (kind, text) in enumerate([('paragraph', '这是完全合成的材料：地球🌍。'), ('figure', ''), ('caption', '图1 示例色块')]):
            bid, rid, fid = ident('b' + str(i)), ident('r' + str(i)), ident('f' + str(i))
            tables['parse_records'].append(dict(parse_record_id=rid, textbook_id=tid, physical_page=1, payload=dict(type=kind, text=text)))
            tables['blocks'].append(dict(block_id=bid, textbook_id=tid, owner_node_id=ident('activity'), block_type=kind, text_raw=text, text_clean=text, text_normalized=text, source_record_ids=[rid], physical_page=1, review_status='unreviewed'))
            tables['block_fragments'].append(dict(fragment_id=fid, block_id=bid, page_id=ident('page1'), bbox=[0.1, 0.1 + i * 0.2, 0.9, 0.25 + i * 0.2], text_layer='text_raw', text_start=0, text_end=len(text)))
            tables['node_members'].append(dict(membership_id=ident('member-b' + str(i)), node_id=ident('activity'), member_type='block', member_id=bid, order_key=str(i), order_status='display_only'))
        tables['media_assets'] = [dict(asset_id=ident('asset'), textbook_id=tid, path='images/demo.png', sha256=digest(raw), alternate_paths=['images/unreferenced.png'])]
        tables['media_occurrences'] = [dict(occurrence_id=ident('occ'), textbook_id=tid, block_id=ident('b1'), asset_id=ident('asset'), parent_occurrence_id=None, review_status='unreviewed')]
        tables['structural_links'] = [dict(link_id=ident('caption'), textbook_id=tid, relation_type='caption_of', source_type='block', source_id=ident('b2'), target_type=None, target_id=None, candidate_target_ids=[ident('occ')], evidence_refs=[ident('f2')], evidence_note='Synthetic unresolved candidate; no semantic verification', review_status='unresolved')]
        tables['annotation_records'] = [dict(annotation_id=ident('ann'), textbook_id=tid, object_type='structural_links', object_id=ident('caption'), producer_type='rule_engine', model_id=None, run_id=ident('run'), schema_version=VERSION, review_status='unreviewed')]
        for name, rows in tables.items():
            with (book / 'data' / (name + '.jsonl')).open('x', encoding='utf-8') as f:
                for row in rows:
                    f.write(dumps(row) + '\n')
        specs.append(dict(alias=alias, directory=alias, files=[dict(path='images/demo.png', role='synthetic_image'), dict(path='images/unreferenced.png', role='unreferenced_image')]))
        write_json(root / (stage + '.json'), dict(release_id=alias + '-v01', books=[specs[-1]]))
    write_json(root / 'all.json', dict(release_id='synthetic-all-v01', books=specs))
    return dict(directory=str(root), synthetic_only=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    d = sub.add_parser('demo', help='Create two synthetic books and manifests in a NEW directory')
    d.add_argument('--out', required=True)
    d = sub.add_parser('pack', help='Validate canonical JSONL and embed explicitly listed files')
    d.add_argument('--manifest', required=True)
    d.add_argument('--out', required=True)
    d = sub.add_parser('validate', help='Read-only full technical audit')
    d.add_argument('database')
    d = sub.add_parser('merge', help='Exact union of compatible, disjoint components')
    d.add_argument('databases', nargs='+')
    d.add_argument('--out', required=True)
    d.add_argument('--release-id', required=True)
    d = sub.add_parser('search', help='Read-only literal substring search')
    d.add_argument('database')
    d.add_argument('query')
    d.add_argument('--limit', type=int, default=30)
    d = sub.add_parser('extract', help='Extract one embedded image without opening a PDF')
    d.add_argument('database')
    d.add_argument('asset_id')
    d.add_argument('--out', required=True)
    d = sub.add_parser('export', help='Export structural Markdown plus all assets to a NEW directory')
    d.add_argument('database')
    d.add_argument('--out', required=True)
    args = p.parse_args()
    try:
        if args.command == 'demo': result = demo(args.out)
        elif args.command == 'pack': result = pack(args.manifest, args.out)
        elif args.command == 'validate': result = validate(args.database)
        elif args.command == 'merge': result = merge(args.databases, args.out, args.release_id)
        elif args.command == 'search': result = search(args.database, args.query, args.limit)
        elif args.command == 'extract': result = extract(args.database, args.asset_id, args.out)
        elif args.command == 'export': result = export(args.database, args.out)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if isinstance(result, dict) and result.get('passed') is False:
            return 1
        return 0
    except (ValueError, OSError, sqlite3.Error, KeyError, TypeError) as exc:
        print(dumps(dict(passed=False, error=str(exc))), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
