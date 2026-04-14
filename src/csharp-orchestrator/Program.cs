using Microsoft.SemanticKernel;
using Orchestrator.Plugins;
using Azure.Monitor.OpenTelemetry.AspNetCore;
using OpenTelemetry.Logs;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;
using Azure.Identity;
using Microsoft.SemanticKernel.Connectors.OpenAI;
using Yarp.ReverseProxy.Configuration;
using Azure.Messaging.ServiceBus;

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

var sbConnectionString = builder.Configuration["SERVICEBUS_CONNECTION_STRING"];
if (string.IsNullOrWhiteSpace(sbConnectionString))
{
    throw new InvalidOperationException("Environment Configuration Error: SERVICEBUS_CONNECTION_STRING must be provided.");
}

// Register the ServiceBusClient cleanly for DI
builder.Services.AddSingleton(new ServiceBusClient(sbConnectionString));
builder.Services.AddTransient<GoogleAgentPlugin>();

// --- 3. Semantic Kernel Orchestration Layer ---
// Note: AddHttpClient<GoogleAgentPlugin> above already registers the plugin as Transient.
// Do NOT re-register with AddScoped — it would strip the typed HttpClient factory.

builder.Services.AddKeyedScoped<Kernel>("AgentKernel", (sp, key) => 
{
    var kernelBuilder = Kernel.CreateBuilder();
    
    // Elite DevOps: Wire the Teacher Brain using Managed Identity
    var endpoint = builder.Configuration["AZURE_OPENAI_ENDPOINT"];
    var deployment = builder.Configuration["AZURE_OPENAI_DEPLOYMENT_NAME"];
    
    if (!string.IsNullOrEmpty(endpoint) && !string.IsNullOrEmpty(deployment))
    {
        kernelBuilder.AddAzureOpenAIChatCompletion(
            deploymentName: deployment,
            endpoint: endpoint,
            credentials: new DefaultAzureCredential()
        );
    }
    
    // Wire the plugin that carries the managed HttpClient from DI
    kernelBuilder.Plugins.AddFromObject(sp.GetRequiredService<GoogleAgentPlugin>());
    return kernelBuilder.Build();
});

// --- NEW: YARP Reverse Proxy Configuration ---
builder.Services.AddReverseProxy()
    .LoadFromMemory(
        routes: new[]
        {
            new RouteConfig()
            {
                RouteId = "copilotkit-stream",
                ClusterId = "python-specialist-cluster",
                // Catch all CopilotKit routes (SSE, WebSockets, standard POSTs)
                Match = new RouteMatch { Path = "/copilotkit/{**catch-all}" } 
            }
        },
        clusters: new[]
        {
            new ClusterConfig()
            {
                ClusterId = "python-specialist-cluster",
                Destinations = new Dictionary<string, DestinationConfig>(StringComparer.OrdinalIgnoreCase)
                {
                    // Dynamically point to the ACA Envoy internal FQDN
                    { "python-backend", new DestinationConfig() { Address = pythonAgentUrl } }
                }
            }
        }
    );

// --- 4. Request Pipeline & Health ---
var app = builder.Build();

// --- NEW: Map the Proxy Middleware ---
app.MapReverseProxy();

app.MapGet("/", () => Results.Ok(new { 
    Status = "Healthy", 
    Component = "Semantic Kernel Orchestrator", 
    TargetSpecialist = pythonAgentUrl 
}));

app.Run();