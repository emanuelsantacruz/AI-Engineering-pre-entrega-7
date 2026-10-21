import time
import asyncio
import httpx
from typing import List, Dict, Any

API_BASE_URL = "http://127.0.0.1:8000"

CONCURRENT_QUERIES = [
    {
        "query": "Armar PC gamer 1080p económica para esports con presupuesto de $650.000.",
        "max_budget": 650000.0
    },
    {
        "query": "Presupuesto PC para gaming 1080p Ultra con Ryzen 5 y placa RTX 4060, tope $850.000.",
        "max_budget": 850000.0
    },
    {
        "query": "Computadora para edición y diseño con placa RX 7600 y 16GB RAM, tope $800.000.",
        "max_budget": 800000.0
    },
    {
        "query": "PC gaming balanceada para Warzone y Fortnite con procesador Intel i5 y SSD 1TB.",
        "max_budget": 780000.0
    },
    {
        "query": "Armado de PC entusiasta de alta gama con RTX 4080 y Ryzen 9 para jugar en 4K.",
        "max_budget": 2500000.0
    }
]


async def run_single_job(client: httpx.AsyncClient, index: int, query_data: Dict[str, Any]) -> Dict[str, Any]:
    query = query_data["query"]
    budget = query_data.get("max_budget")

    t_start = time.perf_counter()

    post_res = await client.post("/tasks", json={"query": query, "max_budget": budget}, timeout=10.0)
    post_duration_ms = (time.perf_counter() - t_start) * 1000.0

    if post_res.status_code != 202:
        return {
            "index": index,
            "status": "ERROR_POST",
            "error": f"Status {post_res.status_code}: {post_res.text}",
            "latency_ms": post_duration_ms
        }

    task_id = post_res.json()["task_id"]
    print(f"[{index+1}/5] Tarea encolada -> ID: {task_id[:8]}... ({post_duration_ms:.2f} ms)")

    poll_start = time.perf_counter()
    timeout_limit = 120.0
    final_status = "PENDING"
    approval_handled = False

    while (time.perf_counter() - poll_start) < timeout_limit:
        await asyncio.sleep(0.5)
        get_res = await client.get(f"/tasks/{task_id}", timeout=10.0)
        if get_res.status_code != 200:
            continue

        job_data = get_res.json()
        status_val = job_data.get("status")

        # Manejo de Human-in-the-loop si la tarea entra en pausa crítica
        if status_val == "WAITING_APPROVAL" and not approval_handled:
            print(f"[{index+1}/5] Tarea {task_id[:8]}... entr\u00f3 en WAITING_APPROVAL (HITL). Enviando aprobaci\u00f3n...")
            approve_res = await client.post(
                f"/tasks/{task_id}/approve",
                json={"approved": True, "feedback": "Autorizado armado entusiasta por operador humano."},
                timeout=10.0
            )
            approval_handled = True
            continue

        if status_val in ("DONE", "FAILED"):
            final_status = status_val
            break

    total_latency_ms = (time.perf_counter() - t_start) * 1000.0

    return {
        "index": index + 1,
        "task_id": task_id,
        "query": query[:45] + "...",
        "status": final_status,
        "post_time_ms": round(post_duration_ms, 2),
        "total_latency_ms": round(total_latency_ms, 2),
        "hitl": approval_handled
    }


async def main():
    print("=" * 70)
    print("INICIANDO PRUEBA DE CARGA: 5 PETICIONES CONCURRENTES (PRE-ENTREGA 7)")
    print(f"Target: {API_BASE_URL}")
    print("=" * 70)

    async with httpx.AsyncClient(base_url=API_BASE_URL) as client:
        # Verificar estado previo de salud
        try:
            health = await client.get("/health", timeout=3.0)
            print(f"Health check: {health.json()}\n")
        except Exception as e:
            print(f"Error conectando a la API en {API_BASE_URL}: {e}")
            print("Asegurate de haber levantado la API con:")
            print("uvicorn app.main:app --reload")
            return

        overall_start = time.perf_counter()

        # Lanzar las 5 peticiones concurrentes
        tasks = [
            run_single_job(client, i, q)
            for i, q in enumerate(CONCURRENT_QUERIES)
        ]
        results = await asyncio.gather(*tasks)

        overall_time = time.perf_counter() - overall_start

    print("\n" + "=" * 70)
    print("RESULTADOS DE LA CORRIDA CONCURRENTE")
    print("=" * 70)
    print(f"{'#':<3} | {'Task ID':<10} | {'Estado':<8} | {'HITL':<5} | {'POST (ms)':<10} | {'Total (ms)':<10} | {'Consulta':<20}")
    print("-" * 75)

    latencies = []
    for r in results:
        lat = r.get("total_latency_ms", 0.0)
        latencies.append(lat)
        hitl_str = "S\u00ed" if r.get("hitl") else "No"
        print(f"{r['index']:<3} | {r.get('task_id', 'N/A')[:8]:<10} | {r['status']:<8} | {hitl_str:<5} | {r.get('post_time_ms', 0):<10} | {lat:<10} | {r.get('query', '')}")

    latencies.sort()
    n = len(latencies)
    idx_p95 = max(0, int(0.95 * n) - 1)
    p95 = latencies[idx_p95]
    p50 = latencies[max(0, int(0.50 * n) - 1)]
    avg = sum(latencies) / n if n > 0 else 0.0

    print("-" * 75)
    print(f"Tiempo total de la prueba: {overall_time:.2f} s")
    print(f"Latencia M\u00ednima:          {min(latencies):.2f} ms")
    print(f"Latencia P50 (Mediana):   {p50:.2f} ms")
    print(f"Latencia P95:             {p95:.2f} ms")
    print(f"Latencia Promedio:        {avg:.2f} ms")
    print("=" * 70)

    # Consultar m\u00e9tricas de observabilidad registradas en la API
    async with httpx.AsyncClient(base_url=API_BASE_URL) as client:
        try:
            metrics_res = await client.get("/metrics")
            if metrics_res.status_code == 200:
                m = metrics_res.json()
                print("\nM\u00c9TRICAS DE OBSERVABILIDAD REGISTRADAS EN LA API:")
                print(f"- Peticiones registradas: {m.get('total_requests')}")
                print(f"- Latencia p95 calculada: {m.get('latency_p95_ms')} ms")
                print(f"- Costo promedio por ejecuci\u00f3n: ${m.get('avg_cost_per_run_usd')} USD")
                print(f"- Costo total de la corrida:     ${m.get('total_cost_usd')} USD")
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
