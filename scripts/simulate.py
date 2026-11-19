"""Canal IoT automatizado. No requiere paquetes externos."""
import argparse
import json
import random
import time
import uuid
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--url', default='http://127.0.0.1:8080')
    p.add_argument('--device', required=True)
    p.add_argument('--key', required=True)
    p.add_argument('--count', type=int, default=20)
    p.add_argument('--interval', type=float, default=1)
    args = p.parse_args()
    for _ in range(args.count):
        event = {'event_id': str(uuid.uuid4()), 'device_id': args.device, 'temperature': round(random.uniform(1, 12), 1), 'observed_at': datetime.now(timezone.utc).isoformat()}
        for attempt in range(6):
            try:
                request = Request(args.url + '/api/v1/telemetry', data=json.dumps(event).encode(), headers={'Content-Type': 'application/json', 'X-Device-Key': args.key})
                with urlopen(request, timeout=8) as response:
                    print(response.status, event['temperature'], event['event_id'])
                break
            except HTTPError as error:
                if error.code not in (429, 503):
                    raise
                time.sleep(int(error.headers.get('Retry-After', 2)))
            except (URLError, TimeoutError):
                time.sleep(min(2 ** attempt, 30) + random.random())
        else:
            raise RuntimeError('Lectura no confirmada: ' + event['event_id'])
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
