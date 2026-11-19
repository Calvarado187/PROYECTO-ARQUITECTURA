# Guion de sustentación FríoAlerta

Duración sugerida: 8 a 10 minutos. Ejecutar previamente `python -m backend.server` desde la raíz del proyecto.

## 1 Problema y elección del dominio — 1 minuto

FríoAlerta permite vigilar temperaturas de cámaras de refrigeración. Elegimos IoT porque reproduce concurrencia, datos continuos y fallos de comunicación sin necesitar una pasarela de pagos ni hardware físico. No se limita a registrar datos: procesa eventos, evita duplicados, controla saturación y gestiona incidentes.

## 2 Arquitectura — 2 minutos

Mostrar C4 nivel 1: operador, sensores y sistema externo. Mostrar nivel 2: web, backend, PostgreSQL y Redis. Aclarar que el trabajador está dentro del backend. Explicar los tres contextos: Dispositivos es dueño de configuración y credenciales; Telemetría de eventos e histórico; Alertas de incidentes y reconocimiento.

Decidimos un monolito modular porque los contextos no requieren despliegues independientes. Conservamos puertos para poder cambiar almacenamiento sin cambiar reglas. PostgreSQL aporta transacciones; Redis desacopla recepción de procesamiento. La demostración local usa SQLite y DBM, por lo que no prueba el comportamiento de Redis o PostgreSQL.

## 3 Demostración — 3 minutos

1. Abrir http://127.0.0.1:8080 e introducir demo-admin-local.
2. Registrar Cámara 01, Bodega central, límites 2 y 8.
3. Mostrar credencial del sensor; explicar que el servidor guarda su hash.
4. Enviar 5 °C y esperar la actualización. Estado NORMAL.
5. Enviar 12 °C y esperar. Se abre ALTA.
6. Reconocer la alerta. Explicar por qué reconocer no la resuelve.
7. Enviar 5 °C y esperar. La alerta queda resuelta, preservando reconocimiento.
8. Abrir histórico. Mostrar mediciones y UUID.
9. Si hay tiempo, usar scripts/simulate.py para demostrar el canal independiente.

## 4 Fallos y evidencia — 2 minutos

Ejecutar `python -m unittest discover -s tests -v`. Explicar la prueba de caída después del commit: al volver a procesar no aparece una segunda lectura. Explicar 429 por frecuencia y 503 por cola llena. No afirmar que una cola soluciona cualquier carga: si llegan más eventos de los que se procesan de forma sostenida, termina llenándose.

Informar qué pruebas se ejecutaron en la máquina de presentación. En el entorno de elaboración la prueba TCP se omitió por restricción de sockets; la adaptación HTTP sí se verificó en memoria. Si no se ha corrido Compose, decirlo. Evitar presentar las metas de diseño como resultados medidos.

## 5 Cierre — 1 minuto

El aporte principal es mantener coherencia entre recepción, persistencia y alertas ante duplicados y fallos. El paso siguiente para operar a escala consiste en validar PostgreSQL/Redis, sustituir el adaptador HTTP de demostración, probar capacidad y añadir retención y recuperación operativa.

## Preguntas probables

**¿Por qué no microservicios?** No existe todavía una necesidad que compense redes, contratos distribuidos y coordinación. La modularidad lógica cubre el alcance.

**¿Dónde están los tres canales?** La web de operadores, la API de consulta para sistemas externos y el agente IoT que envía eventos con su propia credencial.

**¿Por qué Redis si ya existe SQL?** Permite admitir temporalmente ráfagas antes del procesamiento transaccional. Añade complejidad y una ventana de durabilidad, por eso la decisión está registrada.

**¿Qué significa 202?** Que el evento ingresó a la cola. La consulta posterior del histórico confirma que se procesó.

**¿Se pierde información?** Un fallo del proceso después del commit no duplica datos. Un fallo abrupto del almacenamiento puede perder escrituras no sincronizadas; AOF everysec no ofrece RPO cero.

**¿Qué ocurre con lecturas atrasadas?** Se conservan en histórico, pero no reemplazan el estado actual ni reabren incidentes anteriores.

**¿Es exactamente una vez?** No. Es reentrega con efectos idempotentes en SQL mientras se mantiene el identificador histórico.

**¿Qué pasaría con varios trabajadores?** La implementación entregada usa uno. Para escalar hay que introducir coordinación y partición; no basta aumentar réplicas.

**¿Por qué el perfil local es lento?** Prioriza instalación inmediata. DBM realiza búsqueda lineal y SQLite serializa escrituras; no representa el motor de volumen.

**¿Qué falta antes de producción?** Validación distribuida, servidor HTTP de producción, TLS, identidades nominales, backups probados, política automática de retención y métricas de capacidad.
