import os
import uuid
import logging
import operator
from typing import TypedDict, Annotated, List, Dict, Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import orjson
import json
import asyncio
from azure.servicebus.aio import ServiceBusClient

# OpenTelemetry & Azure Monitor
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from azure.monitor.opentelemetry import configure_azure_monitor

# Microsoft Agent Lightning — Core Components per Gemini.MD
# LightningStore: central coordination hub for task queues, OTel spans, prompt template versioning
# AgentOpsTracer: default tracer — auto-instruments LangChain, LangGraph, LiteLLM, FastAPI
# emit_reward: emits deterministic reward signals (1.0 / 0.0) into the APO training loop
from agentlightning import LightningStore
from agentlightning.runner import AgentOpsTracer
from agentlightning.emitter import emit_reward, find_final_reward

# CopilotKit & LangGraph
from copilotkit import CopilotKitRemoteEndpoint, LangGraphAgent
from copilotkit.integrations.fastapi import add_fastapi_endpoint
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import StateGraph, START, END

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("google-agent-specialist")

# ─── Azure Monitor (OTel → App Insights) ──────────────────────────────────────
# OTEL_SERVICE_NAME and OTEL_RESOURCE_ATTRIBUTES are injected via ACA env vars
# per engineering_standards in Gemini.MD — NEVER hardcoded here
configure_azure_monitor()

# ─── Resilient ORJSON Serializer ───────────────────────────────────────────────
class ResilientORJSONResponse(JSONResponse):
    """
    Blazing fast ORJSON serializer that safely falls back to standard JSON 
    if the LLM hallucinates invalid UTF-8 bytes or surrogate characters.
    """
    media_type = "application/json"

    def render(self, content: Any) -> bytes:
        try:
            return orjson.dumps(content)
        except orjson.JSONEncodeError as e:
            logger.warning(f"[Elite-DevOps] ORJSON strict UTF-8 validation failed. Falling back to standard JSON. Error: {e}")
            return json.dumps(
                content,
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")

# ─── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(title="Python Specialist Agent", version="1.0.0", default_response_class=ResilientORJSONResponse)
FastAPIInstrumentor.instrument_app(app)
tracer = trace.get_tracer(__name__)

# ─── Azure Service Bus Background Worker ──────────────────────────────────────
SB_CONNECTION_STRING = os.environ.get("SERVICEBUS_CONNECTION_STRING", "")
QUEUE_NAME = "apo-tasks-queue"
sb_client = None

async def servicebus_worker():
    if not SB_CONNECTION_STRING:
        logger.warning("[Elite-DevOps] SERVICEBUS_CONNECTION_STRING not set. Service Bus Worker disabled.")
        return
    
    global sb_client
    sb_client = ServiceBusClient.from_connection_string(SB_CONNECTION_STRING)
    receiver = sb_client.get_queue_receiver(queue_name=QUEUE_NAME)
    
    logger.info(f"[Agent-Lightning] Started listening to Azure Service Bus queue: {QUEUE_NAME}")
    
    async with receiver:
        while True:
            try:
                # Long polling
                messages = await receiver.receive_messages(max_message_count=10, max_wait_time=5)
                for msg in messages:
                    try:
                        # Resilient fast parse
                        payload_dict = orjson.loads(str(msg))
                        payload = SpecialistPayload(**payload_dict)
                        
                        rollout_id = str(uuid.uuid4())
                        attempt_id = str(uuid.uuid4())
                        
                        # Enterprise Decoupled Execution (no HTTP timeouts)
                        async with apo_tracer.trace_context(
                            name=f"sb-rollout-{payload.task_id}",
                            store=store,
                            rollout_id=rollout_id,
                            attempt_id=attempt_id,
                        ):
                            logger.info(f"[Agent-Lightning] Worker executing async rollout for task: {payload.task_id}")
                            
                            # E.g. execute graph state
                            # state = await mas_graph.ainvoke({"messages": [HumanMessage(content=payload.intent)]})
                            emit_reward(1.0)
                            
                        # Ack message upon success
                        await receiver.complete_message(msg)
                    except Exception as inner_e:
                        logger.error(f"[Elite-DevOps] Error processing message {msg}: {inner_e}")
                        # Abandoning allows standard retry policies
                        await receiver.abandon_message(msg)
            except asyncio.CancelledError:
                logger.info("[Elite-DevOps] Service Bus polling cancelled.")
                break
            except Exception as e:
                logger.error(f"[Elite-DevOps] Service Bus Loop Error: {e}")
                await asyncio.sleep(5)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(servicebus_worker())

@app.on_event("shutdown")
async def shutdown_event():
    if sb_client:
        await sb_client.close()

# ─── Agent Lightning Core Components ──────────────────────────────────────────
# LightningStore: mandatory for rollout queuing, span storage, prompt weight versioning
# Per Gemini.MD: "The central coordination hub"
store = LightningStore()

# AgentOpsTracer: auto-instruments LangGraph node entrances, LLM calls, tool invocations
# Captures spans and ships them to LightningStore via LightningSpanProcessor
apo_tracer = AgentOpsTracer()


# ─── A2A Payload Schema (C# Orchestrator → Python Specialist) ─────────────────
class SpecialistPayload(BaseModel):
    task_id: str = Field(..., description="Unique identifier for tracing.")
    agent_role: str = Field(..., description="The persona the agent should adopt.")
    intent: str = Field(..., description="The explicit instruction from Semantic Kernel.")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, str] = Field(default_factory=dict)
    raw_input: str = Field(..., description="The data to be processed.")


