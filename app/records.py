"""公开目录收据，不把目录缺失解释为详情不存在。"""
import json
import sqlite3
from pathlib import Path

def save_catalog(path, items):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS catalog (id TEXT PRIMARY KEY, source TEXT NOT NULL, payload TEXT NOT NULL)')
        for item in items:
            db.execute('INSERT OR REPLACE INTO catalog VALUES (?, ?, ?)', (item['id'], item['source'], json.dumps(item, ensure_ascii=False)))
    return len(items)

def save_detail_entries(path, entries):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS detail_entries (visit_id INTEGER PRIMARY KEY, item_id TEXT NOT NULL, business_key TEXT NOT NULL, source TEXT NOT NULL, payload TEXT NOT NULL)')
        for entry in entries:
            if entry['catalog_fact']['identity'] != entry['id']:
                raise ValueError('catalog and detail identity mismatch')
            db.execute('INSERT INTO detail_entries (item_id, business_key, source, payload) VALUES (?, ?, ?, ?)',
                       (entry['id'], entry['detail_fact']['business_key'], entry['source'], json.dumps(entry, ensure_ascii=False)))
    return len(entries)

def read_detail_entries(path):
    with sqlite3.connect(path) as db:
        rows = db.execute('SELECT payload FROM detail_entries ORDER BY visit_id').fetchall()
    return [json.loads(row[0]) for row in rows]

def save_qualification_observation(path, cache_key, observation):
    """按 (来源, 业务, 精确地址) 键保存资格观察；同地址重跑覆盖自己的记录，
    不同地址键不同，互不共享。技术性失败的观察不入库。"""
    if observation.get('technical_error'):
        raise ValueError('technical-failure observations are not cached')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(observation)
    payload.pop('cache_hit', None)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS qualification_observations ('
                   'cache_key TEXT PRIMARY KEY, item_id TEXT NOT NULL, '
                   'address TEXT NOT NULL, source TEXT NOT NULL, '
                   'payload TEXT NOT NULL, observed_at TEXT NOT NULL)')
        db.execute('INSERT OR REPLACE INTO qualification_observations '
                   '(cache_key, item_id, address, source, payload, observed_at) '
                   'VALUES (?, ?, ?, ?, ?, ?)',
                   (cache_key, observation['id'], observation['address'],
                    observation['origin'], json.dumps(payload, ensure_ascii=False),
                    observation['observed_at']))
    return cache_key

def load_qualification_observation(path, cache_key):
    path = Path(path)
    if not path.exists():
        return None
    with sqlite3.connect(path) as db:
        row = db.execute('SELECT payload FROM qualification_observations '
                         'WHERE cache_key = ?', (cache_key,)).fetchone()
    if row is None:
        return None
    return json.loads(row[0])

def read_qualification_observations(path):
    path = Path(path)
    if not path.exists():
        return []
    with sqlite3.connect(path) as db:
        rows = db.execute('SELECT payload FROM qualification_observations '
                          'ORDER BY observed_at').fetchall()
    return [json.loads(row[0]) for row in rows]
