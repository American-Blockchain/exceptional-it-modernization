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