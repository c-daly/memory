import hashlib
import json
import pytest
import bounded_read
import index


@pytest.fixture
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMORY_VAULT_DIR', str(tmp_path))
    def add(name, text, description='A remembered fact', type='user', subject='user', path=None):
        rel = path or f'.memory/2026-09-18-{name}.md'
        entry = index.IndexEntry(name=name, type=type, subject=subject, path=rel, description=description)
        file = tmp_path / rel
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text)
        with (tmp_path/'MEMORY.md').open('a') as handle:
            handle.write(index._format_bullet(entry)+'\n')
    return tmp_path, add


def escaped_bytes(text):
    return len(json.dumps(text, ensure_ascii=False).encode())


def test_many_memories_page_without_losing_identity_or_writing(vault):
    root, add = vault
    for i in range(100):
        add(f'memory-{i:03}', 'body', description='Quoted "detail" \\ Irish é 😃 '*40)
    before = {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
    offset = 0; names = []
    while True:
        text = bounded_read.search(offset=offset, max_bytes=2048)
        assert escaped_bytes(text) <= 2048
        value = json.loads(text)
        names.extend(e['name'] for e in value['entries'])
        assert value['total_matches'] == 100
        assert all(e['source'].endswith(e['name']+'.md') for e in value['entries'])
        if not value['more']:break
        assert value['next_offset'] > offset
        offset = value['next_offset']
    assert len(names) == len(set(names)) == 100
    assert before == {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


def test_search_filters_and_relevance(vault):
    _, add = vault
    add('one','a','GPU scientific simulation',type='project',subject='earthsim')
    add('two','b','GPU setup',type='feedback',subject='user')
    add('three','c','French lessons',type='user',subject='user')
    result = json.loads(bounded_read.search(query='scientific GPU', type='project', subject='EARTHSIM'))
    assert [e['name'] for e in result['entries']] == ['one']
    assert json.loads(bounded_read.search(query='nonexistent'))['total_matches'] == 0


def test_unicode_body_pagination_round_trips_and_has_source(vault):
    _, add = vault
    original = 'Quoted "hello" \\\nSpiddal é 😃\n'*600
    add('profile', original)
    offset = 0; revision = ''; pages = []
    while True:
        text = bounded_read.read('profile', 'user', offset=offset, revision=revision, max_bytes=1024)
        assert escaped_bytes(text) <= 1024
        value = json.loads(text);pages.append(value['text'])
        assert value['source'] == '.memory/2026-09-18-profile.md'
        if not value['more']:break
        assert value['next_offset'] > offset
        offset, revision = value['next_offset'], value['revision']
    assert ''.join(pages) == original


def test_changed_memory_does_not_silently_mix_pages(vault):
    root, add = vault
    add('profile','x'*4000)
    first = json.loads(bounded_read.read('profile','user',max_bytes=1024))
    (root/first['source']).write_text('Changed contents')
    with pytest.raises(ValueError,match='changed between pages'):
        bounded_read.read('profile','user',offset=first['next_offset'],revision=first['revision'])
    fresh = json.loads(bounded_read.read('profile','user'))
    assert fresh['text'] == 'Changed contents' and fresh['revision'] != first['revision']


def test_missing_index_never_rebuilds_or_creates_files(vault):
    root, _ = vault
    with pytest.raises(ValueError,match='no automatic rebuild'):
        bounded_read.search()
    assert list(root.iterdir()) == []


def test_index_path_cannot_escape_vault(vault):
    root, _ = vault
    (root/'MEMORY.md').write_text(index._format_bullet(index.IndexEntry('escape','user','user','../outside.md','x'))+'\n')
    with pytest.raises(ValueError,match='outside the vault'):
        bounded_read.read('escape','user')


def test_invalid_budgets_and_oversized_identity_are_explicit(vault):
    _, add = vault
    add('ok','text')
    with pytest.raises(ValueError):bounded_read.search(max_bytes=100000)
    with pytest.raises(ValueError):bounded_read.read('ok','user',offset=-1)
    root, _ = vault
    (root/'MEMORY.md').write_text(index._format_bullet(index.IndexEntry('z'*3000,'user','user','some.md','desc'))+'\n')
    with pytest.raises(ValueError,match='identity cannot fit'):
        bounded_read.search(max_bytes=1024)
