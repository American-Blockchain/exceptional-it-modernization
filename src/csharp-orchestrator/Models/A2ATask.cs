using System.Text.Json.Serialization;

namespace Orchestrator.Models;

// ---------------------------------------------------------
// A2A Protocol JSON-RPC 2.0 Message Schema
// Spec: https://google.github.io/A2A
// Method: tasks/send
// ---------------------------------------------------------

/// <summary>A single content part within an A2A message.</summary>
public record A2APart(
    [property: JsonPropertyName("type")] string Type,
    [property: JsonPropertyName("text")] string Text
);

/// <summary>An A2A message envelope carrying the user or agent turn.</summary>
public record A2AMessage(
    [property: JsonPropertyName("role")] string Role,
    [property: JsonPropertyName("parts")] A2APart[] Parts
);

/// <summary>The params block for the tasks/send method.</summary>
public record A2ATaskParams(
    [property: JsonPropertyName("id")]      string Id,
    [property: JsonPropertyName("message")] A2AMessage Message
);

/// <summary>
/// The complete A2A JSON-RPC 2.0 request envelope sent over Azure Service Bus.
/// Replaces the proprietary SpecialistPayload, enabling interoperability
/// with any A2A-compliant agent (Google ADK, Semantic Kernel, etc).
/// </summary>
public record A2ARequest(
    [property: JsonPropertyName("jsonrpc")] string JsonRpc,
    [property: JsonPropertyName("id")]      string Id,
    [property: JsonPropertyName("method")]  string Method,
    [property: JsonPropertyName("params")]  A2ATaskParams Params
)
{
    /// <summary>Factory: constructs a standards-compliant tasks/send envelope.</summary>
    public static A2ARequest CreateTasksSend(string taskId, string userText) =>
        new(
            JsonRpc: "2.0",
            Id: taskId,
            Method: "tasks/send",
            Params: new A2ATaskParams(
                Id: taskId,
                Message: new A2AMessage(
                    Role: "user",
                    Parts: [new A2APart(Type: "text", Text: userText)]
                )
            )
        );
}
