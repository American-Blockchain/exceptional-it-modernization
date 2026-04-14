variable "acr_name" {
  type        = string
  default     = "primeagentacr"
  description = "The name of the Azure Container Registry (must be globally unique and alphanumeric)."
}

variable "identity_name" {
  type        = string
  description = "The name of the User-Assigned Managed Identity."
  default     = "id-github-actions-builder"
}

variable "federated_credential_name" {
  type        = string
  description = "The name of the federated identity credential."
  default     = "github-actions-main-branch"
}

variable "github_subject" {
  type        = string
  description = "The GitHub OIDC subject (e.g., repo:owner/repository:ref:refs/heads/main)."
  validation {
    condition     = can(regex("^repo:.+:.+", var.github_subject))
    error_message = "The github_subject must be in the format 'repo:org/repo:ref:refs/heads/branch' or similar OIDC subject format."
  }
  default = "repo:American-Blockchain/exceptional-it-modernization:ref:refs/heads/main"
}

variable "resource_group_name" {
  type        = string
  description = "The name of the Resource Group."
  default     = "rg-terraform-state"
}

variable "shared_prefix" {
  type        = string
  description = "Prefix for shared resources."
  default     = "ai-foundry-mas"
}

variable "ca_python_name" {
  type        = string
  description = "The name of the Python Specialist Container App."
  default     = "ca-python-specialist"
}

variable "ca_csharp_name" {
  type        = string
  description = "The name of the C# Orchestrator Container App."
  default     = "ca-csharp-orchestrator"
}

variable "teacher_model_name" {
  type        = string
  default     = "gpt-5"
}

variable "teacher_model_version" {
  type        = string
  default     = "2025-08-07" # GA per az cognitiveservices query
}

variable "student_model_name" {
  type        = string
  default     = "gpt-4.1-mini"
}

variable "student_model_version" {
  type        = string
  default     = "2025-04-14" # GA per az cognitiveservices query
}