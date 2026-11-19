# Arquitectura de FríoAlerta

Proyecto final de Arquitectura de Software

Docente: MSc. Feisar Moreno

Versión 1.0 | 18 de noviembre de 2026

## 1 Propósito y problema

FríoAlerta supervisa la temperatura de cámaras de refrigeración en bodegas de alimentos. Una falla eléctrica o una puerta abierta puede producir una excursión térmica que pasa inadvertida entre inspecciones manuales. El operador necesita conocer qué cámara está fuera de rango, desde cuándo y si alguien ya revisó la situación. El responsable de calidad requiere un histórico consultable. Un sistema externo necesita extraer los mismos datos sin acceder directamente a las bases de datos.

Se propone una red de sensores que envía mediciones identificadas y fechadas. La aplicación valida y recibe los eventos, los procesa en segundo plano y abre alertas al detectar valores inferiores al mínimo o superiores al máximo. Cuando llega una lectura normal más reciente, resuelve la alerta. El reconocimiento humano se registra por separado: reconocer una alerta no corrige la temperatura.

La elección del dominio IoT reduce reglas administrativas y dependencias externas frente a pagos, transporte o streaming. Conserva desafíos arquitectónicos reales: ráfagas de reconexión, eventos repetidos, desorden temporal, fallos parciales y consumidores con necesidades distintas. No se requiere hardware: el simulador reproduce el contrato del sensor.

La solución es una instalación para una organización. No es un sistema clínico ni certifica condiciones sanitarias. Los datos utilizados en la demostración son sintéticos. Los umbrales 2 a 8 °C son un ejemplo configurable al registrar el dispositivo, no una recomendación aplicable a todos los productos.

## 2 Alcance y actores

| Actor o canal | Necesidad | Capacidad implementada |
|---|---|---|
| Operador mediante web | Ver estado y atender incidentes | Panel, registro, simulación, histórico y reconocimiento |
| Responsable de calidad | Revisar lecturas y alertas | Consulta web e histórico paginado por API |
| Sensor o agente IoT | Entregar mediciones incluso tras reintentos | POST autenticado, UUID, fecha y control de admisión |
| Sistema de terceros | Consumir datos sin escritura directa | REST de consulta con credencial de solo lectura |

Los tres canales exigidos son web interactiva, integración REST externa y agentes automatizados IoT. Comparten infraestructura HTTP, pero representan consumidores y permisos diferentes. No se cuenta el simulador dentro del panel como un cuarto canal. La implementación incluye el cliente IoT independiente en scripts/simulate.py.

Quedan fuera del alcance la aplicación móvil, envío de notificaciones por correo o SMS, múltiples organizaciones, mantenimiento de hardware, edición posterior de límites y eliminación de sensores. En la versión entregada los dispositivos se crean activos y los límites permanecen constantes. No se afirma que existan flujos de administración no implementados.

## 3 Requisitos y trazabilidad

| ID | Requisito | Evidencia y aceptación |
|---|---|---|
| RF01 | Registrar sensor y límites | DeviceRegistry; rechaza nombre vacío o mínimo mayor o igual al máximo |
| RF02 | Autenticar cada sensor | Credencial aleatoria; hash SHA-256; clave ajena produce 401 |
| RF03 | Recibir lectura con fecha e identidad | Reading.parse; 202 solo después de encolar |
| RF04 | Evitar efectos repetidos | PK event_id y commit SQL antes de eliminar el evento |
| RF05 | Detectar excursiones | Reglas ALTA, BAJA y NORMAL; una alerta activa por sensor |
| RF06 | Reconocer y resolver por separado | acknowledged_at y resolved_at independientes |
| RF07 | Consultar histórico | GET paginado, máximo 200 por solicitud |
| RF08 | Mantener estado ante eventos atrasados | Se archiva la lectura; no retrocede last_at |
| RA01 | Tres plataformas o canales | Web, API de terceros y simulador IoT |
| RA02 | Tres Bounded Contexts y capas | Dispositivos, Telemetría, Alertas; contexts.py, domain.py y adaptadores |
| RA03 | Dos motores de persistencia | PostgreSQL más Redis; perfil local SQLite más DBM |
| RA04 | Prevenir saturación | 32 solicitudes concurrentes, 120 eventos/min/sensor y cola limitada |
| RA05 | C4 niveles 1, 2 y 3 | Diagramas vectoriales y fuentes editables |
| RA06 | ADR y compromisos | Nueve decisiones registradas en sección 11 |
| RE01 | Backend y frontend | Código y pasos reproducibles en README |
| RE02 | Repositorio público | Requiere URL pública verificable; no acreditado por un ZIP |

