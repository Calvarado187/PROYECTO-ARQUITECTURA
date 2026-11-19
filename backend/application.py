"""Casos de uso de Dispositivos, Telemetría y Alertas."""
import logging
import threading
from .domain import utcnow
from .ports import EventQueue, Repository
from .contexts import DeviceRegistry, TelemetryIngestion, AlertOperations


class Service:
    def __init__(self, repository: Repository, queue: EventQueue, rate_limit=120):
        self.repository, self.queue = repository, queue
        self.rate_limit = rate_limit
        self.stop = threading.Event()
        self.worker_alive = False
        self.last_success = None
        self.registry = DeviceRegistry(repository)
        self.telemetry = TelemetryIngestion(self.registry, queue, rate_limit)
        self.alert_operations = AlertOperations(repository)

    def register(self, body):
        return self.registry.register(body)

    def ingest(self, body, token):
        self.telemetry.rate_limit = self.rate_limit
        return self.telemetry.ingest(body, token)

    def process_one(self):
        entry = self.queue.peek()
        if not entry:
            return False
        key, event = entry
        self.repository.process(event)
        # Primero commit SQL; después ACK. Una caída intermedia provoca reentrega segura.
        self.queue.ack(key)
        self.last_success = utcnow()
        return True

    def run_worker(self):
        self.worker_alive = True
        delay = 0.25
        while not self.stop.is_set():
            try:
                if not self.process_one():
                    self.stop.wait(0.1)
                delay = 0.25
            except Exception:
                logging.exception('No se confirmó el evento; permanece en cola para reintento')
                self.stop.wait(delay)
                delay = min(delay * 2, 10)
        self.worker_alive = False
