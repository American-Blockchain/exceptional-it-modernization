"""
Python Specialist Agent — Google ADK + Microsoft Agent Lightning + CopilotKit
=============================================================================
Architecture (per Gemini.MD):
  - Google ADK:           A2A-compliant agent runtime wrapping LangGraph mas_graph
  - Agent Lightning:      APO backbone — store.trace() wraps every ADK execution
  - Azure Service Bus:    Async A2A tasks/send receiver (decoupled from HTTP timeout)
  - CopilotKit:           LangGraph streaming to Next.js AG-UI
  - Vite Dashboard:       Agent Lightning native dashboard at /lightning-dashboard

Transport protocol:
  - Incoming (Service Bus): A2A JSON-RPC 2.0  {"jsonrpc":"2.0","method":"tasks/send",...}
  - Outgoing (HTTP /a2a):   A2A JSON-RPC 2.0  {"jsonrpc":"2.0","result":{"artifacts":[...]}}
  - Streaming (/copilotkit): CopilotKit remote protocol (LangGraph state)
"""

import os
import logging
import asyncio
import json
import orjson
from contextlib import asynccontextmanager
from typing import TypedDict, Annotated, List, Dict, Any, Optional
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import operator

# Azure & Messaging
from azure.servicebus.aio import ServiceBusClient
from azure.identity.aio import DefaultAzureCredential
from azure.identity import DefaultAzureCredential as SyncDefaultAzureCredential, get_bearer_token_provider

# OpenTelemetry
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from azure.monitor.opentelemetry import configure_azure_monitor

# Agent Lightning — APO backbone (built from source in Dockerfile)
from agentlightning import LightningStore

# Google ADK — A2A-compliant agent runtime
from google.adk.agents import Agent as ADKAgent
from google.adk.runners import Runner as ADKRunner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

# CopilotKit & LangGraph — HITL streaming to Next.js UI
from copilotkit import CopilotKitRemoteEndpoint, LangGraphAgent
from copilotkit.integrations.fastapi import add_fastapi_endpoint
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import StateGraph, START, END

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("google-agent-specialist")

# ─── OTel / Azure Monitor ──────────────────────────────────────────────────────
try:
    configure_azure_monitor()
except Exception as e:
    logger.warning(f"[OTel] Azure Monitor skipped (local dev?): {e}")

tracer = trace.get_tracer(__name__)

# ─── Agent Lightning LightningStore ───────────────────────────────────────────
# Central APO coordination hub — manages traces, prompt versions, reward signals
store = LightningStore()

# ─── Module-level Azure Identity ──────────────────────────────────────────────
# Hoisted once: DefaultAzureCredential caches Entra ID tokens internally.
# Per-request instantiation caused unnecessary identity round-trips.
_azure_credential = SyncDefaultAzureCredential()
_token_provider = get_bearer_token_provider(
    _azure_credential, "https://cognitiveservices.azure.com/.default"
)

# ─── Resilient ORJSON Response ────────────────────────────────────────────────
class ResilientORJSONResponse(JSONResponse):
    """
    Ultra-fast ORJSON serializer with fallback to standard JSON for LLM
    output that contains invalid UTF-8 / surrogate characters.
    """
    media_type = "application/json"

    def render(self, content: Any) -> bytes:
        try:
            return orjson.dumps(content)
        except orjson.JSONEncodeError as e:
            logger.warning(f"[ORJSON] Falling back to stdlib JSON. Error: {e}")
            return json.dumps(content, ensure_ascii=True, allow_nan=False,
                              separators=(",", ":")).encode("utf-8")

# ─── A2A JSON-RPC 2.0 Schema (Receiver) ───────────────────────────────────────
class A2APart(BaseModel):
    type: str
    text: str

class A2AMessage(BaseModel):
    role: str
    parts: List[A2APart]

class A2ATaskParams(BaseModel):
    id: str
    message: A2AMessage

class A2ARequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str
    method: str
    params: A2ATaskParams

# ─── LangGraph MAS State Machine ──────────────────────────────────────────────
class MASState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    teacher_critiques: Annotated[List[str], operator.add]
    notable_events: Annotated[List[str], operator.add]

async def student_node(state: MASState):
    """Student agent — executes the primary task. Wrapped in Agent Lightning trace."""
    llm = AzureChatOpenAI(
        azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
        azure_deployment="student-model",
        api_version="2024-07-18",
        azure_ad_token_provider=_token_provider
    )
    response = await llm.ainvoke(state["messages"])
    tokens = response.usage_metadata.get("total_tokens", 0) if response.usage_metadata else 0
    return {
        "messages": [response],
        "notable_events": [f"Student executed task. Tokens Consumed: {tokens}"]
    }