El documento satisface la especificación del diseño. La verificación de ejecución se delimita en la sección 12; no se asigna un porcentaje de cumplimiento que oculte la validación distribuida pendiente o la publicación del repositorio.

## 4 Carga de diseño y atributos de calidad

El escenario propuesto contempla hasta 1000 sensores, una lectura por minuto y 20 operadores. La carga media es 1000/60 = 16,7 eventos por segundo, con 1 440 000 eventos diarios. Una reconexión coordinada podría concentrar 1000 envíos en pocos segundos. Estos valores son supuestos de dimensionamiento, no mediciones realizadas.

Suponiendo 250 bytes por evento serializado, el flujo bruto sería aproximadamente 360 MB/día y 10,8 GB en 30 días, antes de índices y sobrecarga del motor. La cola de 10 000 eventos representa cerca de diez minutos de entradas a la tasa media si el procesamiento se detiene. No representa retención histórica: el evento sale de la cola tras el commit SQL.

| Atributo | Escenario y respuesta | Meta de diseño |
|---|---|---|
| Latencia | Sensor envía y recibe confirmación de encolado | p95 de admisión menor a 500 ms bajo carga nominal |
| Frescura | Lectura aceptada genera actualización visible | Menor a 10 s bajo carga nominal |
| Control de carga | Ráfaga supera concurrencia o capacidad | 429/503 con Retry-After; no descartar silenciosamente |
| Recuperación | Se interrumpe SQL durante procesamiento | Conservar evento y reintentar con espera creciente |
| Consistencia | Se repite una lectura confirmada | Una fila histórica y un solo efecto sobre alertas |
| Mantenibilidad | Cambia el motor de eventos | Sustituir adaptador EventQueue sin cambiar el dominio |

Las metas de latencia y frescura del perfil distribuido requieren pruebas. El microbenchmark local muestra una capacidad de procesamiento inferior al escenario nominal: el modo SQLite/DBM se destina a demostración. La cola absorbe picos breves, pero no resuelve una tasa de llegada sostenida superior a la tasa de servicio. En esa situación deben reducirse emisores/frecuencia o ampliarse y medirse la capacidad antes de operar.

## 5 Bounded Contexts y lenguaje del dominio

### Dispositivos

Es dueño de identidad, sede, límites y credencial del sensor. Su entrada es la solicitud de registro; su salida es un identificador y una credencial que se muestra una vez. El contrato authorize_sensor permite a Telemetría verificar la identidad sin manipular la credencial almacenada. Un dispositivo es una fuente de mediciones; no equivale a un usuario humano.

### Telemetría

Es dueño del evento recibido y del histórico de lecturas. Define event_id, observed_at y received_at. observed_at procede del sensor y received_at del servidor. Valida formato, temperatura físicamente acotada y fecha entre 24 horas atrás y 5 minutos adelante. La ventana evita aceptar relojes claramente erróneos y limita reenvíos históricos. Una lectura es inmutable: no se proporciona endpoint para editarla.

### Alertas

Es dueño del incidente térmico y sus estados. Una lectura fuera de rango abre un incidente si no existe uno del mismo tipo. Una lectura normal posterior lo resuelve; cambiar de ALTA a BAJA cierra el incidente previo y abre otro. La temperatura de la alerta es la que la abrió, no la última del sensor. El reconocimiento es idempotente y conserva su primera fecha.

