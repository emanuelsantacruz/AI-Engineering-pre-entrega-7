import os
from datetime import datetime
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.prebuilt import create_react_agent

from ..state import AgentState, AgentContribution
from ..tools.search_tools import search_tools, search_hardware_components

load_dotenv()

RESEARCHER_PROMPT = """Eres el agente especialista en hardware de PC.
Usa la herramienta 'search_hardware_components' para buscar los componentes adecuados (procesador, placa de video, memoria RAM, SSD o fuente) según lo que pide el usuario.
Identifica claramente el modelo de cada pieza, su precio en pesos y su consumo en Watts (TDP). No hagas sumas ni cálculos complejos, solo recopila los componentes y sus especificaciones.
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


def research_node(state: AgentState) -> dict:
    task = state.get("current_task") or state.get("user_query")
    prompt = f"Tarea: {task}\nConsulta del usuario: {state.get('user_query')}"

    model = get_model()
    research_result = None

    if model:
        try:
            sub_agent = create_react_agent(
                model=model,
                tools=search_tools,
                prompt=RESEARCHER_PROMPT
            )
            res = sub_agent.invoke({"messages": [HumanMessage(content=prompt)]})
            final_msg = res["messages"][-1]
            content = final_msg.content
            if isinstance(content, list):
                content = "".join([part.get("text", "") if isinstance(part, dict) else str(part) for part in content])
            research_result = content
        except Exception:
            pass

    if not research_result:
        componentes = search_hardware_components.invoke({"query": task})
        research_result = (
            "Componentes seleccionados para el armado:\n"
            f"{componentes}"
        )

    contribution: AgentContribution = {
        "agent": "researcher",
        "action": "busqueda_componentes",
        "summary": "Selección de componentes de PC con precios y consumo en Watts.",
        "timestamp": datetime.now().isoformat(),
        "metadata": {"task": task}
    }

    return {
        "research_data": research_result,
        "messages": [AIMessage(content=f"[Investigador]: {research_result}", name="researcher")],
        "agent_history": [contribution]
    }
