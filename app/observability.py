import os
import time
import logging
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("observability")

# Almacén en memoria para registro de métricas de producción y latencias
_metrics_records: List[Dict[str, Any]] = []


def setup_observability() -> Dict[str, Any]:
    status = {
        "langsmith_active": False,
        "phoenix_active": False,
        "timestamp": datetime.now().isoformat()
    }

    langsmith_key = os.getenv("LANGCHAIN_API_KEY")
    if langsmith_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        if not os.getenv("LANGCHAIN_PROJECT"):
            os.environ["LANGCHAIN_PROJECT"] = "pre-entrega-7-api"
        status["langsmith_active"] = True

    enable_phoenix = os.getenv("ENABLE_PHOENIX", "false").lower() in ("true", "1", "yes")
    if enable_phoenix:
        try:
            import phoenix as px
            from openinference.instrumentation.langchain import LangChainInstrumentor
            
            collector_endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT")
            if not collector_endpoint:
                session = px.launch_app(port=int(os.getenv("PHOENIX_PORT", "6006")))
            
            LangChainInstrumentor().instrument()
            status["phoenix_active"] = True
        except Exception as e:
            logger.warning(f"Error iniciando Phoenix: {e}")

    return status


def record_execution_metric(
    task_id: str,
    latency_ms: float,
    status: str,
    input_tokens: int = 420,
    output_tokens: int = 180,
    model_name: str = "gemini-3.8-flash"
) -> Dict[str, Any]:
    if "gpt" in model_name.lower():
        cost_input = (input_tokens / 1_000_000) * 0.15
        cost_output = (output_tokens / 1_000_000) * 0.60
    else:
        cost_input = (input_tokens / 1_000_000) * 0.075
        cost_output = (output_tokens / 1_000_000) * 0.30

    total_cost = round(cost_input + cost_output, 6)

    record = {
        "task_id": task_id,
        "timestamp": datetime.now().isoformat(),
        "latency_ms": round(latency_ms, 2),
        "status": status,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cost_usd": total_cost,
        "model": model_name
    }
    _metrics_records.append(record)
    return record


def get_performance_summary() -> Dict[str, Any]:
    """
    Calcula resumen estadístico: cantidad de peticiones, latencias (min, p50, p95, max)
    y costo acumulado / promedio por ejecución.
    """
    if not _metrics_records:
        return {
            "total_requests": 0,
            "latency_p95_ms": 0.0,
            "latency_p50_ms": 0.0,
            "latency_avg_ms": 0.0,
            "total_cost_usd": 0.0,
            "avg_cost_per_run_usd": 0.0,
            "records": []
        }

    latencies = sorted([r["latency_ms"] for r in _metrics_records])
    n = len(latencies)

    idx_p95 = max(0, int(0.95 * n) - 1)
    idx_p50 = max(0, int(0.50 * n) - 1)

    p95 = latencies[idx_p95]
    p50 = latencies[idx_p50]
    avg_latency = sum(latencies) / n

    total_cost = sum(r["cost_usd"] for r in _metrics_records)
    avg_cost = total_cost / n if n > 0 else 0.0

    return {
        "total_requests": n,
        "latency_min_ms": min(latencies),
        "latency_p50_ms": round(p50, 2),
        "latency_p95_ms": round(p95, 2),
        "latency_max_ms": max(latencies),
        "latency_avg_ms": round(avg_latency, 2),
        "total_cost_usd": round(total_cost, 6),
        "avg_cost_per_run_usd": round(avg_cost, 6),
        "recent_records": _metrics_records[-10:]
    }


def trace_step(step_name: str) -> Callable:
    """Decorador para instrumentar y medir tiempos de ejecución en pasos individuales."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                duration = (time.perf_counter() - start) * 1000.0
                logger.debug(f"Paso [{step_name}] completado en {duration:.2f} ms")
                return result
            except Exception as e:
                duration = (time.perf_counter() - start) * 1000.0
                logger.error(f"Paso [{step_name}] falló tras {duration:.2f} ms con error: {e}")
                raise e
        return wrapper
    return decorator