Dispositivos suministra identidad y umbrales a Telemetría. Telemetría suministra hechos validados a Alertas. Los contratos son internos y explícitos; no se añade un bus empresarial ni una llamada de red entre contextos. Los tres contextos comparten despliegue y una transacción SQL cuando el procesamiento debe actualizar histórico, estado y alerta juntos. Esta elección reduce fallos parciales; se acepta menor independencia de despliegue.

## 6 Arquitectura y modelo C4

### Nivel 1 Contexto del sistema

![C4 nivel 1](diagramas/c4_nivel_1.pdf)

FríoAlerta es el sistema de interés. El operador utiliza el panel; los sensores envían lecturas y el sistema de calidad consulta resultados. Los sensores y el sistema de terceros están fuera del límite. En este nivel no se incluyen tablas, controladores ni motores de almacenamiento.

### Nivel 2 Contenedores

![C4 nivel 2](diagramas/c4_nivel_2.pdf)

La web HTML/CSS/JavaScript se ejecuta en el navegador. El backend Python sirve sus archivos y expone REST/JSON. Dentro del backend vive un trabajador de procesamiento; no constituye un servicio desplegable aparte. PostgreSQL conserva registros transaccionales, mientras Redis Streams mantiene eventos pendientes. Los enlaces están rotulados con su propósito y protocolo. HTTP corresponde al despliegue académico en localhost; HTTPS es requisito para una futura exposición externa, no una capacidad TLS ya entregada.

En el perfil local, SQLite sustituye a PostgreSQL y DBM sustituye a Redis. El cambio se hace por configuración; el dominio no cambia. Redis y PostgreSQL aparecen en el diagrama de despliegue principal porque representan la persistencia seleccionada para el escenario de volumen, cuya integración en ejecución sigue pendiente de validación.

### Nivel 3 Componentes del backend

![C4 nivel 3](diagramas/c4_nivel_3.pdf)

Handler adapta HTTP a casos de uso. DeviceRegistry, TelemetryIngestion y AlertOperations representan las fronteras de aplicación. Service compone esos casos de uso y ejecuta el ciclo del trabajador. Reading y thermal_state contienen reglas independientes de red y almacenamiento. SQLRepository implementa transacciones; EventQueue admite LocalQueue y RedisQueue. Los componentes no se confunden con tablas o procesos independientes.

El repositorio SQL concentra la operación atómica de archivar, evaluar y persistir la transición. La decisión térmica se delega al dominio; la selección de filas y los bloqueos quedan en infraestructura. Esta unidad transaccional es una concesión deliberada frente a una separación más estricta de repositorios por contexto. Evita introducir transacciones distribuidas en una aplicación académica pequeña.

### Correspondencia con el código

| Elemento | Ubicación | Responsabilidad |
|---|---|---|
| Dominio | backend/domain.py | Validación, fecha, lectura y clasificación térmica |
| Contextos | backend/contexts.py | Registro, autenticación de sensor, admisión y reconocimiento |
| Aplicación | backend/application.py | Composición y procesamiento diferido |
| Puertos | backend/ports.py | Contratos Repository y EventQueue |
| Persistencia | backend/storage.py | SQL, DBM, Redis y fronteras transaccionales |
| Adaptador HTTP | backend/server.py | Rutas, permisos, límites y respuestas |
| Presentación | frontend/ | Renderizado y consumo REST; no accede a las bases |

## 7 Persistencia y consistencia

| Motor | Datos | Motivo | Compromiso |
|---|---|---|---|
| PostgreSQL | Dispositivos, lecturas y alertas | Transacciones, restricciones e histórico indexado | Operación, backups y crecimiento del histórico |
| Redis Streams | Eventos pendientes como JSON | Separar recepción y procesamiento; capacidad acotada | Memoria, persistencia configurable y fallo adicional |
| SQLite local | Mismo esquema relacional | Demostración sin instalar servidor SQL | Un escritor y menor capacidad concurrente |
| DBM local | Eventos por clave aleatoria | Almacén clave-valor persistente sin paquetes | Un proceso, búsqueda lineal y no apto para volumen |

