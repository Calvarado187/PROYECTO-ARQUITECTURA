import json
import os
import tempfile
import threading
import unittest
import uuid
import io
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from backend.application import Service
from backend.domain import BusinessError, Reading, thermal_state
from backend.storage import LocalQueue, SQLRepository
from backend.server import BoundedServer, Handler


class SystemTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = SQLRepository(self.tmp.name + '/test.sqlite')
        self.queue = LocalQueue(self.tmp.name + '/events', 100)
        self.service = Service(self.repo, self.queue)
        registered = self.service.register({'name': 'Cámara 1', 'site': 'Bodega', 'minimum': 2, 'maximum': 8})
        self.device = registered['device']['id']
        self.key = registered['device_token']

    def tearDown(self):
        self.queue.close()
        self.tmp.cleanup()

    def event(self, temperature=5, seconds=0):
        return {'event_id': str(uuid.uuid4()), 'device_id': self.device, 'temperature': temperature, 'observed_at': (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()}

    def submit(self, temperature, seconds=0):
        self.service.ingest(self.event(temperature, seconds), self.key)
        self.service.process_one()

    def test_thresholds_inclusive(self):
        self.assertEqual(thermal_state(2, 2, 8), 'NORMAL')
        self.assertEqual(thermal_state(8, 2, 8), 'NORMAL')
        self.assertEqual(thermal_state(9, 2, 8), 'ALTA')
        self.assertEqual(thermal_state(1, 2, 8), 'BAJA')

    def test_invalid_values_and_dates(self):
        for value in (float('nan'), float('inf'), True, 101):
            with self.assertRaises(BusinessError):
                Reading.parse(self.event(value))
        for seconds in (600, -90000):
            with self.assertRaises(BusinessError):
                Reading.parse(self.event(5, seconds))
        value = self.event(); value['observed_at'] = '2026-01-01'
        with self.assertRaises(BusinessError):
            Reading.parse(value)

    def test_registration_validation(self):
        with self.assertRaises(BusinessError):
            self.service.register({'name': '', 'site': 'x', 'minimum': 8, 'maximum': 2})

    def test_invalid_device_key(self):
        with self.assertRaises(BusinessError) as error:
            self.service.ingest(self.event(), 'invalid')
        self.assertEqual(error.exception.status, 401)
        self.assertEqual(self.queue.size(), 0)

    def test_alert_lifecycle_and_ack(self):
        self.submit(12)
        alert = self.repo.alerts()[0]
        self.assertTrue(self.repo.acknowledge(alert['id']))
        self.assertTrue(self.repo.acknowledge(alert['id']))
        self.submit(13, 1)
        self.assertEqual(len(self.repo.alerts()), 1)
        self.submit(5, 2)
        self.assertIsNotNone(self.repo.alerts()[0]['resolved_at'])
        self.assertIsNotNone(self.repo.alerts()[0]['acknowledged_at'])
        self.submit(1, 3)
        self.assertEqual(self.repo.summary()['open_alerts'], 1)
        self.assertEqual(len(self.repo.alerts()), 2)

    def test_out_of_order_does_not_reopen(self):
        self.submit(5)
        self.submit(12, -60)
        self.assertEqual(self.repo.summary()['readings'], 2)
        self.assertEqual(self.repo.summary()['open_alerts'], 0)

    def test_duplicate_event_is_idempotent(self):
        event = self.event(12)
        for _ in range(2):
            self.service.ingest(event, self.key)
            self.service.process_one()
        self.assertEqual(self.repo.summary()['readings'], 1)
        self.assertEqual(self.repo.summary()['open_alerts'], 1)

    def test_commit_then_ack_crash_recovery(self):
        self.service.ingest(self.event(12), self.key)
        _, event = self.queue.peek()
        self.repo.process(event)  # Simula caída tras commit y antes de eliminar de la cola.
        self.queue.close()
        self.queue = LocalQueue(self.tmp.name + '/events', 100)
        self.service.queue = self.queue
        self.service.process_one()
        self.assertEqual(self.queue.size(), 0)
        self.assertEqual(self.repo.summary()['readings'], 1)

    def test_storage_failure_keeps_event(self):
        self.service.ingest(self.event(), self.key)
        process = self.repo.process
        def fail(_):
            raise ConnectionError('SQL no disponible')
        self.repo.process = fail
        with self.assertRaises(ConnectionError):
            self.service.process_one()
        self.assertEqual(self.queue.size(), 1)
        self.repo.process = process
        self.service.process_one()
        self.assertEqual(self.queue.size(), 0)

    def test_full_queue_rejects_without_discard(self):
        self.queue.capacity = 1
        self.service.ingest(self.event(), self.key)
        with self.assertRaises(BusinessError) as error:
            self.service.ingest(self.event(), self.key)
        self.assertEqual(error.exception.status, 503)
        self.assertEqual(self.queue.size(), 1)

    def test_rate_limit(self):
        self.service.rate_limit = 1
        self.service.ingest(self.event(), self.key)
        with self.assertRaises(BusinessError) as error:
            self.service.ingest(self.event(), self.key)
        self.assertEqual(error.exception.status, 429)

    def test_concurrent_ingestion(self):
        with ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(lambda _: self.service.ingest(self.event(), self.key), range(40)))
        while self.service.process_one():
            pass
        self.assertEqual(self.repo.summary()['readings'], 40)

    def test_http_authorization_validation_and_frontend(self):
        server = BoundedServer(('127.0.0.1', 0), Handler, self.service, 'admin', 'reader')
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        def call(path, token=None, body=None, headers=None):
            h = headers or {}
            if token:
                h['Authorization'] = 'Bearer ' + token
            request = Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=h)
            try:
                with urlopen(request) as response:
                    return response.status, response.read()
            except HTTPError as error:
                return error.code, error.read()
        try:
            try:
                self.assertEqual(call('/')[0], 200)
            except URLError as error:
                if getattr(error.reason, 'winerror', None) == 10013:
                    self.skipTest('El entorno prohíbe conexiones TCP locales; cubierta aparte la adaptación HTTP en memoria.')
                raise
            self.assertEqual(call('/app.js')[0], 200)
            self.assertEqual(call('/api/v1/devices')[0], 401)
            self.assertEqual(call('/api/v1/devices', 'reader')[0], 200)
            self.assertEqual(call('/api/v1/devices', 'reader', {})[0], 401)
            self.assertEqual(call('/api/v1/alerts?limit=999', 'admin')[0], 422)
            self.assertEqual(call('/api/v1/telemetry', body=self.event(), headers={'X-Device-Key': self.key})[0], 202)
            self.service.process_one()
            status, data = call('/api/v1/summary', 'admin')
            self.assertEqual(json.loads(data)['readings'], 1)
            self.assertEqual(call('/api/v1/alerts/no-existe/ack', 'admin', {})[0], 404)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_http_wire_in_memory(self):
        """Ejecuta el parser HTTP y las rutas reales sin depender de permisos TCP."""
        class FakeSocket:
            def __init__(self, request):
                self.input = io.BytesIO(request)
                self.output = bytearray()
            def makefile(self, *args): return self.input
            def sendall(self, value): self.output.extend(value)
            def settimeout(self, value): pass
        class Context:
            service = self.service
            admin_token = 'admin'
            integration_token = 'reader'
        def request(path, method='GET', token='admin', body=None, extra=''):
            payload = json.dumps(body).encode() if body is not None else b''
            wire = (f'{method} {path} HTTP/1.0\r\nAuthorization: Bearer {token}\r\nContent-Length: {len(payload)}\r\n{extra}\r\n').encode() + payload
            connection = FakeSocket(wire)
            Handler(connection, ('127.0.0.1', 0), Context())
            header, data = bytes(connection.output).split(b'\r\n\r\n', 1)
            return int(header.split()[1]), data
        self.assertEqual(request('/')[0], 200)
        self.assertEqual(request('/styles.css')[0], 200)
        self.assertEqual(request('/api/v1/devices', token='bad')[0], 401)
        self.assertEqual(request('/api/v1/devices', token='reader')[0], 200)
        self.assertEqual(request('/api/v1/devices', 'POST', 'reader', {})[0], 401)
        self.assertEqual(request('/api/v1/devices', 'POST', 'admin', {'name':'Nuevo','site':'B','minimum':1,'maximum':5})[0], 201)
        self.assertEqual(request('/api/v1/alerts?limit=999')[0], 422)
        self.assertEqual(request('/api/v1/telemetry', 'POST', body=self.event(), extra='X-Device-Key: '+self.key+'\r\n')[0], 202)
        self.service.process_one()
        self.assertEqual(json.loads(request('/api/v1/summary')[1])['readings'], 1)
        self.assertEqual(len(json.loads(request('/api/v1/devices/'+self.device+'/readings')[1])), 1)
        self.assertEqual(request('/api/v1/alerts/missing/ack', 'POST', body={})[0], 404)


if __name__ == '__main__':
    unittest.main()
