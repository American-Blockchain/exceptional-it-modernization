data "azurerm_client_config" "current" {}

data "azurerm_resource_group" "rg" {
  name = "rg-terraform-state" # Update to match your actual RG name
}

# ---------------------------------------------------------
# Observability (OpenTelemetry Backbone)
# ---------------------------------------------------------
resource "azurerm_log_analytics_workspace" "law" {
  name                = "law-ai-foundry-mas"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_application_insights" "app_insights" {
  name                = "appi-ai-foundry-mas"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name
  workspace_id        = azurerm_log_analytics_workspace.law.id
  application_type    = "web"
}

# ---------------------------------------------------------
# Azure AI Foundry (Teacher & Student Models)
# ---------------------------------------------------------
resource "azurerm_cognitive_account" "ai_foundry" {
  name                  = "cog-ai-foundry-mas"
  location              = data.azurerm_resource_group.rg.location
  resource_group_name   = data.azurerm_resource_group.rg.name
  kind                  = "OpenAI"
  sku_name              = "S0"
  custom_subdomain_name = "oai-mas-core-${var.acr_name}" # Improved uniqueness
}

resource "azurerm_cognitive_deployment" "teacher_model" {
  name                 = "gpt-4o"
  cognitive_account_id = azurerm_cognitive_account.ai_foundry.id
  model {
    format  = "OpenAI"
    name    = "gpt-4o"
    version = "2024-05-13"
  }
  scale { type = "Standard" }
}

resource "azurerm_cognitive_deployment" "student_model" {
  name                 = "gpt-4o-mini"
  cognitive_account_id = azurerm_cognitive_account.ai_foundry.id
  model {
    format  = "OpenAI"
    name    = "gpt-4o-mini"
    version = "2024-07-18"
  }
  scale { type = "Standard" }
}

# ---------------------------------------------------------
# Compute Layer & Container Apps
# ---------------------------------------------------------
resource "azurerm_container_app_environment" "mas_env" {
  name                       = "cae-ai-foundry-mas"
  location                   = data.azurerm_resource_group.rg.location
  resource_group_name        = data.azurerm_resource_group.rg.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.law.id
}

# --- Python Specialist Agent ---
resource "azurerm_container_app" "python_specialist" {
  name                         = "ca-python-specialist"
  container_app_environment_id = azurerm_container_app_environment.mas_env.id
  resource_group_name          = data.azurerm_resource_group.rg.name
  revision_mode                = "Single"

  identity {
    type = "SystemAssigned"
  }

  registry {
    server   = azurerm_container_registry.acr.login_server
    identity = "system"
  }

  template {
    container {
      name = "google-agent-worker"
      # Dynamically point to the ACR created in id.tf
      image  = "${azurerm_container_registry.acr.login_server}/python-specialist:latest"
      cpu    = 2.0
      memory = "4.0Gi"

      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.app_insights.connection_string
      }
      env {
        name  = "OTEL_SERVICE_NAME"
        value = "google-agent-specialist"
      }
      env {
        name  = "OTEL_RESOURCE_ATTRIBUTES"
        value = "service.namespace=ai-foundry-mas"
      }
      env {
        name  = "AZURE_OPENAI_ENDPOINT"
        value = azurerm_cognitive_account.ai_foundry.endpoint
      }
    }

    min_replicas = 1
    max_replicas = 10

    custom_scale_rule {
      name             = "http-concurrent-python"
      custom_rule_type = "http"
      metadata         = { concurrentRequests = "20" }
    }
  }

  ingress {
    allow_insecure_connections = false
    external_enabled           = false # Internal VNet only
    target_port                = 8000
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }
}

resource "azurerm_role_assignment" "python_acr_pull" {
  principal_id         = azurerm_container_app.python_specialist.identity[0].principal_id
  role_definition_name = "AcrPull"
  scope                = azurerm_container_registry.acr.id
}

# --- C# Semantic Kernel Orchestrator ---
resource "azurerm_container_app" "csharp_orchestrator" {
  name                         = "ca-csharp-orchestrator"
  container_app_environment_id = azurerm_container_app_environment.mas_env.id
  resource_group_name          = data.azurerm_resource_group.rg.name
  revision_mode                = "Single"

  identity {
    type = "SystemAssigned"
  }

  registry {
    server   = azurerm_container_registry.acr.login_server
    identity = "system"
  }

  template {
    container {
      name   = "sk-orchestrator"
      image  = "${azurerm_container_registry.acr.login_server}/csharp-orchestrator:latest"
      cpu    = 2.0
      memory = "4.0Gi"

      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.app_insights.connection_string
      }
      env {
        name  = "OTEL_SERVICE_NAME"
        value = "semantic-kernel-orchestrator"
      }
      env {
        name  = "OTEL_RESOURCE_ATTRIBUTES"
        value = "service.namespace=ai-foundry-mas"
      }
      env {
        name  = "PYTHON_AGENT_INTERNAL_URL"
        value = "https://${azurerm_container_app.python_specialist.ingress[0].fqdn}"
      }
      env {
        name  = "AZURE_OPENAI_ENDPOINT"
        value = azurerm_cognitive_account.ai_foundry.endpoint
      }
    }

    min_replicas = 1
    max_replicas = 10

    custom_scale_rule {
      name             = "http-concurrent-dotnet"
      custom_rule_type = "http"
      metadata         = { concurrentRequests = "50" }
    }
  }

  ingress {
    allow_insecure_connections = false
    external_enabled           = true # Public facing
    target_port                = 8080
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }
}

resource "azurerm_role_assignment" "csharp_acr_pull" {
  principal_id         = azurerm_container_app.csharp_orchestrator.identity[0].principal_id
  role_definition_name = "AcrPull"
  scope                = azurerm_container_registry.acr.id
}