La persistencia políglota no se justifica por contar tecnologías. SQL resuelve invariantes y consultas relacionadas. Redis atiende un ciclo diferente: entrada rápida, espera y eliminación tras confirmación. No hay un doble guardado simultáneo desde el endpoint; primero se encola y después se realiza la transacción SQL. [2][3]

devices contiene id, name, site, minimum, maximum, token_hash, active, last_at, last_temperature y state. readings contiene event_id como clave primaria, device_id como clave foránea, temperature, observed_at y received_at. alerts contiene id, device_id, kind, temperature, opened_at, resolved_at y acknowledged_at. La relación es un dispositivo a muchas lecturas y muchas alertas.

Un índice por device_id y observed_at soporta el histórico. Un índice único parcial en alerts(device_id) cuando resolved_at es nulo protege la regla de una alerta activa por dispositivo. Se usan parámetros SQL, no interpolación de entradas. En SQLite se activan claves foráneas y WAL; en PostgreSQL se bloquea la fila del dispositivo durante el procesamiento. WAL mejora convivencia de lecturas y escrituras, pero no elimina la limitación de un escritor de SQLite. [4][5]

El identificador del evento proporciona idempotencia durante la retención de readings. La entrega es al menos una vez mientras el registro permanezca durable en la cola; no se promete entrega exactamente una vez. Si el proceso cae después del commit y antes del borrado, la repetición encuentra el UUID existente y no duplica el efecto. Si el mismo UUID se usa para un contenido distinto, gana la primera versión procesada: el emisor debe generar un UUID nuevo por medición.

El histórico permite eventos atrasados. last_at solo avanza con una fecha estrictamente posterior; con fechas iguales la primera lectura procesada conserva el estado actual. Una lectura antigua nunca reabre una alerta ya resuelta por una lectura posterior. No se pretende reconstruir retrospectivamente episodios a partir de eventos fuera de orden.

La política propuesta es conservar 30 días en línea y exportar/depurar fuera de ese plazo. Esa automatización no está implementada y el histórico actual crece hasta intervención manual. Antes de operar el volumen nominal se necesitan particiones temporales, retención y backup probado. El código no utiliza DBM para simular falsamente un Redis real.

## 8 Flujos principales

### Registrar y medir

El operador envía nombre, sede y umbrales. Dispositivos valida el rango y genera un UUID y una clave aleatoria de 256 bits. El servidor conserva el hash y devuelve la clave solo en el registro. El sensor envía event_id, device_id, temperature y observed_at, junto con X-Device-Key. La API valida el evento y la credencial, aplica el límite y escribe en la cola. Solo entonces devuelve 202.

### Procesar y abrir una alerta

El trabajador lee el evento pendiente más antiguo. En una transacción inserta la lectura si el UUID no existe, compara la fecha con el estado actual y calcula NORMAL, ALTA o BAJA. Persiste los cambios de alerta y dispositivo, confirma SQL y elimina el evento de la cola. La interfaz consulta cada cinco segundos; la consistencia visible entre recepción y panel es eventual.

### Recuperar y reconocer

Si SQL falla, el evento no se elimina. El trabajador espera inicialmente 0,25 segundos y duplica la espera hasta un máximo de 10 segundos. Si Redis falla, no se confirma la admisión y la API responde 503. El simulador conserva el UUID entre reintentos. Reconocer una alerta guarda acknowledged_at sin cambiar su resolución. Una nueva temperatura normal la resuelve automáticamente.

## 9 Contrato de integración

| Método y ruta | Permiso | Resultado principal |
|---|---|---|
| GET /health | Sin token | Estado de SQL, cola y trabajador |
| POST /api/v1/devices | Operador | 201 con dispositivo y credencial mostrada una sola vez |
| GET /api/v1/devices | Operador o integración | Hasta 1000 sensores, sin hashes |
| POST /api/v1/telemetry | Clave del sensor | 202 recibido en cola |
| GET /api/v1/devices/{id}/readings | Operador o integración | Histórico con limit y offset |
| GET /api/v1/alerts | Operador o integración | Alertas paginadas |
| POST /api/v1/alerts/{id}/ack | Operador | 200 reconocimiento idempotente |
| GET /api/v1/summary | Operador o integración | Contadores y profundidad de cola |