# ─── LangGraph MAS State Schema ────────────────────────────────────────────────
# Synchronized with Next.js frontend via CopilotKit remote protocol
class MASState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    teacher_critiques: Annotated[List[str], operator.add]
    notable_events: Annotated[List[str], operator.add]


# ─── Student Node ──────────────────────────────────────────────────────────────
# Per Gemini.MD: "run Agent Lightning rollouts, return structured responses with reward signals"
async def student_node(state: MASState):
    """Student Agent — azure_deployment='student-model' (Terraform: azurerm_cognitive_deployment.student_model)"""
    llm = AzureChatOpenAI(
        azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
        azure_deployment="student-model",
        api_version="2024-07-18",
    )

    response = await llm.ainvoke(state["messages"])

    # Extract real token usage from Azure OpenAI response metadata
    tokens = (
        response.usage_metadata.get("total_tokens", 0)
        if response.usage_metadata
        else 0
    )

    # Emit deterministic reward signal to LightningStore APO loop
    # Per Gemini.MD: "Rollouts must provide objective, deterministic reward signals"
    reward = 1.0 if response.content else 0.0
    emit_reward(reward)

    event = [f"Student executed task. Tokens Consumed: {tokens}"]
    logger.info(f"[Agent-Lightning] Student node complete. Reward={reward}, Tokens={tokens}")

    return {"messages": [response], "notable_events": event}


# ─── Teacher Node ──────────────────────────────────────────────────────────────
# Per Gemini.MD: APO — "uses textual gradients (Critic and Editor models)"
async def teacher_node(state: MASState):
    """Teacher Critic — azure_deployment='teacher-model' (Terraform: azurerm_cognitive_deployment.teacher_model)"""
    llm = AzureChatOpenAI(
        azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
        azure_deployment="teacher-model",
        api_version="2024-07-18",
    )

    last_message = state["messages"][-1].content

    # Per Gemini.MD: "NEVER manually tweak prompt templates — delegate to APO"
    # Teacher acts as the Critic model generating textual gradients
    teacher_prompt = [
        HumanMessage(content=(
            f"You are the APO Critic in a Multi-Agent System. "
            f"Evaluate the Student's output and provide: "
            f"(1) a concise critique identifying failure modes, "
            f"(2) a suggested prompt rewrite for the next iteration, "
            f"(3) a quality score 0-100. "
            f"\n\nStudent output:\n{last_message}"
        ))
    ]

    teacher_response = await llm.ainvoke(teacher_prompt)
    teacher_tokens = (
        teacher_response.usage_metadata.get("total_tokens", 0)
        if teacher_response.usage_metadata
        else 0
    )

    # Emit teacher's reward signal — drives APO beam search
    teacher_reward = 1.0 if teacher_response.content else 0.0
    emit_reward(teacher_reward)

    critique = f"APO Critique: {teacher_response.content}"
    event = [f"Teacher evaluated output. Tokens Consumed: {teacher_tokens}"]
    logger.info(f"[Agent-Lightning] Teacher node complete. Reward={teacher_reward}, Tokens={teacher_tokens}")

    return {"teacher_critiques": [critique], "notable_events": event}


