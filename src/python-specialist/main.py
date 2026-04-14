import os
import logging
import asyncio
import json
import orjson
from contextlib import asynccontextmanager
from typing import TypedDict, Annotated, List, Dict, Any
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import operator

# Azure & Messaging Imports
from azure.servicebus.aio import ServiceBusClient
from azure.identity.aio import DefaultAzureCredential

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

# Initialize Azure Monitor for OpenTelemetry
try:
    configure_azure_monitor()
except Exception as e:
    logger.warning(f"[OTel] Azure Monitor configuration skipped (local dev?): {e}")

tracer = trace.get_tracer(__name__)
store = LightningStore()

# ---------------------------------------------------------
# Resilient ORJSON Serializer
# ---------------------------------------------------------
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

# ---------------------------------------------------------
# Payload Schema
# ---------------------------------------------------------
class SpecialistPayload(BaseModel):
    task_id: str = Field(..., description="Unique identifier for tracing.")
    agent_role: str = Field(..., description="The persona the Google Agent should adopt.")
    intent: str = Field(..., description="The explicit instruction from Semantic Kernel.")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, str] = Field(default_factory=dict)
    raw_input: str = Field(..., description="The data to be processed.")

def run_google_agent_logic(role, intent, data, params):
    # Core execution/rollout logic for Agent Lightning would go here
    return f"Processed {data} as {role}"

# ---------------------------------------------------------
# Asynchronous Service Bus Worker (The Decoupled Engine)
# ---------------------------------------------------------
async def servicebus_worker():
    servicebus_fqdn = os.environ.get("SERVICEBUS_FQDN")
    queue_name = "apo-tasks-queue"

    if not servicebus_fqdn:
        logger.warning("[Elite-DevOps] SERVICEBUS_FQDN missing. Async worker disabled.")
        return

    logger.info(f"[*] Connecting to Azure Service Bus: {servicebus_fqdn}")
    credential = DefaultAzureCredential()
    
    # Run the client in a persistent connection loop
    async with ServiceBusClient(servicebus_fqdn, credential) as client:
        async with client.get_queue_receiver(queue_name=queue_name) as receiver:
            logger.info(f"[*] Started listening to Service Bus Queue: {queue_name}")
            
            while True:
                # Pull batches of messages with backpressure handling
                messages = await receiver.receive_messages(max_message_count=5, max_wait_time=5)
                for msg in messages:
                    try:
                        # 1. Deserialize
                        payload_dict = json.loads(str(msg))
                        payload = SpecialistPayload(**payload_dict)

                        # 2. Extract OpenTelemetry Context injected by C# Orchestrator
                        # C# Activity.Id maps to W3C traceparent header
                        diagnostic_id = msg.application_properties.get(b"Diagnostic-Id", b"").decode("utf-8")
                        extracted_context = TraceContextTextMapPropagator().extract(carrier={"traceparent": diagnostic_id})

                        # 3. Resume the Distributed Trace
                        with tracer.start_as_current_span("servicebus_process_apo_task", context=extracted_context) as span:
                            trace_id = format(span.get_span_context().trace_id, '032x')
                            logger.info(f"[Elite-DevOps] Resuming distributed trace from Service Bus: {trace_id}")
                            
                            # 4. Execute the Agent Lightning Loop
                            with store.trace(task_id=payload.task_id) as agent_trace:
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

                        # 5. Acknowledge and remove from queue
                        await receiver.complete_message(msg)
                        logger.info(f"[+] Successfully processed APO task {payload.task_id}")

                    except Exception as e:
                        logger.error(f"[-] Error processing APO task: {e}")
                        # Abandon the message so it goes back to the queue (or dead-letter queue)
                        await receiver.abandon_message(msg)

# ---------------------------------------------------------
# FastAPI App Lifecycle & Routes
# ---------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Boot up the Service Bus worker in the background
    worker_task = asyncio.create_task(servicebus_worker())
    yield
    # Graceful shutdown
    worker_task.cancel()

app = FastAPI(lifespan=lifespan, default_response_class=ResilientORJSONResponse)
FastAPIInstrumentor.instrument_app(app)

# Retaining the HTTP fallback endpoint for local sync testing
@app.post("/execute")
async def execute_task(request: Request, payload: SpecialistPayload):
    extracted_context = TraceContextTextMapPropagator().extract(carrier=request.headers)
    with tracer.start_as_current_span("specialist_agent_execution", context=extracted_context, kind=trace.SpanKind.SERVER) as span:
        trace_id = format(span.get_span_context().trace_id, '032x')
        with store.trace(task_id=payload.task_id) as agent_trace:
            result = run_google_agent_logic(payload.agent_role, payload.intent, payload.raw_input, payload.parameters)
            agent_trace.record_state("final_result", result)
        return {"status": "success", "data": result, "trace_id": trace_id}

# ---------------------------------------------------------
# LangGraph MAS State Machine (CopilotKit Remote Protocol)
# ---------------------------------------------------------
class MASState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    teacher_critiques: Annotated[List[str], operator.add]
    notable_events: Annotated[List[str], operator.add]

async def student_node(state: MASState):
    llm = AzureChatOpenAI(azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"), azure_deployment="student-model", api_version="2024-07-18")
    response = await llm.ainvoke(state["messages"])
    tokens = response.usage_metadata.get("total_tokens", 0) if response.usage_metadata else 0
    return {"messages": [response], "notable_events": [f"Student executed task. Tokens Consumed: {tokens}"]}

async def teacher_node(state: MASState):
    llm = AzureChatOpenAI(azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"), azure_deployment="teacher-model", api_version="2024-07-18")
    last_message = state["messages"][-1].content
    teacher_prompt = [HumanMessage(content=(f"You are the Teacher critic in an APO loop. Evaluate the following output. Output:\n\n{last_message}"))]
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

langgraph_agent = LangGraphAgent(name="mas_orchestrator", description="Multi-Agent System executing Student/Teacher APO loops", graph=mas_graph)
sdk = CopilotKitRemoteEndpoint(agents=[langgraph_agent])
add_fastapi_endpoint(app, sdk, "/copilotkit")
