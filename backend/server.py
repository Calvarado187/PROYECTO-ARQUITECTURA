"""API HTTP con concurrencia acotada y frontend desacoplado en archivos estáticos."""
import hmac
import json
import logging
import mimetypes
import os
from pathlib import Path
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from .application import Service
from .domain import BusinessError
from .storage import LocalQueue, RedisQueue, SQLRepository

ROOT = Path(__file__).resolve().parents[1]


class BoundedServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 64
    def __init__(self, address, handler, service, admin_token, integration_token):
        self.service = service
        self.admin_token, self.integration_token = admin_token, integration_token
        self.slots = threading.BoundedSemaphore(32)
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(False):
            try:
                request.sendall(b'HTTP/1.0 503 Service Unavailable\r\nRetry-After: 2\r\nContent-Length: 0\r\n\r\n')
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, fmt, *args):
        logging.info('%s %s', self.command, self.path.split('?')[0])

    def send(self, status, payload, mime='application/json; charset=utf-8'):
        data = json.dumps(payload, ensure_ascii=False).encode() if not isinstance(payload, bytes) else payload
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'")
        if status in (429, 503):
            self.send_header('Retry-After', '60' if status == 429 else '2')
        self.end_headers()
        self.wfile.write(data)

    def authorize(self, integration=False):
        supplied = self.headers.get('Authorization', '').removeprefix('Bearer ')
        valid = hmac.compare_digest(supplied, self.server.admin_token)
        if integration:
            valid = valid or hmac.compare_digest(supplied, self.server.integration_token)
        if not valid:
            raise BusinessError('Token de acceso inválido.', 401)

    def body(self):
        try:
            if self.headers.get('Transfer-Encoding'):
                raise BusinessError('Transfer-Encoding no admitido.', 400)
            size = int(self.headers.get('Content-Length', '0'))
            if size <= 0 or size > 16384:
                raise BusinessError('El cuerpo debe tener entre 1 y 16384 bytes.', 413)
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except (ValueError, UnicodeError):
            raise BusinessError('Se requiere un objeto JSON válido.', 400)

    def handle_request(self):
        try:
            path = urlparse(self.path).path
            query = parse_qs(urlparse(self.path).query)
            service, repo = self.server.service, self.server.service.repository
            if self.command == 'GET' and path in ('/', '/app.js', '/styles.css'):
                file = ROOT / 'frontend' / ('index.html' if path == '/' else path[1:])
                return self.send(200, file.read_bytes(), mimetypes.guess_type(file)[0] or 'text/plain')
            if self.command == 'GET' and path == '/health':
                repo.summary()
                return self.send(200, {'status': 'ok', 'queue': service.queue.healthy(), 'worker': service.worker_alive})
            if self.command == 'POST' and path == '/api/v1/telemetry':
                return self.send(202, service.ingest(self.body(), self.headers.get('X-Device-Key', '')))
            self.authorize(integration=self.command == 'GET')
            try:
                limit = int(query.get('limit', ['100'])[0])
                offset = int(query.get('offset', ['0'])[0])
                if not 1 <= limit <= 200 or offset < 0:
                    raise ValueError()
            except ValueError:
                raise BusinessError('Paginación inválida: limit 1..200, offset ≥ 0.', 422)
            if path == '/api/v1/devices':
                if self.command == 'POST':
                    return self.send(201, service.register(self.body()))
                if self.command == 'GET':
                    return self.send(200, repo.devices())
            if path == '/api/v1/summary' and self.command == 'GET':
                return self.send(200, {**repo.summary(), 'pending': service.queue.size(), 'worker': service.worker_alive, 'last_processed_at': service.last_success})
            if path == '/api/v1/alerts' and self.command == 'GET':
                return self.send(200, repo.alerts(limit, offset))
            parts = path.strip('/').split('/')
            if len(parts) == 5 and parts[:3] == ['api', 'v1', 'alerts'] and parts[4] == 'ack' and self.command == 'POST':
                return self.send(200, service.alert_operations.acknowledge(parts[3]))
            if len(parts) == 5 and parts[:3] == ['api', 'v1', 'devices'] and parts[4] == 'readings' and self.command == 'GET':
                if not repo.device(parts[3]):
                    raise BusinessError('Dispositivo no encontrado.', 404)
                return self.send(200, repo.readings(parts[3], limit, offset))
            raise BusinessError('Ruta no encontrada.', 404)
        except BusinessError as error:
            self.send(error.status, {'error': str(error)})
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            return
        except Exception:
            logging.exception('Fallo de infraestructura')
            self.send(503, {'error': 'Servicio temporalmente no disponible. Reintente con el mismo identificador.'})

    do_GET = handle_request
    do_POST = handle_request


def create_server(port=None):
    mode = os.getenv('APP_MODE', 'local')
    admin = os.getenv('ADMIN_TOKEN', 'demo-admin-local' if mode == 'local' else '')
    integration = os.getenv('INTEGRATION_TOKEN', 'demo-integracion-local' if mode == 'local' else '')
    if not admin or not integration or (mode != 'local' and (len(admin) < 24 or len(integration) < 24)):
        raise RuntimeError('Configure ADMIN_TOKEN e INTEGRATION_TOKEN distintos, de al menos 24 caracteres.')
    if admin == integration:
        raise RuntimeError('Las credenciales deben ser distintas.')
    data = Path(os.getenv('DATA_DIR', str(ROOT / 'data')))
    repo = SQLRepository(os.getenv('DATABASE_URL', str(data / 'frioalerta.sqlite3')))
    capacity = int(os.getenv('QUEUE_CAPACITY', '10000'))
    queue = RedisQueue(os.environ['REDIS_URL'], capacity) if os.getenv('REDIS_URL') else LocalQueue(str(data / 'events'), capacity)
    if mode != 'local' and (not repo.postgres or not isinstance(queue, RedisQueue)):
        raise RuntimeError('El perfil distribuido requiere PostgreSQL y Redis.')
    service = Service(repo, queue)
    server = BoundedServer((os.getenv('HOST', '127.0.0.1'), port if port is not None else int(os.getenv('PORT', '8080'))), Handler, service, admin, integration)
    return server


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    server = create_server()
    worker = threading.Thread(target=server.service.run_worker, daemon=True)
    worker.start()
    print(f'FríoAlerta: http://{server.server_address[0]}:{server.server_address[1]}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.service.stop.set()
        worker.join(timeout=15)
        server.server_close()
        if hasattr(server.service.queue, 'close'):
            server.service.queue.close()


if __name__ == '__main__':
    main()
