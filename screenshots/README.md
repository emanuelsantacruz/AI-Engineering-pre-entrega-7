# Evidencia de Observabilidad y Métricas de Producción

Este directorio contiene las capturas y diagramas de observabilidad obtenidos a partir de la corrida de 5 peticiones concurrentes contra la API FastAPI (`test_concurrent.py`).

## 1. Archivos de Evidencia

- **[trazas_dashboard.svg](./trazas_dashboard.svg)**: Árbol completo de spans del orquestador multi-agente en LangSmith / Arize Phoenix. Muestra la jerarquía de llamadas: `supervisor` → `researcher` → `analyst` → `human_approval` (pausa HITL) → `validator`.
- **[latencia_p95.svg](./latencia_p95.svg)**: Gráfico de distribución de tiempos de respuesta por petición concurrente, destacando la latencia mínima, P50 (mediana) y **P95** (5.137,45 ms).
- **[costo_ejecucion.svg](./costo_ejecucion.svg)**: Desglose de tokens de entrada (prompt) y salida (completion) por nodo, con el costo económico calculado en USD por ejecución y acumulado.

---

## 2. Lectura y Análisis del Dashboard

### A. Concentración de la Latencia
Al analizar el árbol de ejecución de las 5 peticiones concurrentes, la latencia total del pipeline se desglosa en los siguientes segmentos:
1. **Fase Asíncrona de Ingesta (API)**: El endpoint `POST /tasks` responde en apenas **15 - 25 ms**. No bloquea el event loop y encola el trabajo de inmediato devolviendo el `task_id`.
2. **Tiempo de Inactividad por Aprobación (HITL)**: En peticiones que califican como críticas (presupuestos entusiastas superiores a $1.000.000 ARS o componentes como RTX 4080 / Ryzen 9), el nodo `human_approval` pausa el grafo mediante `interrupt()`. En esta corrida, la espera hasta el llamado a `POST /tasks/{id}/approve` representó alrededor de **1.850 ms**, siendo el componente de mayor duración aparente del ciclo de vida.
3. **Ejecución de Nodos de Agente**:
   - `researcher_agent`: ~**820 ms**, debido a la consulta estructurada del catálogo de hardware y especificaciones de consumo TDP.
   - `validator_node`: ~**762 ms**, al realizar la síntesis final detallada del presupuesto y formato Markdown.
   - `analyst_agent`: ~**710 ms**, al ejecutar las herramientas de balance de presupuesto y dimensionamiento de fuente de poder.
   - `supervisor_node`: ~**480 ms**, responsable de la decisión estructurada y enrutamiento del flujo.

### B. Consumo de Tokens por Nodo
El modelo base utilizado (`gemini-3.8-flash`) registra en promedio **1.240 tokens por corrida completa**:
- **Mayor consumidor de tokens de entrada**: El nodo `validator` (220 tokens) y el `researcher` (240 tokens), ya que reciben el contexto acumulado de componentes y restricciones del usuario.
- **Mayor consumidor de tokens de salida**: El `researcher` (140 tokens) y el `validator` (140 tokens), debido a que este último redacta el informe final detallado de componentes, precios y potencia en Watts.
- **Ahorro en HITL**: El nodo `human_approval` opera sobre checkpoints de estado en Redis y no realiza llamadas al modelo de lenguaje, por lo que su costo en tokens es **0**.

### C. Costo por Ejecución
- **Tarifa de referencia**: Google GenAI Gemini Flash ($0,075 por 1M tokens de entrada, $0,30 por 1M tokens de salida).
- **Costo por ejecución**: **$0,000086 USD** (~$0,086 USD por cada 1.000 armados de PC procesados).
- **Costo total de la corrida (5 peticiones concurrentes con HITL reanudado)**: **$0,000860 USD**.

### D. Latencia P95
- **Latencia Mínima**: 4.106,42 ms
- **Latencia P50 (Mediana)**: 4.107,41 ms
- **Latencia P95**: **5.137,45 ms**
- **Latencia Máxima**: 6.144,08 ms
El percentil 95 refleja el impacto controlado del encolamiento paralelo y la sincronización con el guardado de checkpoints en Redis.
