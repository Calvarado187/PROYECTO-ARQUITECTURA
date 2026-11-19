"""Reglas puras: no dependen de HTTP, SQL ni del almacenamiento de eventos."""
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import uuid
import hashlib


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


class BusinessError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def utcnow():
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Reading:
    event_id: str
    device_id: str
    temperature: float
    observed_at: str

    @classmethod
    def parse(cls, value):
        try:
            event_id = str(uuid.UUID(str(value['event_id'])))
            device_id = str(uuid.UUID(str(value['device_id'])))
            if isinstance(value['temperature'], bool):
                raise ValueError()
            temperature = float(value['temperature'])
            instant = datetime.fromisoformat(value['observed_at'].replace('Z', '+00:00'))
            if instant.tzinfo is None:
                raise ValueError()
            age = (datetime.now(timezone.utc) - instant).total_seconds()
            if not math.isfinite(temperature) or not -100 <= temperature <= 100:
                raise ValueError()
            if not -300 <= age <= 86400:
                raise ValueError()
            return cls(event_id, device_id, temperature, instant.astimezone(timezone.utc).isoformat())
        except (KeyError, ValueError, TypeError, AttributeError):
            raise BusinessError('Lectura inválida: UUID, temperatura entre -100 y 100 °C y fecha con zona horaria (últimas 24 h, tolerancia futura 5 min).', 422)


def thermal_state(value, low, high):
    return 'BAJA' if value < low else 'ALTA' if value > high else 'NORMAL'


def device_values(value):
    try:
        name, site = value['name'].strip(), value['site'].strip()
        low, high = float(value['minimum']), float(value['maximum'])
        if not name or not site or len(name) > 80 or len(site) > 80:
            raise ValueError()
        if not (-100 <= low < high <= 100):
            raise ValueError()
        return name, site, low, high
    except (KeyError, TypeError, ValueError, AttributeError):
        raise BusinessError('Nombre y sede obligatorios (máx. 80 caracteres); límites válidos: -100 ≤ mínimo < máximo ≤ 100.', 422)
