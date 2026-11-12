variable "project" {
  description = "Project prefix for all resource names."
  type        = string
  default     = "rag-corpus"
}
variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "ap-south-1"
}
variable "max_vcpus" {
  description = "Max vCPUs for the Batch Fargate Spot compute environment."
  type        = number
  default     = 64
}
variable "subnet_ids" {
  description = "Subnets for Batch Fargate tasks (must have NAT / S3 VPC endpoint for S3 access)."
  type        = list(string)
  default     = []
}
variable "security_group_ids" {
  description = "Security groups for Batch Fargate tasks."
  type        = list(string)
  default     = []
}
