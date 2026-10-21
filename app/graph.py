from typing import Literal
from langgraph.graph import StateGraph, START, END

from .state import AgentState
from .agents.supervisor import supervisor_node, validator_node
from .agents.research_agent import research_node
from .agents.analyst_agent import analyst_node
from .hitl import human_approval_node
from .redis_client import get_checkpointer


def route_supervisor(state: AgentState) -> Literal["researcher", "analyst", "human_approval", "validator", "__end__"]:
    decision = state.get("next_agent")
    if decision == "researcher":
        return "researcher"
    elif decision == "analyst":
        return "analyst"
    elif decision == "human_approval":
        return "human_approval"
    elif decision == "validator":
        return "validator"
    elif decision == "FINISH":
        return END
    return END


def route_validator(state: AgentState) -> Literal["supervisor", "__end__"]:
    if state.get("validation_passed", False):
        return END
    return "supervisor"


def build_graph(checkpointer=None):
    if checkpointer is None:
        checkpointer = get_checkpointer()

    workflow = StateGraph(AgentState)

    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("researcher", research_node)
    workflow.add_node("analyst", analyst_node)
    workflow.add_node("human_approval", human_approval_node)
    workflow.add_node("validator", validator_node)

    workflow.add_edge(START, "supervisor")

    workflow.add_conditional_edges(
        "supervisor",
        route_supervisor,
        {
            "researcher": "researcher",
            "analyst": "analyst",
            "human_approval": "human_approval",
            "validator": "validator",
            END: END
        }
    )

    workflow.add_edge("researcher", "supervisor")
    workflow.add_edge("analyst", "supervisor")
    workflow.add_edge("human_approval", "supervisor")

    workflow.add_conditional_edges(
        "validator",
        route_validator,
        {
            END: END,
            "supervisor": "supervisor"
        }
    )

    return workflow.compile(checkpointer=checkpointer)


_compiled_graph = None


def get_agent_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def export_graph_mermaid() -> str:
    app = get_agent_graph()
    return app.get_graph().draw_mermaid()
