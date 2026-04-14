import os
import logging
from typing import TypedDict, Annotated, List
from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
from typing import Dict, Any
import operator

# OpenTelemetry & Observability imports
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from azure.monitor.opentelemetry import configure_azure_monitor

# Agent Lightning imports (APO-enabled)
from agentlightning import LightningStore

# CopilotKit & LangGraph Imports
from copilotkit import CopilotKitRemoteEndpoint, LangGraphAgent
from copilotkit.integrations.fastapi import add_fastapi_endpoint
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END

# Configure Elite DevOps Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("google-agent-specialist")

# Initialize Azure Monitor
configure_azure_monitor()

app = FastAPI()
FastAPIInstrumentor.instrument_app(app)
tracer = trace.get_tracer(__name__)
store = LightningStore()

# ---------------------------------------------------------
# Existing A2A Execution Endpoint (C# Orchestrator → Python)
# ---------------------------------------------------------
class SpecialistPayload(BaseModel):
    task_id: str = Field(..., description="Unique identifier for tracing.")
    agent_role: str = Field(..., description="The persona the Google Agent should adopt.")
    intent: str = Field(..., description="The explicit instruction from Semantic Kernel.")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, str] = Field(default_factory=dict)
    raw_input: str = Field(..., description="The data to be processed.")

def run_google_agent_logic(role, intent, data, params):
    # Simulated execution logic
    return f"Processed {data} as {role}"

@app.post("/execute")
async def execute_task(request: Request, payload: SpecialistPayload):
    extracted_context = TraceContextTextMapPropagator().extract(carrier=request.headers)
    
    with tracer.start_as_current_span(
        "specialist_agent_execution", 
        context=extracted_context,
        kind=trace.SpanKind.SERVER
    ) as span:
        trace_id = format(span.get_span_context().trace_id, '032x')
        logger.info(f"[Elite-DevOps] Resuming distributed trace: {trace_id}")

        with store.trace(task_id=payload.task_id) as agent_trace:
            # Teacher's critique/APO feedback would be processed here
            agent_trace.record_state("agent_mission", payload.intent)
            
            result = run_google_agent_logic(
                role=payload.agent_role,
                intent=payload.intent,
                data=payload.raw_input,
                params=payload.parameters,
            )

            agent_trace.record_state("final_result", result)
            span.set_attribute("agent.role", payload.agent_role)
            span.set_attribute("agent.task_id", payload.task_id)

        return {
            "status": "success", 
            "data": result, 
            "trace_id": trace_id
        }

# ---------------------------------------------------------
# LangGraph MAS State Machine (CopilotKit Remote Protocol)
# ---------------------------------------------------------

# 1. Define the Shared State Schema
# This state is automatically synchronized with the Next.js frontend via CopilotKit
class MASState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    teacher_critiques: Annotated[List[str], operator.add]
    notable_events: Annotated[List[str], operator.add]


# 2. Define the Agent Nodes
async def student_node(state: MASState):
    """The Student Agent — maps to Terraform deployment 'student-model'"""
    llm = AzureChatOpenAI(
        azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
        azure_deployment="student-model",  # Maps to azurerm_cognitive_deployment.student_model
        api_version="2024-07-18"
    )
    
    response = await llm.ainvoke(state["messages"])
    
    # Extract native token usage from the Azure OpenAI response metadata
    tokens = response.usage_metadata.get("total_tokens", 0) if response.usage_metadata else 0
    
    # Broadcast the metric to the Next.js UI via CopilotKit state sync
    event = [f"Student executed task. Tokens Consumed: {tokens}"]
    
    return {"messages": [response], "notable_events": event}


async def teacher_node(state: MASState):
    """The Teacher Critic — maps to Terraform deployment 'teacher-model'"""
    llm = AzureChatOpenAI(
        azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
        azure_deployment="teacher-model",  # Maps to azurerm_cognitive_deployment.teacher_model
        api_version="2024-07-18"
    )
    
    # The teacher evaluates the student's last response
    last_message = state["messages"][-1].content
    
    teacher_prompt = [
        HumanMessage(content=(
            f"You are the Teacher critic in an APO (Automated Prompt Optimization) loop. "
            f"Evaluate the following student output and provide a concise critique with a quality score out of 100. "
            f"Student output:\n\n{last_message}"
        ))
    ]
    
    teacher_response = await llm.ainvoke(teacher_prompt)
    
    # Extract teacher token usage
    teacher_tokens = teacher_response.usage_metadata.get("total_tokens", 0) if teacher_response.usage_metadata else 0
    
    critique = f"APO Critique: {teacher_response.content}"
    event = [f"Teacher evaluated output. Tokens Consumed: {teacher_tokens}"]
    
    return {"teacher_critiques": [critique], "notable_events": event}


# 3. Compile the LangGraph
workflow = StateGraph(MASState)
workflow.add_node("student", student_node)
workflow.add_node("teacher", teacher_node)

workflow.add_edge(START, "student")
workflow.add_edge("student", "teacher")
workflow.add_edge("teacher", END)

mas_graph = workflow.compile()


# 4. Expose the Graph via CopilotKit using the LangGraphAgent SDK wrapper
langgraph_agent = LangGraphAgent(
    name="mas_orchestrator",
    description="Multi-Agent System executing Student/Teacher APO loops via LangGraph",
    graph=mas_graph,
)

sdk = CopilotKitRemoteEndpoint(
    agents=[langgraph_agent]
)

# Route added for the CopilotKit Frontend to stream thoughts
add_fastapi_endpoint(app, sdk, "/copilotkit")
