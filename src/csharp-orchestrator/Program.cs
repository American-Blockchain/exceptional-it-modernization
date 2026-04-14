using Microsoft.SemanticKernel;
using Orchestrator.Plugins;
using Azure.Monitor.OpenTelemetry.AspNetCore;
using OpenTelemetry.Logs;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

var builder = WebApplication.CreateBuilder(args);

// --- 1. Infrastructure Alignment: OpenTelemetry & Observability ---
var appInsightsConnectionString = builder.Configuration["APPLICATIONINSIGHTS_CONNECTION_STRING"];
if (!string.IsNullOrEmpty(appInsightsConnectionString))
{
    builder.Services.AddOpenTelemetry()
        .UseAzureMonitor(options => 
        {
            options.ConnectionString = appInsightsConnectionString;
        })
        .WithTracing(tracing => 
        {
            // Capture Semantic Kernel internal spans for a full A2A trace waterfall
            tracing.AddSource("Microsoft.SemanticKernel*");
        });
}

// --- 2. Managed Networking: Typed HttpClient for Python Specialist ---
var pythonAgentUrl = builder.Configuration["PYTHON_AGENT_INTERNAL_URL"];

// Elite DevOps Assertion: Prevent "blind routing" to localhost.
if (string.IsNullOrWhiteSpace(pythonAgentUrl))
{
    Console.ForegroundColor = ConsoleColor.Red;
    Console.WriteLine("[CRITICAL] PYTHON_AGENT_INTERNAL_URL is missing. The system cannot orchestrate specialist tasks.");
    Console.ResetColor();
    // In a production ACA environment, we want to fail-fast on boot to trigger KEDA/ACA health restart
    throw new InvalidOperationException("Environment Configuration Error: PYTHON_AGENT_INTERNAL_URL must be provided.");
}

builder.Services.AddHttpClient<GoogleAgentPlugin>(client =>
{
    client.BaseAddress = new Uri(pythonAgentUrl);
    client.DefaultRequestHeaders.Add("User-Agent", "SK-Orchestrator-Elite-DevOps");
    client.Timeout = TimeSpan.FromSeconds(60); 
});

// --- 3. Semantic Kernel Orchestration Layer ---
// Note: AddHttpClient<GoogleAgentPlugin> above already registers the plugin as Transient.
// Do NOT re-register with AddScoped — it would strip the typed HttpClient factory.

builder.Services.AddKeyedScoped<Kernel>("AgentKernel", (sp, key) => 
{
    var kernelBuilder = Kernel.CreateBuilder();
    // Wire the plugin that carries the managed HttpClient from DI
    kernelBuilder.Plugins.AddFromObject(sp.GetRequiredService<GoogleAgentPlugin>());
    return kernelBuilder.Build();
});

// --- 4. Request Pipeline & Health ---
var app = builder.Build();

app.MapGet("/", () => Results.Ok(new { 
    Status = "Healthy", 
    Component = "Semantic Kernel Orchestrator", 
    TargetSpecialist = pythonAgentUrl 
}));

app.Run();