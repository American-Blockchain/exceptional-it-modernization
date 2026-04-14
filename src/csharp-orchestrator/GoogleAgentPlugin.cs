using System.ComponentModel;
using System.Diagnostics;
using System.Text.Json;
using Microsoft.SemanticKernel;
using Microsoft.Extensions.Logging;
using OpenTelemetry;
using OpenTelemetry.Context.Propagation;
using Orchestrator.Models;
using Azure.Messaging.ServiceBus;

namespace Orchestrator.Plugins;

public class GoogleAgentPlugin
{
    private readonly ServiceBusClient _serviceBusClient;
    private readonly ILogger<GoogleAgentPlugin> _logger;
    private const string QueueName = "apo-tasks-queue";

    public GoogleAgentPlugin(ServiceBusClient serviceBusClient, ILogger<GoogleAgentPlugin> logger)
    {
        _serviceBusClient = serviceBusClient ?? throw new ArgumentNullException(nameof(serviceBusClient));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    [KernelFunction]
    [Description("Delegates a specialized task to the Python Google Agent.")]
    public async Task<string> ExecuteSpecialistTaskAsync(
        [Description("The core instruction for the agent")] string intent,
        [Description("The raw input data to process")] string rawInput,
        [Description("The target programming language")] string targetLanguage,
        [Description("Whether to enforce strict execution rules")] bool strictMode = true)
    {
        // Extract the OpenTelemetry TraceId to unify the distributed trace
        var activity = Activity.Current;
        var traceId = activity?.TraceId.ToHexString() ?? Guid.NewGuid().ToString("N");
        
        _logger.LogInformation("[Elite-DevOps] Initiating async specialist task delegation via Service Bus. TraceId: {TraceId}, Intent: {Intent}", traceId, intent);

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

        var jsonContent = JsonSerializer.Serialize(payload);
        var message = new ServiceBusMessage(jsonContent)
        {
            MessageId = traceId,
            ContentType = "application/json"
        };
        
        // Explicitly inject the W3C Trace Context into the Service Bus Message application properties
        if (activity != null)
        {
            _logger.LogDebug("[OTel] Resuming trace context from Activity.Current. Injecting W3C properties into Service Bus message.");
            Propagators.DefaultTextMapPropagator.Inject(
                new PropagationContext(activity.Context, Baggage.Current), 
                message, 
                (msg, key, value) => msg.ApplicationProperties.Add(key, value));
        }
        else
        {
            _logger.LogWarning("[OTel] Critical: No active activity found. Distributed trace waterfall will be fragmented contextually.");
        }

        try 
        {
            await using var sender = _serviceBusClient.CreateSender(QueueName);
            await sender.SendMessageAsync(message);
            
            _logger.LogInformation("[Elite-DevOps] Specialist task successfully queued via Service Bus. TraceId: {TraceId}", traceId);
            return $"Task queued successfully. TraceId: {traceId}. Awaiting Python Specialist offline resolution.";
        }
        catch (Exception ex)
        {
            _logger.LogCritical(ex, "[A2A-Error] Failed to communicate with Service Bus Queue {QueueName}. TraceId: {TraceId}", QueueName, traceId);
            throw;
        }
    }
}