Los errores devuelven JSON con error. Se distinguen 400 de formato, 401 de credencial, 403 de sensor inactivo, 404 de recurso, 409 de capacidad de dispositivos, 413 de tamaño, 422 de validación, 429 de frecuencia y 503 de indisponibilidad. Las respuestas 429 y 503 incluyen Retry-After. El listado de dispositivos está limitado por la capacidad de la instalación; histórico y alertas permiten páginas de 1 a 200 filas. El contrato completo está en openapi.json.

## 10 Resiliencia seguridad y operación

El servidor admite 32 solicitudes simultáneas y una espera TCP de hasta 64 conexiones. Rechaza exceso de concurrencia con 503. El cuerpo está limitado a 16 KiB y la conexión tiene timeout de 5 segundos. Cada sensor autenticado dispone de 120 intentos por minuto; la ventana es local al proceso y se reinicia al arrancar. La capacidad de cola predeterminada es 10 000 eventos. Redis verifica longitud e inserta mediante una operación Lua atómica. No usa MAXLEN para descartar eventos sin procesar.

La configuración entregada ejecuta un único trabajador. XRANGE obtiene la primera entrada y XDEL confirma su eliminación después de SQL; no hay grupos de consumidores. Mantener un consumidor simplifica el orden y evita coordinación innecesaria. Para escalar habría que particionar por dispositivo, usar grupos de consumidores, recuperar pendientes y trasladar el limitador a un almacén compartido. Es una evolución propuesta, no una característica implementada.

Un evento corrupto en el almacén podría bloquear la cabeza de la cola; las entradas HTTP se validan antes de persistir, pero no existe una cola de errores automática. La respuesta operativa es detener el trabajador, respaldar la cola, diagnosticar y aislar el registro, sin borrado indiscriminado. Las fallas se registran sin credenciales ni cuerpos completos. /health y /summary permiten observar disponibilidad, pendientes y última confirmación; no existe alerta automática de inactividad de sensores.

Los roles se separan mediante tokens: operador, integración de consulta y sensor individual. La aplicación no incluye login por usuario, recuperación de contraseña ni trazabilidad nominal de operadores. La interfaz mantiene el token solo en memoria de la página y utiliza textContent para datos de usuario. La política CSP limita scripts al mismo origen. Las bases de datos solo son accesibles dentro de Compose; no se publican sus puertos.

Redis utiliza AOF cada segundo y política noeviction. Una caída abrupta del host puede perder aproximadamente el último segundo de escrituras aún no sincronizadas; la solución no promete RPO cero. Cambiar a appendfsync always reduce esa ventana a costa de latencia y requiere nuevas mediciones. En el perfil local, DBM no ofrece garantías transaccionales equivalentes y solo se recomienda para demostración. [3]

El servidor de biblioteca estándar es adecuado para una demostración controlada, no para publicación productiva. Antes de exponerlo deben reemplazarse el adaptador HTTP, instalar TLS, gestionar secretos y cuentas, validar backups y probar la carga real. Las credenciales locales de ejemplo no se deben reutilizar. El modo distribuido exige credenciales separadas de al menos 24 caracteres. [6]

## 11 Registros de decisiones de arquitectura

### ADR 001 Monolito modular con trabajador interno

Estado: aceptada. Contexto: tres áreas del dominio y alcance académico acotado. Alternativas: microservicios por contexto o monolito con límites internos. Decisión: un despliegue con clases de contexto separadas y trabajador interno. Consecuencia favorable: instalación sencilla y transacción común para histórico y alertas. Coste: no se escalan o publican contextos por separado; una caída del proceso afecta API y trabajador. Revisar si distintos equipos o perfiles de carga exigen independencia.

### ADR 002 Capas y puertos explícitos