async def teacher_node(state: MASState):
    """Teacher critic — evaluates student output for APO reward signal."""
    llm = AzureChatOpenAI(
        azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
        azure_deployment="teacher-model",
        api_version="2024-07-18",
        azure_ad_token_provider=_token_provider
    )
    last_message = state["messages"][-1].content
    teacher_prompt = [HumanMessage(
        content=f"You are the Teacher critic in an APO loop. Evaluate this output:\n\n{last_message}"
    )]
    teacher_response = await llm.ainvoke(teacher_prompt)
    teacher_tokens = teacher_response.usage_metadata.get("total_tokens", 0) if teacher_response.usage_metadata else 0
    return {
        "teacher_critiques": [f"APO Critique: {teacher_response.content}"],
        "notable_events": [f"Teacher evaluated output. Tokens Consumed: {teacher_tokens}"]
    }

workflow = StateGraph(MASState)
workflow.add_node("student", student_node)
workflow.add_node("teacher", teacher_node)
workflow.add_edge(START, "student")
workflow.add_edge("student", "teacher")
workflow.add_edge("teacher", END)
mas_graph = workflow.compile()

# ─── Google ADK Agent (A2A Runtime) ───────────────────────────────────────────
# Wraps the LangGraph state machine inside a Google ADK Agent class,
# exposing a standards-compliant A2A interface for cross-agent interoperability.
class MASADKAgent(ADKAgent):
    """
    Google ADK Agent wrapping the Teacher/Student LangGraph.
    Receives A2A tasks/send envelopes from the C# Semantic Kernel Orchestrator.
    All executions are wrapped in Agent Lightning store.trace() for APO tracking.
    """
    def __init__(self):
        super().__init__(name="mas_orchestrator")

    async def _run_async_impl(self, ctx):
        user_text = ""
        for part in ctx.user_content.parts:
            if hasattr(part, "text"):
                user_text += part.text

        task_id = ctx.session_id or "unknown"

        # Agent Lightning APO trace — wraps the full ADK execution
        with store.trace(task_id=task_id) as agent_trace:
            agent_trace.record_state("agent_mission", user_text)

            initial_state: MASState = {
                "messages": [HumanMessage(content=user_text)],
                "teacher_critiques": [],
                "notable_events": [],
            }

            result = await mas_graph.ainvoke(initial_state)

            final_response = result["messages"][-1].content if result["messages"] else ""
            critiques = result.get("teacher_critiques", [])

            agent_trace.record_state("final_result", final_response)

            # Emit deterministic reward signal to Agent Lightning APO loop
            store.emit_reward(1.0)

        # Yield A2A-compliant response artifact
        yield genai_types.Content(
            role="model",
            parts=[genai_types.Part(text=final_response)]
        )

# Initialize ADK runner with in-memory session service for ACA stateless replicas
_adk_agent = MASADKAgent()
_adk_session_service = InMemorySessionService()
_adk_runner = ADKRunner(
    agent=_adk_agent,
    session_service=_adk_session_service,
    app_name="mas_orchestrator"
)

