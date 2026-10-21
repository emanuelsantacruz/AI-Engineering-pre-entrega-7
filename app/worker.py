import time
import logging
from typing import Optional, Dict, Any
from anyio import to_thread
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from .state import AgentState
from .graph import get_agent_graph
from .redis_client import update_job, get_job
from .observability import record_execution_metric

logger = logging.getLogger("worker")


def _sync_run_task(task_id: str, query: str, max_budget: Optional[float] = None) -> None:
    start_time = time.perf_counter()
    update_job(task_id, {
        "status": "RUNNING",
        "started_at": time.time()
    })

    config = {"configurable": {"thread_id": task_id}}
    app = get_agent_graph()

    initial_state = {
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "max_budget": max_budget or 850000.0,
        "iteration_count": 0,
        "max_iterations": 6,
        "agent_history": [],
        "validation_passed": False,
        "requires_human_approval": False,
        "human_approved": None,
        "human_feedback": None,
    }

    try:
        app.invoke(initial_state, config=config)
        state_snapshot = app.get_state(config)

        has_interrupt = False
        interrupt_value = None
        if state_snapshot.tasks:
            for t in state_snapshot.tasks:
                if getattr(t, "interrupts", None):
                    has_interrupt = True
                    interrupt_value = t.interrupts[0].value
                    break

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        if has_interrupt:
            update_job(task_id, {
                "status": "WAITING_APPROVAL",
                "approval_info": interrupt_value,
                "latency_ms": round(duration_ms, 2)
            })
            record_execution_metric(task_id, duration_ms, status="WAITING_APPROVAL")
            return

        final_values = state_snapshot.values
        final_report = final_values.get("final_synthesis")
        history = final_values.get("agent_history", [])

        update_job(task_id, {
            "status": "DONE",
            "result": final_report,
            "agent_history": history,
            "latency_ms": round(duration_ms, 2)
        })
        record_execution_metric(task_id, duration_ms, status="DONE")

    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        logger.error(f"Error en tarea {task_id}: {e}")
        update_job(task_id, {
            "status": "FAILED",
            "error": str(e),
            "latency_ms": round(duration_ms, 2)
        })
        record_execution_metric(task_id, duration_ms, status="FAILED")


def _sync_resume_task(task_id: str, approved: bool, feedback: Optional[str] = None) -> None:
    start_time = time.perf_counter()
    update_job(task_id, {
        "status": "RUNNING",
        "resumed_at": time.time()
    })

    config = {"configurable": {"thread_id": task_id}}
    app = get_agent_graph()

    try:
        resume_payload = {"approved": approved, "feedback": feedback}
        app.invoke(Command(resume=resume_payload), config=config)

        state_snapshot = app.get_state(config)
        final_values = state_snapshot.values
        final_report = final_values.get("final_synthesis")
        history = final_values.get("agent_history", [])
        duration_ms = (time.perf_counter() - start_time) * 1000.0

        update_job(task_id, {
            "status": "DONE",
            "result": final_report,
            "agent_history": history,
            "latency_ms": round(duration_ms, 2)
        })
        record_execution_metric(task_id, duration_ms, status="DONE")

    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        logger.error(f"Error reanudando {task_id}: {e}")
        update_job(task_id, {
            "status": "FAILED",
            "error": str(e),
            "latency_ms": round(duration_ms, 2)
        })
        record_execution_metric(task_id, duration_ms, status="FAILED")


async def enqueue_agent_task(task_id: str, query: str, max_budget: Optional[float] = None) -> None:
    await to_thread.run_sync(_sync_run_task, task_id, query, max_budget)


async def resume_agent_task(task_id: str, approved: bool, feedback: Optional[str] = None) -> None:
    await to_thread.run_sync(_sync_resume_task, task_id, approved, feedback)
