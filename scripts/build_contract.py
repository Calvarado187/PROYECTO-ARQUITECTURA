"""Genera el contrato OpenAPI versionado sin dependencias."""
import json
from pathlib import Path

def ref(name): return {'$ref':'#/components/schemas/'+name}
def response(description, schema): return {'description':description,'content':{'application/json':{'schema':schema}}}
def obj(properties, required=None): return {'type':'object','properties':properties,'required':required or list(properties)}
string={'type':'string'}
uuid={'type':'string','format':'uuid'}
instant={'type':'string','format':'date-time'}
nullable_time={'type':['string','null'],'format':'date-time'}
number={'type':'number'}
schemas={
 'Error':obj({'error':string}),
 'DeviceInput':obj({'name':{'type':'string','minLength':1,'maxLength':80},'site':{'type':'string','minLength':1,'maxLength':80},'minimum':{'type':'number','minimum':-100,'maximum':100},'maximum':{'type':'number','minimum':-100,'maximum':100}}),
 'ReadingInput':obj({'event_id':uuid,'device_id':uuid,'temperature':{'type':'number','minimum':-100,'maximum':100},'observed_at':{**instant,'description':'Ventana: últimas 24 h hasta 5 min futuros; zona horaria obligatoria.'}}),
 'Device':obj({'id':uuid,'name':string,'site':string,'minimum':number,'maximum':number,'active':{'type':'integer','enum':[0,1]},'last_at':nullable_time,'last_temperature':{'type':['number','null']},'state':{'type':'string','enum':['SIN DATOS','NORMAL','ALTA','BAJA']}}),
 'Alert':obj({'id':uuid,'device_id':uuid,'device_name':string,'kind':{'type':'string','enum':['ALTA','BAJA']},'temperature':number,'opened_at':instant,'resolved_at':nullable_time,'acknowledged_at':nullable_time}),
 'Summary':obj({'devices':{'type':'integer'},'readings':{'type':'integer'},'open_alerts':{'type':'integer'},'pending':{'type':'integer'},'worker':{'type':'boolean'},'last_processed_at':nullable_time}),
}
schemas['Reading']={'allOf':[ref('ReadingInput'),obj({'received_at':instant})]}
paths={}
def operation(path,method,title,result,code='200',input_schema=None,security='bearerAuth',parameters=None,description=''):
    op={'summary':title,'description':description,'operationId':method+'_'+path.strip('/').replace('/','_').replace('{','').replace('}',''),'security':[{security:[]}] if security else [],'responses':{code:response('Operación completada',result),**{str(n):response(text,ref('Error')) for n,text in [(400,'JSON inválido'),(401,'Credencial inválida'),(404,'Recurso no encontrado'),(413,'Cuerpo fuera de tamaño'),(422,'Validación'),(429,'Frecuencia excedida'),(503,'Indisponibilidad o cola llena')]}}}
    if input_schema: op['requestBody']={'required':True,'content':{'application/json':{'schema':input_schema}}}
    if parameters: op['parameters']=parameters
    paths.setdefault(path,{})[method]=op

pagination=[{'name':'limit','in':'query','schema':{'type':'integer','minimum':1,'maximum':200,'default':100}},{'name':'offset','in':'query','schema':{'type':'integer','minimum':0,'default':0}}]
identifier={'name':'id','in':'path','required':True,'schema':uuid}
operation('/health','get','Salud',obj({'status':string,'queue':{'type':'boolean'},'worker':{'type':'boolean'}}),security=None)
operation('/api/v1/devices','get','Consultar sensores',{'type':'array','items':ref('Device')},description='Operador o integración; instalación limitada a 1000 sensores.')
operation('/api/v1/devices','post','Registrar sensor',obj({'device':ref('Device'),'device_token':string}),'201',ref('DeviceInput'),description='Solo operador. minimum debe ser estrictamente menor a maximum. 409 si alcanza 1000 sensores.')
paths['/api/v1/devices']['post']['responses']['409']=response('Capacidad de instalación alcanzada',ref('Error'))
operation('/api/v1/telemetry','post','Admitir lectura',obj({'event_id':uuid,'status':{'type':'string','const':'accepted'}}),'202',ref('ReadingInput'),'deviceKey',description='202 confirma encolado. Reutilizar el mismo UUID al reintentar la misma lectura. 403 para sensor inactivo.')
paths['/api/v1/telemetry']['post']['responses']['403']=response('Sensor inactivo',ref('Error'))
operation('/api/v1/devices/{id}/readings','get','Histórico',{'type':'array','items':ref('Reading')},parameters=[identifier]+pagination)
operation('/api/v1/alerts','get','Consultar alertas',{'type':'array','items':ref('Alert')},parameters=pagination)
operation('/api/v1/alerts/{id}/ack','post','Reconocer alerta',obj({'status':{'type':'string','const':'acknowledged'}}),parameters=[identifier],description='Solo operador. Idempotente; no resuelve la alerta.')
operation('/api/v1/summary','get','Resumen',ref('Summary'))
document={'openapi':'3.1.0','info':{'title':'FríoAlerta API','version':'1.0.0','description':'Monitoreo IoT. Perfil académico local; TLS requerido para exposición externa.'},'servers':[{'url':'http://127.0.0.1:8080'}],'paths':paths,'components':{'securitySchemes':{'bearerAuth':{'type':'http','scheme':'bearer','description':'Token de operador para escritura; operador o integración para GET.'},'deviceKey':{'type':'apiKey','in':'header','name':'X-Device-Key'}},'schemas':schemas}}
(Path(__file__).resolve().parents[1]/'docs/openapi.json').write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding='utf-8')
