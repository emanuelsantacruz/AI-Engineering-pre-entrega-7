import operator
from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict
from langchain_core.messages import AnyMessage


class AgentContribution(TypedDict):
    agent: str
    action: str
    summary: str
    timestamp: Optional[str]
    metadata: Optional[Dict[str, Any]]


class AgentState(TypedDict):
    messages: Annotated[List[AnyMessage], operator.add]
    user_query: str
    max_budget: Optional[float]
    current_task: Optional[str]
    research_data: Optional[str]
    analysis_data: Optional[str]
    agent_history: Annotated[List[AgentContribution], operator.add]
    next_agent: Literal["researcher", "analyst", "human_approval", "validator", "FINISH"]
    supervisor_reasoning: Optional[str]
    validation_passed: bool
    validation_feedback: Optional[str]
    final_synthesis: Optional[str]
    iteration_count: int
    max_iterations: int
    requires_human_approval: bool
    human_approval_reason: Optional[str]
    human_approved: Optional[bool]
    human_feedback: Optional[str]
    critical_risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    total_cost: Optional[float]
    total_watts: Optional[int]
