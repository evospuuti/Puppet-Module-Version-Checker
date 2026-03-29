# AVD Version Tracker

Stand: 2026-03-27

## Runner

| Name | Ort | Tracked | Neueste Release | Status | Link |
|------|-----|---------|-----------------|--------|------|
| **Terraform** | Runner (vorinstalliert) | `>= 1.14.0, < 2.0.0` | *auto* | Auto | [Releases](https://github.com/hashicorp/terraform/releases) |
| **Azure CLI** | Runner (vorinstalliert) | Nicht getracked | *auto* | Runner pruefen | [Releases](https://github.com/Azure/azure-cli/releases) |
| **PowerShell** | Runner (vorinstalliert) | 7.6 | *auto* | Runner pruefen | [Releases](https://github.com/PowerShell/PowerShell/releases) |

## Spoke

| Name | Ort | Tracked | Neueste Release | Status | Link |
|------|-----|---------|-----------------|--------|------|
| **AzureRM Provider** | `spoke/providers.tf`, `session-hosts/providers.tf` | `~> 4.0` (installed: 4.66.0) | *auto* | Auto | [Releases](https://github.com/hashicorp/terraform-provider-azurerm/releases) |
| **AzureAD Provider** | `spoke/providers.tf` | `~> 3.0` | *auto* | Auto | [Releases](https://github.com/hashicorp/terraform-provider-azuread/releases) |

## Session Host

| Name | Ort | Tracked | Neueste Release | Status | Link |
|------|-----|---------|-----------------|--------|------|
| **DSC Extension (AVD Agent)** | `modules/session-host/main.tf:164` | `2.77` | 2.83 | OK (auto-upgrade, Retirement 2028-03-31) | [Docs](https://learn.microsoft.com/en-us/azure/virtual-machines/extensions/dsc-windows) |
| **AVD Agent DSC Config ZIP** | `modules/session-host/variables.tf:147` | `1.0.02797.442` | Agent 1.0.13514.600 | ZIP via Portal pruefen | [Agent Releases](https://learn.microsoft.com/en-us/azure/virtual-desktop/whats-new-agent) |
| **JsonADDomainExtension** | `modules/session-host/main.tf:131` | `1.3` | 1.3 | OK | [Docs](https://learn.microsoft.com/en-us/entra/identity/domain-services/join-windows-vm-template) |
| **FSLogix** | Im Packer Image (nicht in Terraform) | Im Image | 26.01 CU1 (3.26.126.19110) | Image pruefen | [Release Notes](https://learn.microsoft.com/en-us/fslogix/overview-release-notes) |

## Azure Allgemein

| Name | Ort | Tracked | Neueste Release | Status | Link |
|------|-----|---------|-----------------|--------|------|
| **AVD REST API** | `scripts/*.ps1`, `pipelines/*.yml` | `2024-04-03` | GA 2024-04-03, Preview 2026-01-01 | OK | [API Docs](https://learn.microsoft.com/en-us/rest/api/desktopvirtualization/) |
