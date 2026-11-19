"""Aceptación HTTP contra una instancia real local o Compose ya iniciada."""
import argparse
import json
import time
import uuid
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--url',default='http://127.0.0.1:8080')
    p.add_argument('--token',default='demo-admin-local')
    args=p.parse_args()
    def call(path,body=None,key=None):
        headers={'Content-Type':'application/json','Authorization':'Bearer '+args.token}
        if key: headers['X-Device-Key']=key
        request=Request(args.url+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        with urlopen(request,timeout=10) as response:
            return response.status,json.load(response)
    _,registered=call('/api/v1/devices',{'name':'Aceptación '+uuid.uuid4().hex[:6],'site':'Prueba sintética','minimum':2,'maximum':8})
    device,key=registered['device']['id'],registered['device_token']
    for temperature in (5,12,5):
        event={'event_id':str(uuid.uuid4()),'device_id':device,'temperature':temperature,'observed_at':datetime.now(timezone.utc).isoformat()}
        assert call('/api/v1/telemetry',event,key)[0]==202
        assert call('/api/v1/telemetry',event,key)[0]==202
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            _,rows=call('/api/v1/devices/'+device+'/readings')
            if any(row['event_id']==event['event_id'] for row in rows): break
            time.sleep(.25)
        else: raise AssertionError('El evento no se procesó en 30 s')
    _,rows=call('/api/v1/devices/'+device+'/readings')
    assert len(rows)==3, rows
    _,alerts=call('/api/v1/alerts')
    own=[a for a in alerts if a['device_id']==device]
    assert len(own)==1 and own[0]['resolved_at'], own
    assert call('/api/v1/alerts/'+own[0]['id']+'/ack',{})[0]==200
    print('Aceptación HTTP aprobada: registro, ingesta, duplicados, alerta, recuperación y reconocimiento.')

if __name__=='__main__': main()
