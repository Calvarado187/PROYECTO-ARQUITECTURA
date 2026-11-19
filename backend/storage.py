"""SQL transaccional y colas persistentes. El modo local usa dos motores reales."""
import dbm
import dbm.dumb
import json
import socket
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse
from .domain import BusinessError, thermal_state, utcnow


SCHEMA = [
    '''CREATE TABLE IF NOT EXISTS devices (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, site TEXT NOT NULL,
        minimum DOUBLE PRECISION NOT NULL, maximum DOUBLE PRECISION NOT NULL,
        token_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
        last_at TEXT, last_temperature DOUBLE PRECISION, state TEXT NOT NULL DEFAULT 'SIN DATOS',
        CHECK(minimum < maximum))''',
    '''CREATE TABLE IF NOT EXISTS readings (
        event_id TEXT PRIMARY KEY, device_id TEXT NOT NULL REFERENCES devices(id),
        temperature DOUBLE PRECISION NOT NULL, observed_at TEXT NOT NULL,
        received_at TEXT NOT NULL)''',
    'CREATE INDEX IF NOT EXISTS idx_readings_device_time ON readings(device_id, observed_at)',
    '''CREATE TABLE IF NOT EXISTS alerts (
        id TEXT PRIMARY KEY, device_id TEXT NOT NULL REFERENCES devices(id),
        kind TEXT NOT NULL, temperature DOUBLE PRECISION NOT NULL,
        opened_at TEXT NOT NULL, resolved_at TEXT, acknowledged_at TEXT)''',
    'CREATE INDEX IF NOT EXISTS idx_alerts_open ON alerts(device_id, resolved_at)',
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_alert ON alerts(device_id) WHERE resolved_at IS NULL",
]


class SQLRepository:
    def __init__(self, url):
        self.postgres = url.startswith('postgresql://')
        self.url = url
        if not self.postgres:
            Path(url).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            if not self.postgres:
                db.execute('PRAGMA journal_mode=WAL')
            for statement in SCHEMA:
                db.execute(statement)

    @contextmanager
    def connection(self):
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row
            db = psycopg.connect(self.url, row_factory=dict_row, connect_timeout=3)
        else:
            db = sqlite3.connect(self.url, timeout=5)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def execute(self, db, sql, args=()):
        return db.execute(sql.replace('?', '%s') if self.postgres else sql, args)

    def create_device(self, values, token_hash):
        identifier = str(uuid.uuid4())
        with self.connection() as db:
            self.execute(db, 'INSERT INTO devices(id,name,site,minimum,maximum,token_hash) VALUES(?,?,?,?,?,?)', (identifier, *values, token_hash))
        return self.device(identifier)

    def device(self, identifier):
        with self.connection() as db:
            row = self.execute(db, 'SELECT * FROM devices WHERE id=?', (identifier,)).fetchone()
            return dict(row) if row else None

    def devices(self):
        with self.connection() as db:
            return [dict(r) for r in self.execute(db, 'SELECT id,name,site,minimum,maximum,active,last_at,last_temperature,state FROM devices ORDER BY name LIMIT 1000').fetchall()]

    def process(self, event):
        with self.connection() as db:
            if not self.postgres:
                db.execute('BEGIN IMMEDIATE')
            row = self.execute(db, 'SELECT * FROM devices WHERE id=?' + (' FOR UPDATE' if self.postgres else ''), (event['device_id'],)).fetchone()
            if row is None:
                return False
            inserted = self.execute(db, 'INSERT INTO readings(event_id,device_id,temperature,observed_at,received_at) VALUES(?,?,?,?,?) ON CONFLICT(event_id) DO NOTHING', (event['event_id'], event['device_id'], event['temperature'], event['observed_at'], event['received_at'])).rowcount
            if not inserted:
                return False
            # Las lecturas atrasadas quedan en el histórico, sin revertir el estado actual.
            if row['last_at'] and event['observed_at'] <= row['last_at']:
                return True
            state = thermal_state(event['temperature'], row['minimum'], row['maximum'])
            opened = self.execute(db, 'SELECT * FROM alerts WHERE device_id=? AND resolved_at IS NULL', (row['id'],)).fetchone()
            if opened and opened['kind'] != state:
                self.execute(db, 'UPDATE alerts SET resolved_at=? WHERE id=?', (event['observed_at'], opened['id']))
                opened = None
            if state != 'NORMAL' and not opened:
                self.execute(db, 'INSERT INTO alerts(id,device_id,kind,temperature,opened_at) VALUES(?,?,?,?,?)', (str(uuid.uuid4()), row['id'], state, event['temperature'], event['observed_at']))
            self.execute(db, 'UPDATE devices SET last_at=?,last_temperature=?,state=? WHERE id=?', (event['observed_at'], event['temperature'], state, row['id']))
            return True

    def alerts(self, limit=100, offset=0):
        with self.connection() as db:
            return [dict(r) for r in self.execute(db, 'SELECT a.*,d.name AS device_name FROM alerts a JOIN devices d ON d.id=a.device_id ORDER BY opened_at DESC,id LIMIT ? OFFSET ?', (limit, offset)).fetchall()]

    def acknowledge(self, identifier):
        with self.connection() as db:
            return self.execute(db, 'UPDATE alerts SET acknowledged_at=COALESCE(acknowledged_at,?) WHERE id=?', (utcnow(), identifier)).rowcount > 0

    def readings(self, identifier, limit=100, offset=0):
        with self.connection() as db:
            return [dict(r) for r in self.execute(db, 'SELECT * FROM readings WHERE device_id=? ORDER BY observed_at DESC,event_id LIMIT ? OFFSET ?', (identifier, limit, offset)).fetchall()]

    def summary(self):
        with self.connection() as db:
            return {key: self.execute(db, sql).fetchone()['n'] for key, sql in {
                'devices': 'SELECT COUNT(*) AS n FROM devices',
                'readings': 'SELECT COUNT(*) AS n FROM readings',
                'open_alerts': 'SELECT COUNT(*) AS n FROM alerts WHERE resolved_at IS NULL',
            }.items()}


