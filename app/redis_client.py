import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("redis_client")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

_redis_sync = None
_is_fake = False


def get_sync_redis():
    global _redis_sync, _is_fake
    if _redis_sync is not None:
        return _redis_sync

    import redis
    try:
        client = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        client.ping()
        _redis_sync = client
        _is_fake = False
        logger.info(f"Conexión exitosa a Redis en {REDIS_URL}")
    except Exception as e:
        logger.warning(f"No se pudo conectar a Redis ({e}). Usando fakeredis como fallback.")
        import fakeredis
        _redis_sync = fakeredis.FakeRedis(decode_responses=True)
        _is_fake = True

    return _redis_sync


def get_checkpointer():
    """Retorna RedisSaver si Redis está disponible, o MemorySaver como fallback."""
    global _is_fake
    client = get_sync_redis()
    if not _is_fake:
        try:
            from langgraph.checkpoint.redis import RedisSaver
            saver = RedisSaver.from_conn_string(REDIS_URL)
            saver.setup()
            return saver
        except Exception as e:
            logger.warning(f"Error inicializando RedisSaver ({e}). Usando MemorySaver.")
    
    from langgraph.checkpoint.memory import MemorySaver
    return MemorySaver()


def save_job(task_id: str, data: Dict[str, Any]) -> None:
    r = get_sync_redis()
    key = f"job:{task_id}"
    payload = json.dumps(data, ensure_ascii=False)
    r.set(key, payload)
    # Mantener registro en set ordenado de tareas
    r.sadd("jobs_index", task_id)


def get_job(task_id: str) -> Optional[Dict[str, Any]]:
    r = get_sync_redis()
    key = f"job:{task_id}"
    raw = r.get(key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def update_job(task_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    job = get_job(task_id)
    if not job:
        job = {"task_id": task_id, "created_at": datetime.now().isoformat()}
    job.update(updates)
    job["updated_at"] = datetime.now().isoformat()
    save_job(task_id, job)
    return job


def list_jobs(limit: int = 50) -> List[Dict[str, Any]]:
    r = get_sync_redis()
    task_ids = list(r.smembers("jobs_index"))
    jobs = []
    for tid in task_ids[:limit]:
        item = get_job(tid)
        if item:
            jobs.append(item)
    # Ordenar por fecha de creación descendente si existe
    jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return jobs
