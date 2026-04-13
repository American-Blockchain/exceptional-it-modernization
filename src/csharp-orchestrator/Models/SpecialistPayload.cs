using System.Text.Json.Serialization;

namespace Orchestrator.Models;

public record SpecialistPayload(
    [property: JsonPropertyName("task_id")] string TaskId,
    [property: JsonPropertyName("agent_role")] string AgentRole,
    [property: JsonPropertyName("intent")] string Intent,
    [property: JsonPropertyName("parameters")] Dictionary<string, object> Parameters,
    [property: JsonPropertyName("context")] Dictionary<string, string> Context,
    [property: JsonPropertyName("raw_input")] string RawInput
);