Estado: aceptada. Contexto: se necesitan dos perfiles de almacenamiento sin cambiar las reglas. Alternativas: consultas SQL en handlers o contratos Repository/EventQueue. Decisión: dominio puro, contextos de aplicación y adaptadores. Beneficio: pruebas directas y sustitución de cola. Coste: Repository es un puerto amplio y la transacción cruza contextos; dividirlo será útil si crece el sistema. Las fronteras son lógicas, no aislamiento físico.

### ADR 003 PostgreSQL y Redis

Estado: aceptada en diseño; integración pendiente de prueba real. Contexto: histórico relacionado y ráfagas de eventos tienen ciclos distintos. Alternativas: solo PostgreSQL, documentos MongoDB o Redis más SQL. Decisión: PostgreSQL para consistencia y Redis Streams para amortiguar entradas. Beneficio: cada motor tiene una función definida y se cumple la persistencia políglota con fundamento. Coste: dos servicios, recuperación y monitorización; Redis no reemplaza el histórico. [2][3][5]

### ADR 004 Perfil local sin dependencias

Estado: aceptada para demostración. Contexto: facilitar ejecución sin descargar servicios. Alternativas: exigir Docker o proporcionar SQLite/DBM. Decisión: SQLite y dbm.dumb con el mismo contrato de aplicación. Beneficio: basta Python 3.10 o superior. Coste: rendimiento inferior, datos DBM no transaccionales y un solo proceso. Este perfil no valida rendimiento ni protocolos de los motores distribuidos. [4][7]

### ADR 005 Idempotencia mediante identidad de evento

Estado: aceptada. Contexto: los sensores pueden perder la respuesta de recepción y repetirla. Alternativas: rechazar repeticiones en memoria, transacción distribuida o clave única SQL. Decisión: event_id único y eliminación de cola después del commit. Beneficio: evita duplicar lecturas y alertas por reentrega. Coste: duplicados ocupan cola temporalmente y el contrato exige no reutilizar UUID con otro contenido.

### ADR 006 Admisión acotada y un consumidor

Estado: aceptada. Contexto: una cola ilimitada trasladaría la saturación a memoria/disco. Alternativas: descartar mediciones antiguas o rechazar nueva admisión. Decisión: 32 solicitudes, 120 intentos/min/sensor, 10 000 pendientes y respuestas de reintento. Beneficio: memoria y concurrencia acotadas sin borrado silencioso. Coste: el emisor debe reintentar y la capacidad sostenida está limitada al trabajador. La tasa local no se presenta como capacidad del diseño distribuido.

### ADR 007 Web sin framework y API versionada

Estado: aceptada. Contexto: una sola plataforma visual es obligatoria. Alternativas: SPA con framework, aplicación móvil o HTML/JS. Decisión: web accesible sin compilación, API /api/v1 y simulador Python. Beneficio: pocos requisitos de instalación, frontend separado y tres canales reales. Coste: renderizado manual y polling cada cinco segundos; no se implementan WebSockets ni aplicación móvil.

### ADR 008 Credenciales por canal

Estado: aceptada para alcance académico. Contexto: sensores y terceros no deben operar como administradores. Alternativas: una clave global, tokens separados u OIDC completo. Decisión: clave aleatoria por sensor, hash persistido y tokens distintos de operación y consulta. Beneficio: mínimo privilegio entre canales. Coste: no hay usuarios nominales ni rotación automática. Una operación real requeriría gestión de identidades y TLS.

### ADR 009 Persistencia AOF y límites de disponibilidad

Estado: aceptada con riesgo documentado. Contexto: Redis es un componente de admisión y debe sobrevivir reinicios. Alternativas: memoria únicamente, AOF everysec o fsync en cada escritura. Decisión: AOF everysec y volúmenes persistentes. Beneficio: compromiso sencillo entre latencia y durabilidad. Coste: posible pérdida reciente ante fallo abrupto, sin alta disponibilidad ni réplica. No se declara disponibilidad porcentual sin medición. [3]

## 12 Verificación y resultados

La suite ejecuta reglas de umbrales, validación de valores y fechas, credenciales, registro, ciclo de alertas, reconocimiento idempotente, eventos atrasados, duplicados, caída entre commit y eliminación, fallo SQL, cola llena, frecuencia y recepción concurrente. Un ensayo del adaptador HTTP procesa solicitudes reales en memoria con el parser estándar y verifica rutas, códigos y permisos. Un ensayo adicional usa TCP cuando el entorno permite conexiones locales.

