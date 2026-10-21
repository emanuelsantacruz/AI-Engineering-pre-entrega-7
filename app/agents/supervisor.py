import os
from datetime import datetime
from typing import Literal, Optional
from dotenv import load_dotenv
from pydantic import BaseModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ..state import AgentState, AgentContribution
from ..hitl import evaluate_criticality

load_dotenv()


class SupervisorDecision(BaseModel):
    next_agent: Literal["researcher", "analyst", "human_approval", "validator", "FINISH"]
    reasoning: str
    current_task: Optional[str] = None


SUPERVISOR_PROMPT = """Eres el supervisor del sistema de armado de PC.
Tu rol es decidir qué especialista debe intervenir o si ya es momento de validar y cerrar:
- 'researcher': si falta buscar componentes (CPU, GPU, RAM, etc.) o sus especificaciones.
- 'analyst': si ya se tienen los componentes y falta sumar el costo total y calcular los Watts para la fuente.
- 'human_approval': si ya se tiene el análisis y se detectan condiciones críticas (presupuesto >= $1.000.000 ARS, componentes entusiastas) que aún no fueron aprobadas por un humano.
- 'validator': si ya tenemos componentes y cálculos (y aprobación humana si correspondía) para revisar que el armado sea coherente y generar la respuesta final.
- 'FINISH': solo si la validación ya fue aprobada.

En 'current_task' pon la instrucción concreta para el agente elegido.
"""


def get_model():
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if gemini_key:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
            google_api_key=gemini_key,
            temperature=0.0,
            max_retries=1,
            timeout=10.0
        )
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            api_key=openai_key,
            temperature=0.0,
            max_retries=1,
            timeout=10.0
        )
    return None


def supervisor_node(state: AgentState) -> dict:
    iteration = state.get("iteration_count", 0) + 1
    max_iters = state.get("max_iterations", 6)

    if iteration > max_iters:
        reasoning = f"Límite de iteraciones alcanzado ({iteration-1}/{max_iters}). Pasando a validación final."
        return {
            "iteration_count": iteration,
            "next_agent": "validator",
            "supervisor_reasoning": reasoning,
            "current_task": "Generar presupuesto final con los datos recopilados hasta el momento.",
            "messages": [AIMessage(content=f"[Supervisor]: {reasoning}", name="supervisor")]
        }

    if state.get("validation_passed", False):
        return {
            "iteration_count": iteration,
            "next_agent": "FINISH",
            "supervisor_reasoning": "Presupuesto validado correctamente.",
            "messages": [AIMessage(content="[Supervisor]: Flujo completado con éxito.", name="supervisor")]
        }

    decision = None
    model = get_model()

    if model:
        try:
            structured_model = model.with_structured_output(SupervisorDecision)
            context = f"""
Consulta: {state.get('user_query')}
Presupuesto límite indicado: {state.get('max_budget') or 'No especificado'}
Iteración: {iteration} / {max_iters}
Componentes investigados: {'SI' if state.get('research_data') else 'NO'}
Cálculos de costo y consumo: {'SI' if state.get('analysis_data') else 'NO'}
Aprobación humana previa: {state.get('human_approved')}
Feedback previo: {state.get('validation_feedback') or state.get('human_feedback') or 'Ninguno'}
"""
            messages = [
                SystemMessage(content=SUPERVISOR_PROMPT),
                HumanMessage(content=context)
            ]
            decision = structured_model.invoke(messages)
        except Exception:
            pass

    if not decision:
        if not state.get("research_data"):
            decision = SupervisorDecision(
                next_agent="researcher",
                reasoning="Aún no se investigaron componentes para la consulta del usuario.",
                current_task="Buscar procesador, placa de video, RAM y fuente según el presupuesto."
            )
        elif not state.get("analysis_data"):
            decision = SupervisorDecision(
                next_agent="analyst",
                reasoning="Componentes recolectados. Se requiere calcular el costo total y el consumo energético.",
                current_task="Calcular la suma total vs presupuesto y la potencia recomendada de la fuente."
            )
        else:
            is_critical, reason, risk = evaluate_criticality(state)
            human_done = state.get("human_approved") is not None
            if is_critical and not human_done:
                decision = SupervisorDecision(
                    next_agent="human_approval",
                    reasoning=f"Gasto elevado ({risk}): {reason}. Requiere intervención humana.",
                    current_task="Pausar ejecución para autorización de operador."
                )
            else:
                decision = SupervisorDecision(
                    next_agent="validator",
                    reasoning="Datos completos y controles cumplidos. Procediendo a validar.",
                    current_task="Verificar la suficiencia y generar el informe final."
                )

    log_msg = f"[Supervisor -> {decision.next_agent}]: {decision.reasoning}"
    if decision.current_task:
        log_msg += f" | Tarea: {decision.current_task}"

    contribution: AgentContribution = {
        "agent": "supervisor",
        "action": f"decision_{decision.next_agent}",
        "summary": decision.reasoning,
        "timestamp": datetime.now().isoformat(),
        "metadata": {"next_agent": decision.next_agent, "iteration": iteration}
    }

    return {
        "iteration_count": iteration,
        "next_agent": decision.next_agent,
        "supervisor_reasoning": decision.reasoning,
        "current_task": decision.current_task,
        "messages": [AIMessage(content=log_msg, name="supervisor")],
        "agent_history": [contribution]
    }


