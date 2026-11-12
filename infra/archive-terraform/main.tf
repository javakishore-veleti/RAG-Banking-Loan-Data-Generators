terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
  # Uncomment for a remote backend (recommended for a team):
  # backend "s3" {
  #   bucket = "rag-corpus-tfstate-<account-id>"
  #   key    = "rag-corpus/terraform.tfstate"
  #   region = "ap-south-1"
  #   dynamodb_table = "rag-corpus-tf-lock"
  # }
}

provider "aws" { region = var.aws_region }

locals {
  name = var.project
  tags = { Project = var.project, ManagedBy = "terraform" }
}

# ---------------------------------------------------------------- S3
resource "aws_s3_bucket" "corpus" {
  bucket = "${var.project}-corpus-${data.aws_caller_identity.current.account_id}"
  tags   = local.tags
}
resource "aws_s3_bucket_versioning" "corpus" {
  bucket = aws_s3_bucket.corpus.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "corpus" {
  bucket = aws_s3_bucket.corpus.id
  rule { apply_server_side_encryption_by_default { sse_algorithm = "AES256" } }
}
resource "aws_s3_bucket_lifecycle_configuration" "corpus" {
  bucket = aws_s3_bucket.corpus.id
  rule {
    id     = "intelligent-tiering"
    status = "Enabled"
    transition { days = 30, storage_class = "INTELLIGENT_TIERING" }
  }
}
data "aws_caller_identity" "current" {}

# ---------------------------------------------------------------- DynamoDB manifest
resource "aws_dynamodb_table" "manifest" {
  name         = "${var.project}-manifest"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "doc_id"
  attribute { name = "doc_id", type = "S" }
  attribute { name = "loan_id", type = "S" }
  global_secondary_index {
    name            = "loan_id-index"
    hash_key        = "loan_id"
    projection_type = "ALL"
  }
  tags = local.tags
}

# ---------------------------------------------------------------- SQS + DLQ (FIFO, for dedup + ordering per run)
resource "aws_sqs_queue" "dlq" {
  name                        = "${var.project}-shards-dlq.fifo"
  fifo_queue                  = true
  content_based_deduplication = true
  message_retention_seconds   = 1209600 # 14 days
  tags                        = local.tags
}
resource "aws_sqs_queue" "shards" {
  name                        = "${var.project}-shards.fifo"
  fifo_queue                  = true
  content_based_deduplication = true
  visibility_timeout_seconds  = 3600
  message_retention_seconds   = 1209600
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
  tags = local.tags
}

# ---------------------------------------------------------------- ECR
resource "aws_ecr_repository" "worker" {
  name                 = "${var.project}-worker"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
  tags = local.tags
}

# ---------------------------------------------------------------- IAM: Batch execution + task roles (least privilege)
data "aws_iam_policy_document" "batch_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals { type = "Service", identifiers = ["ecs-tasks.amazonaws.com"] }
  }
}
resource "aws_iam_role" "batch_task" {
  name               = "${var.project}-batch-task"
  assume_role_policy = data.aws_iam_policy_document.batch_assume.json
  tags               = local.tags
}
resource "aws_iam_role_policy" "batch_task" {
  name = "${var.project}-batch-task"
  role = aws_iam_role.batch_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:PutObject", "s3:GetObject", "s3:HeadObject"],
        Resource = ["${aws_s3_bucket.corpus.arn}/*"] },
      { Effect = "Allow", Action = ["dynamodb:PutItem"],
        Resource = [aws_dynamodb_table.manifest.arn] },
      { Effect = "Allow", Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"],
        Resource = [aws_sqs_queue.shards.arn] },
      { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"],
        Resource = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/batch/*"] },
    ]
  })
}
resource "aws_iam_role" "batch_execution" {
  name               = "${var.project}-batch-execution"
  assume_role_policy = data.aws_iam_policy_document.batch_assume.json
  tags               = local.tags
}
resource "aws_iam_role_policy_attachment" "batch_execution" {
  role       = aws_iam_role.batch_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# ---------------------------------------------------------------- AWS Batch (Fargate, Spot first)
resource "aws_batch_compute_environment" "main" {
  compute_environment_name = "${var.project}-fargate-spot"
  type                     = "MANAGED"
  state                    = "ENABLED"
  compute_resources {
    type               = "FARGATE_SPOT"
    max_vcpus          = var.max_vcpus
    subnets            = var.subnet_ids
    security_group_ids = var.security_group_ids
  }
  service_role = aws_iam_role.batch_service.arn
  tags         = local.tags
}
resource "aws_iam_role" "batch_service" {
  name               = "${var.project}-batch-service"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "batch.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}
resource "aws_iam_role_policy_attachment" "batch_service" {
  role       = aws_iam_role.batch_service.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBatchServiceRole"
}
resource "aws_batch_job_queue" "main" {
  name                 = "${var.project}-queue"
  state                = "ENABLED"
  priority             = 1
  compute_environments = [aws_batch_compute_environment.main.arn]
  tags                 = local.tags
}
resource "aws_batch_job_definition" "worker" {
  name = "${var.project}-worker"
  type = "container"
  platform_capabilities = ["FARGATE"]
  retry_strategy { attempts = 3 }
  container_properties = jsonencode({
    image      = "${aws_ecr_repository.worker.repository_url}:latest"
    jobRoleArn = aws_iam_role.batch_task.arn
    executionRoleArn = aws_iam_role.batch_execution.arn
    resourceRequirements = [
      { type = "VCPU", value = "2" },
      { type = "MEMORY", value = "4096" },
    ]
    environment = [
      { name = "CORPUS_BUCKET", value = aws_s3_bucket.corpus.bucket },
      { name = "MANIFEST_TABLE", value = aws_dynamodb_table.manifest.name },
      { name = "QUEUE_URL", value = aws_sqs_queue.shards.url },
      { name = "AWS_REGION", value = var.aws_region },
    ]
    logConfiguration = { logDriver = "awslogs" }
  })
  tags = local.tags
}

# ---------------------------------------------------------------- Planner Lambda
data "archive_file" "planner" {
  type        = "zip"
  source_dir  = "${path.module}/../../src/planner"
  output_path = "${path.module}/planner.zip"
}
resource "aws_iam_role" "planner" {
  name = "${var.project}-planner"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
  tags = local.tags
}
resource "aws_iam_role_policy" "planner" {
  name = "${var.project}-planner"
  role = aws_iam_role.planner.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["sqs:SendMessageBatch", "sqs:SendMessage"], Resource = [aws_sqs_queue.shards.arn] },
      { Effect = "Allow", Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"], Resource = ["*"] },
    ]
  })
}
resource "aws_lambda_function" "planner" {
  function_name = "${var.project}-planner"
  role          = aws_iam_role.planner.arn
  handler       = "planner.handler"
  runtime       = "python3.12"
  filename      = data.archive_file.planner.output_path
  timeout       = 120
  environment { variables = { QUEUE_URL = aws_sqs_queue.shards.url, AWS_REGION = var.aws_region } }
  tags = local.tags
}

# ---------------------------------------------------------------- Step Functions
resource "aws_iam_role" "sfn" {
  name = "${var.project}-sfn"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "states.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
  tags = local.tags
}
resource "aws_iam_role_policy" "sfn" {
  name = "${var.project}-sfn"
  role = aws_iam_role.sfn.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["lambda:InvokeFunction"], Resource = [aws_lambda_function.planner.arn] },
      { Effect = "Allow", Action = ["batch:SubmitJob"], Resource = ["*"] },
      { Effect = "Allow", Action = ["events:PutTargets", "events:PutRule", "events:DescribeRule"], Resource = ["*"] },
    ]
  })
}
resource "aws_sfn_state_machine" "main" {
  name       = "${var.project}-run"
  role_arn   = aws_iam_role.sfn.arn
  definition = templatefile("${path.module}/../stepfunctions/state-machine.json", {
    planner_arn        = aws_lambda_function.planner.arn
    job_definition_arn = aws_batch_job_definition.worker.arn
    job_queue_arn      = aws_batch_job_queue.main.arn
  })
  tags = local.tags
}

# ---------------------------------------------------------------- Alarms
resource "aws_cloudwatch_metric_alarm" "dlq_depth" {
  alarm_name          = "${var.project}-dlq-depth"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  dimensions          = { QueueName = aws_sqs_queue.dlq.name }
  alarm_description   = "Shards are failing and landing in the DLQ."
  tags                = local.tags
}
