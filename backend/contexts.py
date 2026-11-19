"""Fronteras de aplicación: cada contexto expone su propio caso de uso."""
import hmac
import secrets
import threading
import time
from dataclasses import asdict
from .domain import BusinessError, Reading, device_values, utcnow, token_hash


class DeviceRegistry:
    """BC Dispositivos: identidad, configuración y credenciales de sensores."""
    def __init__(self, repository):
        self.repository = repository
        self.lock = threading.Lock()

    def register(self, body):
        with self.lock:
            if self.repository.summary()['devices'] >= 1000:
                raise BusinessError('Límite de la instalación: 1000 dispositivos.', 409)
            token = secrets.token_urlsafe(32)
            device = self.repository.create_device(device_values(body), token_hash(token))
            device.pop('token_hash', None)
            return {'device': device, 'device_token': token}

    def authorize_sensor(self, identifier, token):
        device = self.repository.device(identifier)
        if not device or not hmac.compare_digest(device['token_hash'], token_hash(token)):
            raise BusinessError('Credencial de dispositivo inválida.', 401)
        if not device['active']:
            raise BusinessError('Dispositivo inactivo.', 403)


class TelemetryIngestion:
    """BC Telemetría: valida eventos, controla admisión y confirma encolado."""
    def __init__(self, registry, queue, rate_limit):
        self.registry, self.queue, self.rate_limit = registry, queue, rate_limit
        self.buckets = {}
        self.lock = threading.Lock()

    def ingest(self, body, token):
        reading = Reading.parse(body)
        self.registry.authorize_sensor(reading.device_id, token)
        now = time.monotonic()
        with self.lock:
            start, count = self.buckets.get(reading.device_id, (now, 0))
            if now - start >= 60:
                start, count = now, 0
            if count >= self.rate_limit:
                raise BusinessError('Límite por dispositivo alcanzado; reintente en 60 s.', 429)
            self.buckets[reading.device_id] = (start, count + 1)
        event = asdict(reading)
        event['received_at'] = utcnow()
        self.queue.enqueue(event)
        return {'event_id': reading.event_id, 'status': 'accepted'}


class AlertOperations:
    """BC Alertas: consulta y reconocimiento operativo, separado de la resolución."""
    def __init__(self, repository):
        self.repository = repository

    def acknowledge(self, identifier):
        if not self.repository.acknowledge(identifier):
            raise BusinessError('Alerta no encontrada.', 404)
        return {'status': 'acknowledged'}
