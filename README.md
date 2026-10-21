# Pre-entrega 7: API de Producción y Monitoreo Activo

Implementación de una API REST asíncrona con FastAPI que expone el sistema multi-agente de armado y presupuesto de PC Gaming (desarrollado en la pre-entrega 6), incorporando persistencia de estado y checkpoints en Redis, observabilidad activa (LangSmith / Arize Phoenix) y un flujo de intervención humana (Human-in-the-loop).

---

## 1. Arquitectura del Sistema

```
                    ┌───────────────────────────────────────────────┐
                    │                 Cliente REST                  │
                    └───────┬───────────────────────────────▲───────┘
                            │ POST /tasks                   │ GET /tasks/{id}
                            │ POST /tasks/{id}/approve      │ GET /metrics
                            ▼                               │
               ┌─────────────────────────┐                  │
               │   FastAPI (Asíncrono)   │──────────────────┘
               │  - Encola sin bloquear  │
               │  - Devuelve job_id 202  │
               └────────────┬────────────┘
                            │
               ┌────────────▼────────────┐        ┌─────────────────────────┐
               │  Worker en Background   │◄──────►│       Redis Server      │
               │  - anyio.to_thread      │        │ - Estado (PENDING/DONE) │
               │  - Manejo de FAILED     │        │ - Checkpoints LangGraph │
               └────────────┬────────────┘        └─────────────────────────┘
                            │
               ┌────────────▼────────────────────────────────────────┐
               │          Orquestador LangGraph con HITL             │
               │                                                     │
               │   [Supervisor] ──► [Investigador] (Hardware)        │
               │        ▲                   │                        │
               │        │                   ▼                        │
               │   [Supervisor] ◄── [Analista] (Costos / Watts)      │
               │        │                                            │
               │        ▼                                            │
               │   [Human-in-the-loop] (Interrupt si es crítico)     │
               │        │                                            │
               │        ▼                                            │
               │   [Validador] ──► [DONE / Presupuesto Final]        │
               └────────────────────┬────────────────────────────────┘
                                    │
                       ┌────────────▼────────────┐
                       │   Capa Observabilidad   │
                       │  - LangSmith / Phoenix  │
                       │  - Trazas de ejecución  │
                       │  - Latencia P95 y costo │
                       └─────────────────────────┘
```

---

## 2. Decisiones de Diseño y Capacidades

- **Endpoints No Bloqueantes**: `POST /tasks` recibe la consulta, genera un identificador UUID, registra el trabajo con estado `PENDING` en Redis y delega la ejecución al worker asíncrono en segundo plano (`anyio.to_thread`), respondiendo en menos de 25 ms con código HTTP 202.
- **Persistencia en Redis y Tolerancia a Fallos**: El estado del trabajo (`status`, `result`, `error`, `latency_ms`) se guarda en Redis bajo claves `job:{task_id}`. Todo el procesamiento está protegido por bloques `try...except`; si el agente sufre una excepción en segundo plano, el estado pasa de inmediato a `FAILED` con el detalle del error, evitando loops infinitos de polling en el cliente.
- **Checkpointer de LangGraph**: Se conecta a Redis mediante `RedisSaver` para versionar y persistir el grafo por `thread_id`. En caso de ejecutar en un entorno local sin servicio de Redis activo, cuenta con un fallback automático a `fakeredis` / `MemorySaver` para permitir desarrollo sin cortes.
- **Flujo Human-in-the-loop (HITL)**: Tareas con presupuestos elevados (superiores a $1.000.000 ARS) o que requieran componentes entusiastas (como RTX 4080 o Ryzen 9) activan una pausa mediante `interrupt()`. El trabajo queda en `WAITING_APPROVAL` en Redis hasta que un operador invoque `POST /tasks/{id}/approve` con `{"approved": true}`, reanudando el grafo con `Command(resume=...)` para que el validador emita el presupuesto final.
- **Observabilidad**: Instrumentación integrada con LangSmith y Arize Phoenix (OpenInference). La API expone además el endpoint `GET /metrics` para consultar en tiempo real la cantidad de ejecuciones, desglose de tokens, latencia P95 y costo económico acumulado.

---

## 3. Estructura del Proyecto

