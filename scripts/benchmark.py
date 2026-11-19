"""Microbenchmark local reproducible. No equivale a una prueba HTTP o distribuida."""
import json
import sys
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.application import Service
from backend.storage import SQLRepository, LocalQueue

def main():
    with tempfile.TemporaryDirectory() as folder:
        queue = LocalQueue(folder + '/events', 2000)
        service = Service(SQLRepository(folder + '/db.sqlite'), queue, rate_limit=2000)
        device = service.register({'name':'Prueba','site':'Local','minimum':2,'maximum':8})
        latencies = []
        def send(_):
            event = {'event_id':str(uuid.uuid4()),'device_id':device['device']['id'],'temperature':5,'observed_at':datetime.now(timezone.utc).isoformat()}
            start = time.perf_counter()
            service.ingest(event, device['device_token'])
            return (time.perf_counter()-start)*1000
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=16) as pool:
            latencies = list(pool.map(send, range(200)))
        ingress_seconds = time.perf_counter()-start
        start = time.perf_counter()
        while service.process_one(): pass
        process_seconds = time.perf_counter()-start
        print(json.dumps({'profile':'local SQLite + DBM; llamadas directas, sin HTTP','events':200,'concurrency':16,'ingress_seconds':round(ingress_seconds,3),'ingress_p95_ms':round(sorted(latencies)[189],2),'processing_seconds':round(process_seconds,3),'persisted':service.repository.summary()['readings'],'pending':queue.size()},ensure_ascii=False,indent=2))
        queue.close()

if __name__ == '__main__': main()
