"""Bounded, read-only MCP retrieval from the existing vault index.
No alternate store, automatic index rebuild, embeddings, or memory writes.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import index
from config import resolve_vault_root


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def _size(value):
    # Count the escaped string as it appears inside a model tool-result message.
    return len(json.dumps(_json(value), ensure_ascii=False).encode('utf-8'))


def _budget(max_bytes, offset):
    if not 1024 <= max_bytes <= 8192 or offset < 0:
        raise ValueError('max_bytes must be 1024..8192; offset must be nonnegative')


def _entries():
    root = resolve_vault_root().resolve()
    entries = index.read(root)
    if not entries:
        raise ValueError('Memory index is missing or empty; no automatic rebuild was performed')
    return root, entries


def _fit_text(value, key, text, budget):
    value[key] = ''
    if _size(value) > budget:
        raise ValueError('Memory identity metadata exceeds the requested byte budget')
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        value[key] = text[:middle]
        if _size(value) <= budget:
            low = middle
        else:
            high = middle - 1
    value[key] = text[:low]
    return low


def search(query='', type=None, subject=None, offset=0, limit=6, max_bytes=4096):
    _budget(max_bytes, offset)
    if not 1 <= limit <= 20 or len(query) > 512:
        raise ValueError('limit must be 1..20; query must be at most 512 characters')
    _, entries = _entries()
    terms = re.findall(r'\w+', query.casefold())
    matches = []
    for entry in entries:
        if type and entry.type != type or subject and entry.subject.casefold() != subject.casefold():
            continue
        corpus = f'{entry.name} {entry.subject} {entry.description}'.casefold()
        score = sum(term in corpus for term in terms)
        if terms and not score:
            continue
        matches.append((score, entry))
    # Relevance first; newest recorded entry first for a core user-memory brief.
    matches.sort(key=lambda row: (row[0], Path(row[1].path).name[:10], row[1].name, row[1].type), reverse=True)
    result = {'entries': [], 'total_matches': len(matches), 'offset': offset,
              'next_offset': offset, 'more': offset < len(matches),
              'notice': 'Index summaries only; read entries for details. Dates record notes, not live project status.'}
    for _, entry in matches[offset:offset+limit]:
        item = {'name': entry.name, 'type': entry.type, 'subject': entry.subject,
                'source': entry.path, 'description': entry.description[:360]}
        if len(entry.description) > 360:
            item['description_truncated'] = True
        result['entries'].append(item)
        result['next_offset'] += 1
        result['more'] = result['next_offset'] < len(matches)
        if _size(result) > max_bytes:
            result['entries'].pop()
            result['next_offset'] -= 1
            result['more'] = True
            if not result['entries']:
                raise ValueError('One memory identity cannot fit; increase max_bytes')
            break
    return _json(result)


def read(name, type, offset=0, max_bytes=4096, revision=''):
    _budget(max_bytes, offset)
    root, entries = _entries()
    found = next((e for e in entries if e.name == name and e.type == type), None)
    if found is None:
        return _json({'found': False, 'notice': 'No indexed memory matches that name and type.'})
    path = (root / found.path).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Indexed memory path is outside the vault')
    with path.open('rb') as handle:
        raw = handle.read(2*1024*1024+1)
    if len(raw) > 2*1024*1024:
        raise ValueError('Memory entry exceeds the 2 MiB read limit')
    digest = hashlib.sha256(raw).hexdigest()
    if revision and revision != digest:
        raise ValueError('Memory changed between pages; restart at offset 0')
    text = raw.decode('utf-8')
    if offset > len(text):
        raise ValueError('Offset is beyond this memory; restart at offset 0')
    result = {'found': True, 'name': found.name, 'type': found.type, 'subject': found.subject,
              'source': found.path, 'revision': digest, 'offset': offset,
              'next_offset': len(text), 'more': False, 'text': ''}
    count = _fit_text(result, 'text', text[offset:], max_bytes)
    result['next_offset'] = offset + count
    result['more'] = result['next_offset'] < len(text)
    return _json(result)
