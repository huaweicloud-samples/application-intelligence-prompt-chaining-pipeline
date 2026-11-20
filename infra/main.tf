# ============================================================================
# 华为云提示词链编排示例 - 基础设施配置
#
# 说明：本项目主要是本地代码链编排，核心运行时不需要云端基础设施。
# 此配置仅在需要将 Demo 部署到 FunctionGraph 时使用。
#
# 部署方式：
#   1. 方式一（本地前端，推荐）：无需 Terraform，直接运行 streamlit
#   2. 方式二（函数计算）：使用 Terraform 创建 OBS + 可选 FunctionGraph
# ============================================================================

terraform {
  required_version = ">= 1.5"

  required_providers {
    huaweicloud = {
      source  = "huaweicloud/huaweicloud"
      version = ">= 1.96.0"
    }
  }

  backend "local" {}
}

# ---------------------------------------------------------------------------
# 变量定义（使用 tfvars 文件或环境变量传入）
# ---------------------------------------------------------------------------
variable "region" {
  description = "华为云区域"
  type        = string
  default     = "cn-north-4"
}

variable "project_name" {
  description = "项目名称"
  type        = string
  default     = "prompt-chaining"
}

variable "maas_api_key" {
  description = "ModelArts Studio API Key"
  type        = string
  sensitive   = true
}

variable "maas_model" {
  description = "模型名称"
  type        = string
  default     = "deepseek-v4"
}

variable "maas_chat_base_url" {
  description = "MaaS 对话端点"
  type        = string
  default     = "https://api.modelarts-maas.com/v2"
}

# ---------------------------------------------------------------------------
# Provider 配置
# ---------------------------------------------------------------------------
provider "huaweicloud" {
  region = var.region
}

# ---------------------------------------------------------------------------
# OBS Bucket (用于存储函数代码包，仅函数部署时需要)
# ---------------------------------------------------------------------------
resource "huaweicloud_obs_bucket" "function_code" {
  bucket = "${var.project_name}-function-code"
  acl    = "private"
  tags = {
    Description = "Function code storage for prompt chaining demo"
  }
}

# ---------------------------------------------------------------------------
# IAM Agency (FunctionGraph 云服务委托，可选)
# ---------------------------------------------------------------------------
resource "huaweicloud_identity_agency" "functiongraph" {
  name                   = "${var.project_name}-fgs-agency"
  description            = "Agency for FunctionGraph"
  duration               = "FOREVER"
  delegated_service_name = "op_svc_cff"

  domain_roles = [
    "OBS OperateAccess",
  ]
}

# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
output "obs_bucket_name" {
  description = "OBS Bucket name for function code"
  value       = huaweicloud_obs_bucket.function_code.bucket
}

output "functiongraph_agency" {
  description = "FunctionGraph agency name"
  value       = huaweicloud_identity_agency.functiongraph.name
}
