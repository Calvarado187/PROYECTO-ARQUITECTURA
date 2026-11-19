# FríoAlerta

Sistema de monitoreo IoT de temperatura para cámaras de refrigeración. Proyecto de Arquitectura de Software: tres canales, tres Bounded Contexts, capas explícitas, persistencia políglota, procesamiento asíncrono y frontend web.

## Iniciar en dos pasos

Requisito: Python 3.10 o superior. El perfil local no necesita pip, Docker ni acceso a internet.

Desde esta carpeta:

```sh
python -m backend.server
```

Abre **http://127.0.0.1:8080**, introduce `demo-admin-local` y pulsa **Conectar**. Registra un dispositivo; su credencial aparece una sola vez y se copia al simulador. Envía 5 °C, luego 12 °C y finalmente 5 °C. Espera una actualización entre envíos para ver la alerta activa y después resuelta. El rango inicial es 2 a 8 °C inclusive.

La consola se detiene con Ctrl+C. Los datos locales quedan en `data/`. El token de integración de solo lectura es `demo-integracion-local`. Son credenciales exclusivas de demostración: el servicio escucha solo en localhost.

## Entregables

- `docs/Arquitectura_FrioAlerta.pdf`: documento con C4, requisitos, ADR, datos y validación.
- `docs/arquitectura.md`: fuente editable del documento.
- `docs/diagramas/`: diagramas C4 en DOT editable, SVG vectorial, PNG y PDF.
- `docs/sustentacion.md`: guion de exposición y preguntas esperables.
- `docs/openapi.json`: contrato OpenAPI 3.1 importable.
- `backend/`: dominio, contextos, casos de uso, puertos y adaptadores.
- `frontend/`: interfaz web en HTML, CSS y JavaScript sin dependencias externas.
- `scripts/simulate.py`: cliente IoT con reintentos.
- `tests/`: pruebas de negocio, persistencia, concurrencia y API.
- `compose.yaml`, `Dockerfile`: perfil PostgreSQL + Redis.

## Probar

```sh
python -m unittest discover -s tests -v
python scripts/benchmark.py
```

Con el servidor iniciado, el recorrido de aceptación real por HTTP se ejecuta con `python scripts/smoke_http.py`. En Compose agrega `--token TU_ADMIN_TOKEN`. Esta prueba crea un sensor y tres lecturas sintéticas; no elimina datos previos.

El benchmark mide llamadas internas concurrentes, no tráfico HTTP ni rendimiento de PostgreSQL/Redis. La prueba TCP puede omitirse únicamente cuando Windows bloquea los sockets con error 10013. El parser y las rutas HTTP se prueban adicionalmente en memoria.

## Canal IoT

Después de crear el sensor desde la web:

```sh
python scripts/simulate.py --device ID_DEL_SENSOR --key CREDENCIAL_DEL_SENSOR --count 20
```

Cada evento lleva un UUID. Los reintentos conservan ese UUID. Un HTTP 202 confirma recepción en la cola, no escritura en el histórico. La consulta de histórico confirma el procesamiento. Usa siempre un UUID nuevo para una medición distinta; si se reutiliza con otro contenido, prevalece la primera versión procesada.

## Canal de integración

Ejemplo con curl:

```sh
curl -H "Authorization: Bearer demo-integracion-local" http://127.0.0.1:8080/api/v1/summary
```

El token de integración permite GET y no autoriza registro ni reconocimiento de alertas. Las credenciales de sensor solo sirven para su propio dispositivo.

## Perfil PostgreSQL y Redis

Requiere Docker Engine/Desktop, Compose y acceso a internet para descargar imágenes y psycopg. Copia `.env.example` a `.env`. Sustituye los tres valores por cadenas aleatorias distintas, generadas cada una con:

```sh
python -c "import secrets; print(secrets.token_hex(24))"
docker compose up --build -d
docker compose logs -f api
```

El panel continúa en localhost:8080, ahora con el ADMIN_TOKEN configurado. PostgreSQL y Redis no exponen puertos al host. Los volúmenes conservan los datos tras `docker compose down`; no uses `down -v` si deseas conservarlos.

La configuración admite **una instancia de aplicación y un trabajador**. No escales `api` sin rediseñar el consumo y el limitador. Redis usa Streams con lectura y borrado explícitos, no grupos de consumidores. AOF cada segundo implica una ventana potencial de pérdida ante caída brusca. El perfil distribuido está implementado, pero no fue ejecutado en el entorno de elaboración por ausencia de Docker y acceso a dependencias. No confundirlo con un despliegue productivo certificado.

## Configuración

| Variable | Predeterminado local | Uso |
|---|---|---|
| APP_MODE | local | `distributed` exige PostgreSQL, Redis y tokens de 24 caracteres o más |
| HOST | 127.0.0.1 | Dirección de escucha |
| PORT | 8080 | Puerto HTTP |
| DATA_DIR | data/ | SQLite y DBM locales |
| DATABASE_URL | data/frioalerta.sqlite3 | Ruta SQLite o URI `postgresql://` |
| REDIS_URL | Sin configurar | URI Redis de red interna, DB 0 |
| ADMIN_TOKEN | demo-admin-local | Operación y consulta |
| INTEGRATION_TOKEN | demo-integracion-local | Consulta únicamente |
| QUEUE_CAPACITY | 10000 | Límite de eventos pendientes |

## Alcance y límites

Este proyecto académico implementa registro de sensores, ingesta autenticada, almacenamiento, detección y resolución de alertas, reconocimiento e histórico. No incluye correo/SMS, aplicación móvil, multiempresa, edición de umbrales, baja de sensores ni alta disponibilidad. Los canales exigidos son web, API externa y agentes IoT.

El servidor HTTP de biblioteca estándar facilita ejecutar el proyecto sin dependencias, pero no es un servidor de producción. Para exposición pública se necesita otro adaptador HTTP, TLS, gestión de identidades y pruebas de carga del despliegue real. DBM es exclusivo de la demostración, no del escenario de volumen. La arquitectura, límites y compromisos están documentados sin atribuir resultados de producción a las pruebas locales.

## Publicación en GitHub

El enunciado solicita un repositorio público. El paquete incluye los archivos y el workflow, pero su publicación no se puede dar por realizada sin un URL verificable. En un repositorio nuevo y vacío:

```sh
git init
git add .
git commit -m "Implementa FrioAlerta y documenta arquitectura"
git branch -M main
git remote add origin URL_DEL_REPOSITORIO_PUBLICO
git push -u origin main
```

Antes de publicar, confirma que `.env` y `data/` siguen excluidos. No añadas credenciales ni datos operativos al repositorio.