Resultado verificado en el entorno de elaboración: 14 casos, 13 aprobados y 1 omitido por bloqueo de sockets de Windows (10013). La omisión corresponde a integración HTTP por red, no a reglas de negocio. También se verificó la sintaxis de JavaScript. No se ejecutaron PostgreSQL, Redis, Docker ni pruebas reales en navegador; por tanto, no se presentan como aprobados. Las pruebas reproducibles incluidas permiten completar esa validación en una máquina habilitada.

Microbenchmark local: 200 eventos con 16 emisores concurrentes, mediante llamadas directas a la aplicación, 200 persistidos y cero pendientes. Resultado de referencia: admisión 2,620 s, p95 236,11 ms y procesamiento posterior 16,005 s. La tasa de procesamiento de ese ensayo fue aproximadamente 12,5 eventos/s. No incluye HTTP, no mezcla admisión y consumo simultáneos y no acredita el escenario nominal. La medición debe repetirse tras cambios de almacenamiento o hardware.

La prueba de recuperación provoca el estado crítico después del commit y antes de eliminar la cola, cierra y reabre el almacén y procesa otra vez. El histórico conserva una sola lectura. La prueba de fallo SQL verifica que el evento permanece pendiente hasta recuperarse. Estas verificaciones aportan evidencia de consistencia ante fallos que un simple CRUD no cubriría.

Para validar el perfil distribuido se debe ejecutar Compose, repetir el recorrido web, enviar eventos con el simulador, detener PostgreSQL y observar el evento retenido, reiniciarlo y comprobar recuperación, reiniciar Redis y verificar persistencia, y ejecutar carga HTTP midiendo p95 y retraso de cola. Ese recorrido es un criterio de aceptación pendiente, no un resultado atribuido a la entrega.

## 13 Matriz de evaluación y sustentación

| Criterio de rúbrica | Peso | Material preparado |
|---|---|---|
| Rigor y argumentación técnica | 15 % | ADR, alternativas y limitaciones explícitas |
| Restricciones mínimas | 15 % | Tres canales, contextos, capas, motores y admisión acotada |
| Modelado C4 | 15 % | Contexto, contenedores y componentes con límites y protocolos |
| Presentación de avances | 25 % | Guion, recorrido de demostración y preguntas de defensa |
| Código e integración | 30 % | Backend, web, simulador, contrato, pruebas y despliegue |

La ponderación corresponde al enunciado; no implica una calificación obtenida. La sustentación depende de comprender y explicar las decisiones. La presentación realizada en clase no puede sustituirse por un archivo preparado. El repositorio público exige publicación y URL comprobable; el código empaquetado no constituye evidencia de esa publicación.

El enunciado fija primera entrega el 12 de noviembre de 2026 a las 10:00, sustentación el 17 de noviembre de 8:00 a 10:00 y entrega final el 19 de noviembre a las 10:00. Se conservan esas fechas como referencia del documento recibido, sin afirmar prórrogas.

## 14 Referencias

[1] Simon Brown. C4 model, Diagrams. https://c4model.com/diagrams

[2] Redis. Redis Streams. https://redis.io/docs/latest/develop/data-types/streams/

[3] Redis. Redis persistence. https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/

[4] SQLite. Write-Ahead Logging. https://www.sqlite.org/wal.html

[5] PostgreSQL. Explicit Locking. https://www.postgresql.org/docs/current/explicit-locking.html

[6] Python. http.server. https://docs.python.org/3/library/http.server.html

[7] Python. dbm. https://docs.python.org/3/library/dbm.html

[8] Moreno, Feisar. Proyecto final de Arquitectura de Software. Enunciado suministrado, cinco páginas, 2026.

Fuentes técnicas consultadas el 18 de noviembre de 2026. Las cifras de carga y metas de calidad son hipótesis propias del proyecto; los resultados de pruebas se identifican por separado.
