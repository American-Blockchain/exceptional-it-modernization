using System.ComponentModel;
using System.Diagnostics;
using System.Text.Json;
using Azure.Messaging.ServiceBus;
using Microsoft.SemanticKernel;
using Microsoft.Extensions.Logging;
using Orchestrator.Models;

namespace Orchestrator.Plugins;

public class GoogleAgentPlugin
{
    private readonly ServiceBusSender _sender;
    private readonly ILogger<GoogleAgentPlugin> _logger;

    public GoogleAgentPlugin(ServiceBusClient serviceBusClient, ILogger<GoogleAgentPlugin> logger)
    {
        // Target the specific queue we provisioned in Terraform
        _sender = serviceBusClient.CreateSender("apo-tasks-queue");
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    [KernelFunction]
    [Description("Delegates a specialized, long-running ML task to the Python Google Agent.")]
    public async Task<string> ExecuteSpecialistTaskAsync(
        [Description("The core instruction for the agent")] string intent,
        [Description("The raw input data to process")] string rawInput,
        [Description("The target programming language")] string targetLanguage,
        [Description("Whether to enforce strict execution rules")] bool strictMode = true)
    {
        var activity = Activity.Current;
        var traceId = activity?.TraceId.ToHexString() ?? Guid.NewGuid().ToString("N");
        
        _logger.LogInformation("[Elite-DevOps] Queuing specialist task. TraceId: {TraceId}", traceId);

        var payload = new SpecialistPayload(
            TaskId: traceId,
            AgentRole: "general_specialist",
            Intent: intent,
            Parameters: new Dictionary<string, object>
            {
                { "target_language", targetLanguage },
                { "strict_mode", strictMode }
            },
            Context: new Dictionary<string, string> { { "session_id", "sk_session" } },
            RawInput: rawInput
        );

        var message = new ServiceBusMessage(JsonSerializer.Serialize(payload))
        {
            MessageId = traceId,
            CorrelationId = traceId,
            Subject = "APO_Task_Execution"
        };

        // Inject OpenTelemetry Trace Context directly into the Service Bus application properties
        if (activity != null)
        {
            message.ApplicationProperties["Diagnostic-Id"] = activity.Id;
        }

        await _sender.SendMessageAsync(message);
        
        // Return a correlation string so Semantic Kernel knows the task was safely handed off
        return $"Task successfully queued for Agent Lightning. Tracking ID: {traceId}.";
    }
}