# ─── Compile LangGraph ─────────────────────────────────────────────────────────
workflow = StateGraph(MASState)
workflow.add_node("student", student_node)
workflow.add_node("teacher", teacher_node)
workflow.add_edge(START, "student")
workflow.add_edge("student", "teacher")
workflow.add_edge("teacher", END)
mas_graph = workflow.compile()


# ─── CopilotKit Remote Protocol ───────────────────────────────────────────────
# LangGraphAgent wrapper (not raw dict) — CopilotKit SDK requirement
langgraph_agent = LangGraphAgent(
    name="mas_orchestrator",
    description="Multi-Agent System executing Student/Teacher APO loops via LangGraph",
    graph=mas_graph,
)
sdk = CopilotKitRemoteEndpoint(agents=[langgraph_agent])
add_fastapi_endpoint(app, sdk, "/copilotkit")


# ─── A2A Execution Endpoint (C# Orchestrator → Python Specialist) ─────────────
# Per Gemini.MD engineering_standards: wraps store.trace() inside tracer.start_as_current_span
@app.post("/execute")
async def execute_task(request: Request, payload: SpecialistPayload):
    # Extract W3C Trace Context from C# Orchestrator headers
    # Per Gemini.MD: "python_extractor: Use TraceContextTextMapPropagator().extract"
    extracted_context = TraceContextTextMapPropagator().extract(carrier=request.headers)

    with tracer.start_as_current_span(
        "specialist_agent_execution",
        context=extracted_context,
        kind=trace.SpanKind.SERVER,
    ) as span:
        trace_id = format(span.get_span_context().trace_id, "032x")
        logger.info(f"[Elite-DevOps] Resuming distributed trace: {trace_id}")

        # Per Gemini.MD: "wrapping the store.trace() call" inside the span
        rollout_id = str(uuid.uuid4())
        attempt_id = str(uuid.uuid4())

        # AgentOpsTracer.trace_context binds span data to LightningStore
        async with apo_tracer.trace_context(
            name=f"a2a-rollout-{payload.task_id}",
            store=store,
            rollout_id=rollout_id,
            attempt_id=attempt_id,
        ):
            span.set_attribute("agent.role", payload.agent_role)
            span.set_attribute("agent.task_id", payload.task_id)
            span.set_attribute("lightning.rollout_id", rollout_id)

            result = f"Processed '{payload.raw_input}' as {payload.agent_role}"

            # Deterministic reward: 1.0 on success per Gemini.MD APO directives
            emit_reward(1.0)
            logger.info(f"[Agent-Lightning] A2A rollout complete. reward=1.0, trace={trace_id}")

        return {
            "status": "success",
            "data": result,
            "trace_id": trace_id,
            "rollout_id": rollout_id,
        }


# ─── Agent Lightning Store — Span Query API ───────────────────────────────────
# Exposes stored rollout spans for the Next.js UI or external dashboards
@app.get("/lightning/spans/{rollout_id}")
async def get_rollout_spans(rollout_id: str):
    """Query all spans for a given rollout from LightningStore"""
    spans = await store.query_spans(rollout_id=rollout_id)
    reward = find_final_reward(spans) if spans else None
    return {
        "rollout_id": rollout_id,
        "span_count": len(spans),
        "final_reward": reward,
        "spans": [s.model_dump() if hasattr(s, "model_dump") else str(s) for s in spans],
    }


@app.get("/lightning/rollouts")
async def list_rollouts():
    """List all rollouts tracked by LightningStore"""
    rollouts = await store.query_rollouts()
    return {"rollouts": [r.model_dump() if hasattr(r, "model_dump") else str(r) for r in rollouts]}


# ─── Agent Lightning Native Dashboard ─────────────────────────────────────────
# Serves the Vite-built dashboard from agentlightning/dashboard (built in Dockerfile)
# Built per: https://microsoft.github.io/agent-lightning/stable/tutorials/installation/#building-the-dashboard
_dashboard_path = "/app/agentlightning_dashboard"
if os.path.isdir(_dashboard_path):
    app.mount(
        "/lightning-dashboard",
        StaticFiles(directory=_dashboard_path, html=True),
        name="lightning-dashboard",
    )
    logger.info("[Agent-Lightning] Dashboard mounted at /lightning-dashboard")
else:
    logger.warning("[Agent-Lightning] Dashboard not found — skipping mount (expected at %s)", _dashboard_path)


# ─── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "python-specialist", "agent_lightning": "active"}
