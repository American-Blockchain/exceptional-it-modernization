using System.ComponentModel;
using System.Diagnostics;
using System.Text.Json;
using Azure.Messaging.ServiceBus;
using Microsoft.SemanticKernel;
using Microsoft.Extensions.Logging;
using Orchestrator.Models;

namespace Orchestrator.Plugins;

/// <summary>
/// Semantic Kernel plugin that delegates specialized ML tasks to the Python Specialist
/// via Azure Service Bus using the A2A (Agent2Agent) JSON-RPC 2.0 protocol.
///
/// A2A Spec: https://google.github.io/A2A
/// Method: tasks/send
/// Transport: Azure Service Bus (apo-tasks-queue)
/// Tracing: W3C Trace Context injected into ApplicationProperties["Diagnostic-Id"]
/// </summary>
public class GoogleAgentPlugin
{
    private readonly ServiceBusSender _sender;
    private readonly ILogger<GoogleAgentPlugin> _logger;

    private static readonly JsonSerializerOptions _jsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        WriteIndented = false  // compact wire format for Service Bus throughput
    };

    public GoogleAgentPlugin(ServiceBusClient serviceBusClient, ILogger<GoogleAgentPlugin> logger)
    {
        _sender = serviceBusClient.CreateSender("apo-tasks-queue");
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    [KernelFunction]
    [Description("Delegates a specialized, long-running ML task to the Python Google ADK Agent via the A2A protocol.")]
    public async Task<string> ExecuteSpecialistTaskAsync(
        [Description("The core instruction for the agent")] string intent,
        [Description("The raw input data to process")] string rawInput,
        [Description("The target programming language")] string targetLanguage,
        [Description("Whether to enforce strict execution rules")] bool strictMode = true)
    {
        var activity = Activity.Current;
        var taskId = activity?.TraceId.ToHexString() ?? Guid.NewGuid().ToString("N");

        _logger.LogInformation(
            "[SK→ADK] Queuing A2A tasks/send. TaskId: {TaskId} | Intent: {Intent}",
            taskId, intent);

        // Build the A2A JSON-RPC 2.0 envelope — standard cross-agent payload
        var userText = $"{intent}\n\nInput: {rawInput}\nLanguage: {targetLanguage}\nStrictMode: {strictMode}";
        var a2aRequest = A2ARequest.CreateTasksSend(taskId, userText);

        var messageBody = JsonSerializer.Serialize(a2aRequest, _jsonOptions);

        var message = new ServiceBusMessage(messageBody)
        {
            MessageId    = taskId,
            CorrelationId = taskId,
            ContentType  = "application/json",
            Subject      = "A2A/tasks/send"   // human-readable Service Bus label
        };

        // Inject W3C Trace Context for distributed OTel waterfall continuity
        // The Python ADK receiver extracts this via TraceContextTextMapPropagator
        if (activity != null)
        {
            message.ApplicationProperties["Diagnostic-Id"]   = activity.Id;
            message.ApplicationProperties["A2A-JsonRpc"]     = "2.0";
            message.ApplicationProperties["A2A-Method"]      = "tasks/send";
        }

        await _sender.SendMessageAsync(message);

        _logger.LogInformation("[SK→ADK] A2A task enqueued successfully. TrackingId: {TaskId}", taskId);
        return $"{{\"status\":\"queued\",\"a2a_task_id\":\"{taskId}\",\"method\":\"tasks/send\"}}";
    }
}