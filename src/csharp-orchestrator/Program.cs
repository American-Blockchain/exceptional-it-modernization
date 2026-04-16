using Microsoft.SemanticKernel;
using Orchestrator.Plugins;
using Azure.Monitor.OpenTelemetry.AspNetCore;
using OpenTelemetry.Logs;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;
using Azure.Identity;
using Microsoft.SemanticKernel.Connectors.OpenAI;
using Yarp.ReverseProxy.Configuration;
using Yarp.ReverseProxy.Transforms;
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

var servicebusFqdn = builder.Configuration["SERVICEBUS_FQDN"];
if (string.IsNullOrWhiteSpace(servicebusFqdn))
{
    throw new InvalidOperationException("Environment Configuration Error: SERVICEBUS_FQDN must be provided.");
}

// Register the ServiceBusClient cleanly for DI using passwordless Identity
// Elite DevOps: Specifying the ClientId to prevent ambiguity in dual-identity environments
var credentialOptions = new DefaultAzureCredentialOptions();
var managedIdentityClientId = "0fd15bdb-be06-40a2-9dd8-059bfb0d239c"; // Orchestrator User-Assigned Identity
if (!string.IsNullOrEmpty(managedIdentityClientId))
{
    credentialOptions.ManagedIdentityClientId = managedIdentityClientId;
}

builder.Services.AddSingleton(new ServiceBusClient(servicebusFqdn, new DefaultAzureCredential(credentialOptions)));
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

// --- NEW: YARP Reverse Proxy Configuration (VNet Direct — Dapr not enabled) ---
builder.Services.AddReverseProxy()
    .LoadFromMemory(
        routes: new[]
        {
            new RouteConfig()
            {
                RouteId = "copilotkit-route",
                ClusterId = "python-specialist-cluster",
                Match = new RouteMatch { Path = "/copilotkit/{**catch-all}" },
                Transforms = new[]
                {
                    // Do NOT forward the Vercel/Orchestrator host header to FastAPI.
                    // CopilotKit agent discovery compares the Host header to its own
                    // registered base URL — a mismatch returns empty agents: [].
                    new Dictionary<string, string> { { "RequestHeaderOriginalHost", "false" } }
                }
            }
        },
        clusters: new[]
        {
            new ClusterConfig()
            {
                ClusterId = "python-specialist-cluster",
                // Elite DevOps: Trust the internal VNet certificates
                HttpClient = new HttpClientConfig { DangerousAcceptAnyServerCertificate = true },
                Destinations = new Dictionary<string, DestinationConfig>(StringComparer.OrdinalIgnoreCase)
                {
                    // Direct VNet FQDN — sole authoritative destination
                    // (Dapr sidecar not enabled in this ACA environment)
                    { "vnet-primary", new DestinationConfig() { Address = pythonAgentUrl.EndsWith("/") ? pythonAgentUrl : pythonAgentUrl + "/" } }
                }
            }
        }
    )
    .ConfigureHttpClient((context, handler) =>
    {
        // Enable server-side redirect following to mask internal FQDNs from the browser
        handler.AllowAutoRedirect = true;
    });

// --- 4. Request Pipeline & Health ---
var app = builder.Build();

// --- NEW: Map the Proxy Middleware ---
app.MapReverseProxy();

app.MapGet("/", () => Results.Ok(new { 
    Status = "Healthy", 
    Component = "Semantic Kernel Orchestrator", 
    TargetSpecialist = pythonAgentUrl 
}));

// --- ELITE DEVOPS: MAS APO Test Trigger ---
app.MapPost("/api/test/orchestrate", async (GoogleAgentPlugin plugin) =>
{
    var testTraceId = $"TEST-APO-{Guid.NewGuid().ToString("N")[..8]}";
    var intent = "Standardize this executive summary to align with American Blockchain branding guidelines.";
    var input = "American Blockchain (ABC) is a leader in blockchain modernization for the public sector. We focus on transparency and high-fidelity ledger systems.";
    
    var result = await plugin.ExecuteSpecialistTaskAsync(intent, input);
    
    return Results.Ok(new 
    { 
        Message = "APO Test Task Successfully Triggered",
        TraceId = testTraceId,
        PluginResponse = result
    });
});

app.Run();