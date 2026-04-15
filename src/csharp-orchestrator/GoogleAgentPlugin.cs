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
        _sender = serviceBusClient.CreateSender("apo-tasks-queue");
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    [KernelFunction]
    [Description("Delegates a specialized, long-running ML task to the Python Google Agent.")]
    public async Task<string> ExecuteSpecialistTaskAsync(
        [Description("The core instruction for the agent")] string intent,
        [Description("The raw input data to process")] string rawInput)
    {
        var activity = Activity.Current;
        var traceId = activity?.TraceId.ToHexString() ?? Guid.NewGuid().ToString("N");
        
        _logger.LogInformation("[Elite-DevOps] Queuing specialist task via A2A protocol. TraceId: {TraceId}", traceId);

        // Construct the A2A JSON-RPC 2.0 Payload
        var a2aRequest = new A2ARequest(
            JsonRpc: "2.0",
            Id: traceId,
            Method: "tasks/send",
            Params: new A2ATaskParams(
                Id: traceId,
                Message: new A2AMessage(
                    Role: "user",
                    Parts: new[] { new A2APart("text", $"{intent}\n\n{rawInput}") }
                )
            )
        );

        var message = new ServiceBusMessage(JsonSerializer.Serialize(a2aRequest))
        {
            MessageId = traceId,
            CorrelationId = traceId,
            Subject = "APO_Task_Execution"
        };

        if (activity != null)
        {
            message.ApplicationProperties["Diagnostic-Id"] = activity.Id;
        }

        await _sender.SendMessageAsync(message);
        
        return $"Task successfully queued for Google ADK. Tracking ID: {traceId}.";
    }
}