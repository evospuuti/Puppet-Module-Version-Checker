# AVD Version Tracker

Stand: 2026-03-27

| Name | Ort | Tracked | Neueste Release | Status | Link |
|------|-----|---------|-----------------|--------|------|
| **Terraform** | `spoke/providers.tf`, `session-hosts/providers.tf` | `>= 1.14.0, < 2.0.0` | 1.14.8 | OK | [Releases](https://github.com/hashicorp/terraform/releases) |
| **AzureRM Provider** | `spoke/providers.tf`, `session-hosts/providers.tf` | `~> 4.0` (installed: 4.66.0) | 4.66.0 | OK | [Releases](https://github.com/hashicorp/terraform-provider-azurerm/releases) |
| **AzureAD Provider** | `spoke/providers.tf` | `~> 3.0` | 3.8.0 | OK | [Releases](https://github.com/hashicorp/terraform-provider-azuread/releases) |
| **DSC Extension (AVD Agent)** | `modules/session-host/main.tf:164` | `2.77` | 2.77 | OK (Retirement 2028-03-31) | [Docs](https://learn.microsoft.com/en-us/azure/virtual-machines/extensions/dsc-windows) |
| **AVD Agent DSC Config ZIP** | `modules/session-host/variables.tf:147` | `1.0.02797.442` | Pruefen via Portal | PRUEFEN | [Agent Releases](https://learn.microsoft.com/en-us/azure/virtual-desktop/whats-new-agent) |
| **JsonADDomainExtension** | `modules/session-host/main.tf:131` | `1.3` | 1.3 | OK | [Docs](https://learn.microsoft.com/en-us/entra/identity/domain-services/join-windows-vm-template) |
| **FSLogix** | Im Packer Image (nicht in Terraform) | Im Image | 26.01 CU1 (3.26.126.19110) | Image pruefen | [Release Notes](https://learn.microsoft.com/en-us/fslogix/overview-release-notes) |
| **AVD REST API** | `scripts/*.ps1`, `pipelines/*.yml` | `2024-04-03` | 2024-04-03 (GA), 2026-01-01-preview | OK | [API Docs](https://learn.microsoft.com/en-us/rest/api/desktopvirtualization/) |
| **Azure CLI** | Runner (vorinstalliert) | Nicht getracked | 2.84.0 | Runner pruefen | [Releases](https://github.com/Azure/azure-cli/releases) |
| **PowerShell** | Runner (vorinstalliert) | 7.x | 7.5.x | Runner pruefen | [Releases](https://github.com/PowerShell/PowerShell/releases) |
| **TLS Minimum** | `modules/storage/main.tf:22` | `TLS1_2` | TLS 1.2 | OK | - |
| **Windows Image** | `config/common.tfvars` | `latest` (aus Compute Gallery) | Packer Build | Image pruefen | - |
