using System.Text.Json.Serialization;

namespace Orchestrator.Models;

public record A2APart(
    [property: JsonPropertyName("type")] string Type,
    [property: JsonPropertyName("text")] string Text
);

public record A2AMessage(
    [property: JsonPropertyName("role")] string Role,
    [property: JsonPropertyName("parts")] A2APart[] Parts
);

public record A2ATaskParams(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("message")] A2AMessage Message
);

public record A2ARequest(
    [property: JsonPropertyName("jsonrpc")] string JsonRpc,
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("method")] string Method,
    [property: JsonPropertyName("params")] A2ATaskParams Params
);