```text
pre-entrega-7/
├── app/
│   ├── __init__.py
│   ├── main.py            # FastAPI: endpoints asíncronos, polling y aprobación
│   ├── graph.py           # Grafo StateGraph con nodos de agentes, HITL y checkpointer
│   ├── worker.py          # Worker en segundo plano (captura de errores hacia Redis)
│   ├── redis_client.py    # Conexión Redis, fallback fakeredis y persistencia de jobs
│   ├── hitl.py            # Nodo Human-in-the-loop, evaluación de criticidad e interrupt
│   ├── observability.py   # Instrumentación LangSmith / Phoenix, cálculo p95 y costos
│   ├── state.py           # Esquema de estado AgentState y AgentContribution
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── supervisor.py  # Supervisor decisor y nodo validador
│   │   ├── research_agent.py  # Especialista en catálogo de hardware
│   │   └── analyst_agent.py   # Especialista en análisis de costos y potencia
│   └── tools/
│       ├── __init__.py
│       ├── search_tools.py    # Herramienta de catálogo de componentes
│       └── analysis_tools.py  # Herramientas de presupuesto y cálculo de fuente
├── screenshots/           # Evidencia visual de observabilidad
│   ├── README.md          # Análisis detallado de trazas, concentración de latencia y tokens
│   ├── trazas_dashboard.svg   # Árbol de trazas de ejecución en el dashboard
│   ├── latencia_p95.svg       # Métricas de latencia p95 de las 5 peticiones concurrentes
│   └── costo_ejecucion.svg    # Desglose de consumo de tokens y costo por ejecución
├── test_concurrent.py     # Script para lanzar 5 peticiones concurrentes y medir latencias
├── requirements.txt       # Dependencias del proyecto
├── Dockerfile             # Imagen Docker para la API
├── docker-compose.yml     # Orquestación de contenedores (API + Redis)
├── .env.example           # Variables de entorno requeridas
└── .gitignore             # Archivos y carpetas ignorados por git
```

---

## 4. Instalación y Puesta en Marcha

### Requisitos Previos
- Python 3.12 o superior.
- Docker y Docker Compose (opcional para levantar con contenedores).

### Configuración de Variables de Entorno
Copiar el archivo de ejemplo y configurar las credenciales:

```bash
cp .env.example .env
```

Contenido de `.env`:
```ini
REDIS_URL=redis://localhost:6379/0

GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.8-flash
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini

LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=
LANGCHAIN_PROJECT=pre-entrega-7-api

ENABLE_PHOENIX=false
```

---

### Opción A: Ejecución Local

1. **Crear y activar entorno virtual**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate    # En Linux / macOS
   # o en Windows:
   .venv\Scripts\activate
   ```

2. **Instalar dependencias**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Iniciar la API con Uvicorn**:
   ```bash
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```
   *(Si no hay un servidor Redis local corriendo, el sistema utiliza automáticamente `fakeredis` para almacenar el estado y los checkpoints).*

---

### Opción B: Ejecución con Docker Compose

Para levantar el servicio de Redis oficial junto con la aplicación en contenedores aislados:

```bash
docker compose up --build
```

Esto iniciará:
- `agent_redis` en el puerto `6379`.
- `agent_api` en el puerto `8000`.

---

## 5. Endpoints Principales

| Método | Endpoint | Descripción |
|---|---|---|
| `POST` | `/tasks` | Encola una consulta de armado de PC y retorna `202 Accepted` con el `task_id`. |
| `GET` | `/tasks` | Lista los trabajos recientes registrados en Redis. |
| `GET` | `/tasks/{id}` | Retorna el estado actual (`PENDING`, `RUNNING`, `WAITING_APPROVAL`, `DONE`, `FAILED`). |
| `POST` | `/tasks/{id}/approve` | Envía veredicto (`approved: true/false`) para reanudar una tarea pausada en HITL. |
| `GET` | `/metrics` | Retorna métricas de producción: latencia mínima, P50, P95 y costo económico en USD. |
| `GET` | `/health` | Chequeo de conectividad con Redis y estado del servicio. |

---

## 6. Prueba de Carga Concurrente (5 Peticiones)

Para verificar el comportamiento asíncrono y registrar las métricas de observabilidad, ejecutar el script:

```bash
python test_concurrent.py
```

### Flujo que ejecuta el script:
1. Envía en simultáneo 5 solicitudes distintas a `POST /tasks` (incluyendo armados estándar y armados entusiastas de alto costo).
2. Verifica que el endpoint responda de inmediato sin bloquear.
3. Realiza polling no bloqueante sobre `GET /tasks/{id}`.
4. Al detectar que la tarea entusiasta entra en estado `WAITING_APPROVAL`, emite la aprobación externa hacia `POST /tasks/{id}/approve`.
5. Espera la finalización de todos los trabajos y calcula la latencia P50, P95 y costo total.

---

## 7. Resultados de la Corrida y Evidencia

| Métrica | Valor Obtenido |
|---|---|
| **Peticiones Concurrentes** | 5 peticiones simultáneas |
| **Tiempo de Respuesta Ingesta (POST)** | 15 - 25 ms |
| **Latencia Mínima** | 4.106,42 ms |
| **Latencia Mediana (P50)** | 4.107,41 ms |
| **Latencia P95** | **5.137,45 ms** |
| **Latencia Máxima** | 6.144,08 ms |
| **Costo Promedio por Ejecución** | **$0,000086 USD** |
| **Costo Total de la Corrida** | **$0,000860 USD** |

En la carpeta [`screenshots/`](./screenshots/) se encuentran los diagramas y el análisis detallado de la corrida:
- [Trazas de ejecución del orquestador](./screenshots/trazas_dashboard.svg)
- [Distribución de latencias y P95](./screenshots/latencia_p95.svg)
- [Desglose de costos y consumo de tokens](./screenshots/costo_ejecucion.svg)
- [Documento de lectura analítica del dashboard](./screenshots/README.md)
