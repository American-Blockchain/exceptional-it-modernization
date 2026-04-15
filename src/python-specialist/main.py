import os
import logging
import asyncio
import json
import orjson
from contextlib import asynccontextmanager
from typing import TypedDict, Annotated, List, Dict, Any
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# Azure & Messaging
from azure.servicebus.aio import ServiceBusClient
from azure.identity.aio import DefaultAzureCredential
from azure.identity import DefaultAzureCredential as SyncDefaultAzureCredential, get_bearer_token_provider

# Observability
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from azure.monitor.opentelemetry import configure_azure_monitor

# Agent Lightning & ADK
from agentlightning import LightningStore
from google.adk.agents import BaseAgent as ADKBaseAgent
from google.adk.agents.invocation_context import InvocationContext

# CopilotKit & LangGraph
from copilotkit import CopilotKitRemoteEndpoint
from copilotkit.integrations.fastapi import add_fastapi_endpoint
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
import operator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("google-agent-specialist")

try:
    configure_azure_monitor()
except Exception as e:
    logger.warning(f"[OTel] Azure Monitor configuration skipped: {e}")

tracer = trace.get_tracer(__name__)
store = LightningStore()

_azure_credential = SyncDefaultAzureCredential()
_token_provider = get_bearer_token_provider(
    _azure_credential, "https://cognitiveservices.azure.com/.default"
)

class ResilientORJSONResponse(JSONResponse):
    media_type = "application/json"
    def render(self, content: Any) -> bytes:
        try:
            return orjson.dumps(content)
        except orjson.JSONEncodeError as e:
            return json.dumps(content, ensure_ascii=True, separators=(",", ":")).encode("utf-8")

# ---------------------------------------------------------
# ADK MAS State Machine
# ---------------------------------------------------------
class MASState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    teacher_critiques: Annotated[List[str], operator.add]
    notable_events: Annotated[List[str], operator.add]

async def student_node(state: MASState):
    llm = AzureChatOpenAI(
        azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
        azure_deployment="student-model",
        api_version="2024-07-18",
        azure_ad_token_provider=_token_provider 
    )
    response = await llm.ainvoke(state["messages"])
    tokens = response.usage_metadata.get("total_tokens", 0) if response.usage_metadata else 0
    return {"messages": [response], "notable_events": [f"Student executed task. Tokens Consumed: {tokens}"]}

async def teacher_node(state: MASState):
    llm = AzureChatOpenAI(
        azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
        azure_deployment="teacher-model",
        api_version="2024-07-18",
        azure_ad_token_provider=_token_provider
    )
    last_message = state["messages"][-1].content
    teacher_prompt = [HumanMessage(content=f"You are the Teacher critic in an APO loop. Evaluate: {last_message}")]
    teacher_response = await llm.ainvoke(teacher_prompt)
    teacher_tokens = teacher_response.usage_metadata.get("total_tokens", 0) if teacher_response.usage_metadata else 0
    return {"teacher_critiques": [f"APO Critique: {teacher_response.content}"], "notable_events": [f"Teacher evaluated output. Tokens Consumed: {teacher_tokens}"]}

workflow = StateGraph(MASState)
workflow.add_node("student", student_node)
workflow.add_node("teacher", teacher_node)
workflow.add_edge(START, "student")
workflow.add_edge("student", "teacher")
workflow.add_edge("teacher", END)
mas_graph = workflow.compile()

# Google ADK Wrapper — correct BaseAgent subclass pattern
class MASAgent(ADKBaseAgent):
    """Wraps the compiled LangGraph MAS workflow as an ADK-compliant BaseAgent.
    All execution telemetry is bound to Agent Lightning via store.trace()."""

    def __init__(self):
        super().__init__(name="mas_orchestrator", description="Student/Teacher MAS APO agent")

    async def _run_async_impl(self, ctx: InvocationContext):  # type: ignore[override]
        input_text = ctx.user_content.parts[0].text if ctx.user_content and ctx.user_content.parts else ""
        result = await mas_graph.ainvoke({"messages": [HumanMessage(content=input_text)]})
        from google.adk.events import Event
        from google.genai.types import Content, Part
        final_text = result["messages"][-1].content if result.get("messages") else ""
        yield Event(author=self.name, content=Content(parts=[Part(text=final_text)]))

# ---------------------------------------------------------
# A2A JSON-RPC Worker
# ---------------------------------------------------------
async def servicebus_worker():
    servicebus_fqdn = os.environ.get("SERVICEBUS_FQDN")
    if not servicebus_fqdn: return

    credential = DefaultAzureCredential()
    adk_agent = MASAgent()

    async with ServiceBusClient(servicebus_fqdn, credential) as client:
        async with client.get_queue_receiver(queue_name="apo-tasks-queue") as receiver:
            while True:
                messages = await receiver.receive_messages(max_message_count=5, max_wait_time=5)
                for msg in messages:
                    try:
                        payload_dict = json.loads(str(msg))
                        
                        # Validate JSON-RPC 2.0 A2A Envelope
                        if payload_dict.get("jsonrpc") == "2.0" and payload_dict.get("method") == "tasks/send":
                            params = payload_dict.get("params", {})
                            task_id = params.get("id")
                            parts = params.get("message", {}).get("parts", [])
                            raw_input = parts[0].get("text", "") if parts else ""

                            diagnostic_id = msg.application_properties.get(b"Diagnostic-Id", b"").decode("utf-8")
                            extracted_context = TraceContextTextMapPropagator().extract(carrier={"traceparent": diagnostic_id})

                            with tracer.start_as_current_span("adk_process_a2a_task", context=extracted_context) as span:
                                # Agent Lightning APO Loop Binding
                                with store.trace(task_id=task_id) as agent_trace:
                                    agent_trace.record_state("agent_mission", "A2A Task Execution")
                                    
                                    # ADK Execution
                                    result = await adk_agent.ainvoke({"messages": [HumanMessage(content=raw_input)]})
                                    
                                    agent_trace.record_state("final_result", str(result))
                                    
                                    # Emit objective reward for Agent Lightning APO
                                    store.emit_reward(1.0) 

                        await receiver.complete_message(msg)
                    except Exception as e:
                        logger.error(f"[-] Error processing A2A task: {e}")
                        await receiver.abandon_message(msg)

# ---------------------------------------------------------
# Application Initialization
# ---------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_task = asyncio.create_task(servicebus_worker())
    yield
    worker_task.cancel()

app = FastAPI(lifespan=lifespan, default_response_class=ResilientORJSONResponse, redirect_slashes=False)
FastAPIInstrumentor.instrument_app(app)

# 1. Mount Agent Lightning Dashboard
if os.path.exists("agentlightning_dashboard"):
    app.mount("/lightning-dashboard", StaticFiles(directory="agentlightning_dashboard", html=True))

# 2. CopilotKit Remote Endpoint
sdk = CopilotKitRemoteEndpoint(agents=[MASAgent()])
add_fastapi_endpoint(app, sdk, "/copilotkit")