class LocalQueue:
    """Almacén DBM clave-valor persistente. Un proceso, protegido por mutex."""
    def __init__(self, path, capacity=10000):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = dbm.dumb.open(path, 'c')
        self.lock = threading.Lock()
        self.capacity = capacity

    def enqueue(self, event):
        with self.lock:
            if len(self.db) >= self.capacity:
                raise BusinessError('Cola llena. Reintente con el mismo event_id.', 503)
            key = str(uuid.uuid4())
            self.db[key] = json.dumps(event)
            self.sync()
            return key

    def sync(self):
        if hasattr(self.db, 'sync'):
            self.db.sync()

    def peek(self):
        with self.lock:
            keys = list(self.db.keys())
            # DBM no conserva el orden; received_at define el orden local.
            if not keys:
                return None
            items = [(k, json.loads(self.db[k])) for k in keys]
            key, event = min(items, key=lambda pair: pair[1]['received_at'])
            return key.decode(), event

    def ack(self, key):
        with self.lock:
            if key.encode() in self.db:
                del self.db[key]
                self.sync()

    def size(self):
        with self.lock:
            return len(self.db)

    def healthy(self):
        self.size()
        return True

    def close(self):
        self.db.close()


class RedisQueue:
    """Adaptador RESP2 mínimo: conexiones cortas y timeout; sin dependencia Python."""
    KEY = 'frioalerta:ingress'
    SCRIPT = "if redis.call('XLEN',KEYS[1]) >= tonumber(ARGV[1]) then return false end return redis.call('XADD',KEYS[1],'*','payload',ARGV[2])"

    def __init__(self, url, capacity=10000):
        self.url = urlparse(url)
        self.capacity = capacity

    def command(self, *parts):
        def send(sock, values):
            payload = b'*' + str(len(values)).encode() + b'\r\n'
            for item in values:
                data = str(item).encode()
                payload += b'$' + str(len(data)).encode() + b'\r\n' + data + b'\r\n'
            sock.sendall(payload)

        def read(stream):
            line = stream.readline()
            if not line:
                raise ConnectionError('Redis desconectado')
            prefix, body = line[:1], line[1:-2]
            if prefix == b'-':
                raise ConnectionError(body.decode())
            if prefix == b'+':
                return body.decode()
            if prefix == b':':
                return int(body)
            size = int(body)
            if size < 0:
                return None
            if prefix == b'*':
                return [read(stream) for _ in range(size)]
            data = stream.read(size)
            stream.read(2)
            return data.decode()

        with socket.create_connection((self.url.hostname, self.url.port or 6379), timeout=2) as sock:
            stream = sock.makefile('rb')
            if self.url.password:
                send(sock, ('AUTH', self.url.password))
                read(stream)
            send(sock, parts)
            return read(stream)

    def enqueue(self, event):
        key = self.command('EVAL', self.SCRIPT, 1, self.KEY, self.capacity, json.dumps(event))
        if key is None:
            raise BusinessError('Cola llena. Reintente con el mismo event_id.', 503)
        return key

    def peek(self):
        items = self.command('XRANGE', self.KEY, '-', '+', 'COUNT', 1)
        return (items[0][0], json.loads(items[0][1][1])) if items else None

    def ack(self, key):
        self.command('XDEL', self.KEY, key)

    def size(self):
        return self.command('XLEN', self.KEY)

    def healthy(self):
        return self.command('PING') == 'PONG'


