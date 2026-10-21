from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage
from langgraph.types import interrupt

from .state import AgentState, AgentContribution


class ApprovalRequest(BaseModel):
    approved: bool
    feedback: Optional[str] = None


class ApprovalResponse(BaseModel):
    task_id: str
    status: str
    message: str
    feedback: Optional[str] = None


def evaluate_criticality(state: AgentState) -> tuple[bool, str, str]:
    analysis_data = (state.get("analysis_data") or "").lower()
    research_data = (state.get("research_data") or "").lower()
    query = (state.get("user_query") or "").lower()

    high_end_keywords = ["rtx 4080", "rtx 4090", "ryzen 9", "i9", "alta-entusiasta", "850w", "1000w"]
    for kw in high_end_keywords:
        if kw in research_data or kw in query:
            return True, f"Componente de gama alta ({kw.upper()}) con alto impacto de costo y consumo.", "HIGH"

    if "es_critico\": true" in analysis_data or "supera el presupuesto" in analysis_data:
        return True, "El presupuesto calculado supera el límite de $1.000.000 ARS.", "HIGH"

    return False, "Presupuesto estándar.", "LOW"


def human_approval_node(state: AgentState) -> dict:
    human_approved = state.get("human_approved")

    if human_approved is not None:
        status_text = "APROBADO" if human_approved else "RECHAZADO"
        feedback = state.get("human_feedback") or ""
        msg = f"[HITL]: Decisión humana: {status_text}. Feedback: {feedback}"
        
        contribution: AgentContribution = {
            "agent": "human_approval",
            "action": f"decision_{status_text.lower()}",
            "summary": msg,
            "timestamp": datetime.now().isoformat(),
            "metadata": {"approved": human_approved, "feedback": feedback}
        }
        
        return {
            "requires_human_approval": False,
            "messages": [AIMessage(content=msg, name="human_supervisor")],
            "agent_history": [contribution]
        }

    is_critical, reason, risk_level = evaluate_criticality(state)

    if is_critical:
        human_input = interrupt({
            "action": "APPROVAL_REQUIRED",
            "reason": reason,
            "risk_level": risk_level,
            "summary": "Se requiere autorización para continuar con este presupuesto.",
            "current_data": {
                "research": state.get("research_data"),
                "analysis": state.get("analysis_data")
            }
        })

        approved = human_input.get("approved", True) if isinstance(human_input, dict) else bool(human_input)
        feedback = human_input.get("feedback") if isinstance(human_input, dict) else None

        status_text = "APROBADO" if approved else "RECHAZADO"
        msg = f"[HITL]: Decisión registrada: {status_text}. Feedback: {feedback}"

        contribution: AgentContribution = {
            "agent": "human_approval",
            "action": f"decision_{status_text.lower()}",
            "summary": msg,
            "timestamp": datetime.now().isoformat(),
            "metadata": {"approved": approved, "feedback": feedback}
        }

        return {
            "human_approved": approved,
            "human_feedback": feedback,
            "requires_human_approval": False,
            "messages": [AIMessage(content=msg, name="human_supervisor")],
            "agent_history": [contribution]
        }

    return {
        "requires_human_approval": False,
        "human_approved": True,
        "human_feedback": "Aprobación automática."
    }