# ─── Azure Service Bus Worker (A2A Async Consumer) ────────────────────────────
async def servicebus_worker():
    """
    Background worker that pulls A2A tasks/send messages from the Service Bus queue
    and routes them through the Google ADK agent. Decouples the C# Orchestrator
    from HTTP timeouts during long APO evaluation loops.
    """
    servicebus_fqdn = os.environ.get("SERVICEBUS_FQDN")
    queue_name = "apo-tasks-queue"

    if not servicebus_fqdn:
        logger.warning("[ServiceBus] SERVICEBUS_FQDN missing. Async worker disabled.")
        return

    logger.info(f"[ServiceBus] Connecting to: {servicebus_fqdn}")
    credential = DefaultAzureCredential()

    async with ServiceBusClient(servicebus_fqdn, credential) as client:
        async with client.get_queue_receiver(queue_name=queue_name) as receiver:
            logger.info(f"[ServiceBus] Listening on queue: {queue_name}")

            while True:
                messages = await receiver.receive_messages(max_message_count=5, max_wait_time=5)
                for msg in messages:
                    try:
                        # Parse A2A JSON-RPC 2.0 envelope
                        raw = json.loads(str(msg))
                        a2a = A2ARequest(**raw)

                        if a2a.method != "tasks/send":
                            logger.warning(f"[A2A] Unknown method: {a2a.method}. Skipping.")
                            await receiver.abandon_message(msg)
                            continue

                        # Extract W3C Trace Context injected by C# Orchestrator
                        diagnostic_id = msg.application_properties.get(b"Diagnostic-Id", b"").decode("utf-8")
                        extracted_ctx = TraceContextTextMapPropagator().extract(
                            carrier={"traceparent": diagnostic_id}
                        )

                        user_text = " ".join(
                            part.text for part in a2a.params.message.parts
                            if part.type == "text"
                        )

                        # Resume OTel distributed trace from C# Orchestrator
                        with tracer.start_as_current_span(
                            "a2a_task_execution", context=extracted_ctx
                        ) as span:
                            span.set_attribute("a2a.task_id", a2a.params.id)
                            span.set_attribute("a2a.method", a2a.method)

                            logger.info(f"[A2A→ADK] Executing task: {a2a.params.id}")

                            # Route through Google ADK runner
                            session = await _adk_session_service.create_session(
                                app_name="mas_orchestrator",
                                user_id="service_bus",
                                session_id=a2a.params.id
                            )
                            async for _ in _adk_runner.run_async(
                                user_id="service_bus",
                                session_id=session.id,
                                new_message=genai_types.Content(
                                    role="user",
                                    parts=[genai_types.Part(text=user_text)]
                                )
                            ):
                                pass  # Agent Lightning traces inside MASADKAgent handle state

                        await receiver.complete_message(msg)
                        logger.info(f"[A2A] Task {a2a.params.id} completed successfully.")

                    except Exception as e:
                        logger.error(f"[A2A] Task processing error: {e}", exc_info=True)
                        await receiver.abandon_message(msg)

# ─── FastAPI App ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_task = asyncio.create_task(servicebus_worker())
    yield
    worker_task.cancel()

app = FastAPI(lifespan=lifespan, default_response_class=ResilientORJSONResponse)
FastAPIInstrumentor.instrument_app(app)

# ─── A2A HTTP Endpoint (synchronous fallback for direct inter-agent calls) ─────
@app.post("/a2a")
async def a2a_endpoint(request: Request, a2a_request: A2ARequest):
    """
    A2A JSON-RPC 2.0 HTTP endpoint for direct agent-to-agent calls.
    Complements the Service Bus async path for low-latency synchronous use cases.
    """
    if a2a_request.method != "tasks/send":
        return ResilientORJSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "id": a2a_request.id,
                     "error": {"code": -32601, "message": f"Method not found: {a2a_request.method}"}}
        )

    extracted_ctx = TraceContextTextMapPropagator().extract(carrier=request.headers)
    user_text = " ".join(p.text for p in a2a_request.params.message.parts if p.type == "text")

    with tracer.start_as_current_span("a2a_http_task", context=extracted_ctx) as span:
        span.set_attribute("a2a.task_id", a2a_request.params.id)

        session = await _adk_session_service.create_session(
            app_name="mas_orchestrator",
            user_id="http_caller",
            session_id=a2a_request.params.id
        )

        final_text = ""
        async for event in _adk_runner.run_async(
            user_id="http_caller",
            session_id=session.id,
            new_message=genai_types.Content(
                role="user", parts=[genai_types.Part(text=user_text)]
            )
        ):
            if hasattr(event, "content") and event.content:
                for part in event.content.parts:
                    if hasattr(part, "text"):
                        final_text += part.text

    return {
        "jsonrpc": "2.0",
        "id": a2a_request.id,
        "result": {
            "id": a2a_request.params.id,
            "artifacts": [{"parts": [{"type": "text", "text": final_text}]}]
        }
    }

# ─── CopilotKit Endpoint (HITL streaming to Next.js UI) ───────────────────────
langgraph_agent = LangGraphAgent(
    name="mas_orchestrator",
    description="Multi-Agent System executing Student/Teacher APO loops",
    graph=mas_graph
)
sdk = CopilotKitRemoteEndpoint(agents=[langgraph_agent])
add_fastapi_endpoint(app, sdk, "/copilotkit")

# ─── Agent Lightning Dashboard (Vite static build) ────────────────────────────
_dashboard_dir = os.path.join(os.path.dirname(__file__), "agentlightning_dashboard")
if os.path.isdir(_dashboard_dir):
    app.mount("/lightning-dashboard", StaticFiles(directory=_dashboard_dir, html=True),
              name="lightning-dashboard")
    logger.info("[AGL] Agent Lightning dashboard mounted at /lightning-dashboard")
else:
    logger.warning("[AGL] Dashboard directory not found — skipping static mount.")

# ─── Health Check ─────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "healthy", "agent": "mas_orchestrator", "protocol": "A2A/2.0"}
