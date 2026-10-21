import uuid
import logging
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field

from .redis_client import save_job, get_job, list_jobs, get_sync_redis
from .worker import enqueue_agent_task, resume_agent_task
from .hitl import ApprovalRequest, ApprovalResponse
from .observability import setup_observability, get_performance_summary

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    obs_info = setup_observability()
    redis_client = get_sync_redis()
    yield


app = FastAPI(
    title="API de Orquestación Multi-Agente",
    version="1.0.0",
    lifespan=lifespan
)


class TaskCreateRequest(BaseModel):
    query: str
    max_budget: Optional[float] = None


class TaskCreateResponse(BaseModel):
    task_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    query: Optional[str] = None
    max_budget: Optional[float] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    latency_ms: Optional[float] = None
    result: Optional[str] = None
    error: Optional[str] = None
    approval_info: Optional[Dict[str, Any]] = None
    agent_history: Optional[List[Dict[str, Any]]] = None


@app.post("/tasks", response_model=TaskCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_task(request: TaskCreateRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())

    initial_job_data = {
        "task_id": task_id,
        "query": request.query,
        "max_budget": request.max_budget,
        "status": "PENDING",
        "created_at": datetime.now().isoformat(),
        "result": None,
        "error": None
    }
    save_job(task_id, initial_job_data)
    background_tasks.add_task(enqueue_agent_task, task_id, request.query, request.max_budget)

    return TaskCreateResponse(
        task_id=task_id,
        status="PENDING",
        message="Tarea encolada correctamente."
    )


@app.get("/tasks")
async def list_all_tasks(limit: int = 20):
    return list_jobs(limit=limit)


@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    job = get_job(task_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La tarea '{task_id}' no existe."
        )
    return TaskStatusResponse(**job)


@app.post("/tasks/{task_id}/approve", response_model=ApprovalResponse)
async def approve_task(task_id: str, request: ApprovalRequest, background_tasks: BackgroundTasks):
    job = get_job(task_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La tarea '{task_id}' no existe."
        )

    current_status = job.get("status")
    if current_status != "WAITING_APPROVAL":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La tarea no está en espera de aprobación (estado: '{current_status}')"
        )

    background_tasks.add_task(resume_agent_task, task_id, request.approved, request.feedback)

    action_text = "aprobada" if request.approved else "rechazada"
    return ApprovalResponse(
        task_id=task_id,
        status="RESUMING",
        message=f"Intervención {action_text}. Reanudando tarea.",
        feedback=request.feedback
    )


@app.get("/metrics")
async def get_metrics():
    return get_performance_summary()


@app.get("/health")
async def health_check():
    redis_client = get_sync_redis()
    redis_alive = False
    try:
        redis_client.ping()
        redis_alive = True
    except Exception:
        redis_alive = False

    return {
        "status": "healthy",
        "redis_connected": redis_alive
    }
