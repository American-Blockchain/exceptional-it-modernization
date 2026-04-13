using System.ComponentModel;
using System.Diagnostics;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using Microsoft.SemanticKernel;
using Microsoft.Extensions.Logging;
using OpenTelemetry;
using OpenTelemetry.Context.Propagation;
using Orchestrator.Models;

namespace Orchestrator.Plugins;

public class GoogleAgentPlugin
{
    private readonly HttpClient _httpClient;
    private readonly ILogger<GoogleAgentPlugin> _logger;

    public GoogleAgentPlugin(HttpClient httpClient, ILogger<GoogleAgentPlugin> logger)
    {
        _httpClient = httpClient ?? throw new ArgumentNullException(nameof(httpClient));
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
        
        _logger.LogInformation("[Elite-DevOps] Initiating specialist task delegation. TraceId: {TraceId}, Intent: {Intent}", traceId, intent);

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
        
        // Use a relative path; the base address is mandated via DI in Program.cs
        using var request = new HttpRequestMessage(HttpMethod.Post, "execute");
        request.Content = new StringContent(jsonContent, Encoding.UTF8, "application/json");

        // Explicitly inject the W3C Trace Context into the HTTP Request headers
        if (activity != null)
        {
            _logger.LogDebug("[OTel] Resuming trace context from Activity.Current. Injecting W3C headers.");
            Propagators.Default.Inject(
                new PropagationContext(activity.Context, Baggage.Current), 
                request, 
                (req, key, value) => req.Headers.TryAddWithoutValidation(key, value));
        }
        else
        {
            _logger.LogWarning("[OTel] Critical: No active activity found. Distributed trace waterfall will be fragmented contextually.");
        }

        try 
        {
            var response = await _httpClient.SendAsync(request);
            response.EnsureSuccessStatusCode();
            
            _logger.LogInformation("[Elite-DevOps] Specialist task returned successfully. TraceId: {TraceId}", traceId);
            return await response.Content.ReadAsStringAsync();
        }
        catch (HttpRequestException ex)
        {
            _logger.LogCritical(ex, "[A2A-Error] Failed to communicate with Python Specialist agent. BaseAddress: {BaseAddress}, TraceId: {TraceId}", _httpClient.BaseAddress, traceId);
            throw;
        }
    }
}