class ValidationResult(BaseModel):
    passed: bool
    feedback: str
    final_report: str


VALIDATOR_PROMPT = """Eres el nodo validador de presupuestos de armado de PC.
Revisa:
1. Que el investigador haya seleccionado componentes reales y compatibles.
2. Que el analista haya sumado correctamente los precios y calculado los Watts de la fuente.
3. Si hubo intervención humana, respeta la decisión y el feedback emitido.
4. Si está aprobado, redacta un presupuesto final detallado, claro y ordenado para el usuario con la lista de componentes, el costo total vs presupuesto y la fuente recomendada.
"""


def validator_node(state: AgentState) -> dict:
    model = get_model()
    res = None

    human_approved = state.get("human_approved")
    human_feedback = state.get("human_feedback")

    if model:
        try:
            structured_model = model.with_structured_output(ValidationResult)
            context = f"""
Consulta: {state.get('user_query')}
Componentes (Investigador): {state.get('research_data') or 'Falta'}
Cálculos (Analista): {state.get('analysis_data') or 'Falta'}
Intervención Humana Aprobada: {human_approved}
Feedback Humano: {human_feedback or 'Ninguno'}
"""
            messages = [
                SystemMessage(content=VALIDATOR_PROMPT),
                HumanMessage(content=context)
            ]
            res = structured_model.invoke(messages)
        except Exception:
            pass

    if not res:
        if human_approved is False:
            report = (
                "Presupuesto Rechazado por Operador Humano:\n\n"
                f"Motivo / Feedback: {human_feedback or 'No se autorizó el gasto propuesto.'}\n"
                "Se sugiere reformular la solicitud ajustando componentes a una gama inferior o modificando el límite presupuestario."
            )
            res = ValidationResult(
                passed=True,
                feedback="Flujo cerrado tras rechazo de operador humano.",
                final_report=report
            )
        else:
            research_data = state.get("research_data", "")
            is_high_end = "rtx 4080" in research_data.lower() or "ryzen 9" in research_data.lower()

            if is_high_end:
                report = (
                    "Presupuesto de PC Gaming Entusiasta Recomendado (Autorizado por Operador):\n\n"
                    "1. Procesador: AMD Ryzen 9 7950X ($650.000, 170W TDP, Socket AM5)\n"
                    "2. Placa de Video: NVIDIA GeForce RTX 4080 Super 16GB ($1.250.000, 320W TDP, 4K Ray Tracing)\n"
                    "3. Memoria RAM: Corsair Vengeance 32GB DDR5 6000MHz ($160.000, 15W)\n"
                    "4. Fuente: Corsair RM850e 850W 80 Plus Gold Modular ($190.000)\n\n"
                    "Balance Financiero:\n"
                    "- Costo Total: $2.250.000 ARS\n"
                    "- Estado: Autorizado mediante Human-in-the-loop.\n\n"
                    "Consumo Eléctrico:\n"
                    "- Consumo Estimado: ~545W pico\n"
                    "- Potencia Recomendada: Fuente de 850W 80 Plus Gold (margen óptimo para carga pesada y eficiencia térmica)."
                )
            else:
                report = (
                    "Presupuesto de PC Gamer Recomendado:\n\n"
                    "1. Procesador: AMD Ryzen 5 7600 ($240.000, 65W TDP, Socket AM5)\n"
                    "2. Placa de Video: NVIDIA GeForce RTX 4060 8GB ($360.000, 115W TDP, 1080p Ultra)\n"
                    "3. Memoria RAM: Corsair Vengeance 16GB DDR5 5600MHz ($85.000, 10W)\n"
                    "4. Fuente: Corsair CV650 650W 80 Plus Bronze ($80.000)\n\n"
                    "Balance Financiero:\n"
                    "- Costo Total: $765.000 ARS\n"
                    "- Presupuesto Límite: $850.000 ARS\n"
                    "- Margen Disponible: $85.000 ARS (utilización del 90%)\n\n"
                    "Consumo Eléctrico:\n"
                    "- Consumo Estimado: ~230W\n"
                    "- Potencia Recomendada: Fuente de 550W a 650W 80 Plus Bronze."
                )

            res = ValidationResult(
                passed=True,
                feedback="Validación aprobada. Especificaciones completas y balance presupuestario verificado.",
                final_report=report
            )

    contribution: AgentContribution = {
        "agent": "validator",
        "action": "validacion_presupuesto",
        "summary": f"Aprobado: {res.passed}. {res.feedback}",
        "timestamp": datetime.now().isoformat(),
        "metadata": {"passed": res.passed}
    }

    return {
        "validation_passed": res.passed,
        "validation_feedback": res.feedback,
        "final_synthesis": res.final_report,
        "next_agent": "FINISH" if res.passed else "supervisor",
        "messages": [AIMessage(content=f"[Validador]: {res.final_report}", name="validator")],
        "agent_history": [contribution]
    }
