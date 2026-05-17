# -----------------------------------------------------------------------------
# Conduit — Observability (CloudWatch alarms + SNS → ops email)
#
# Alarms that protect the "nothing is silently lost" promise on single-box
# infra: the service must be running, the DB must be healthy, the timer
# sweeper's "oldest unfired timer age" must stay low, and failed state
# transitions must never be silent.
# -----------------------------------------------------------------------------

resource "aws_sns_topic" "ops" {
  name = "${var.name_prefix}-ops"
}

resource "aws_sns_topic_subscription" "ops_email" {
  topic_arn = aws_sns_topic.ops.arn
  protocol  = "email"
  endpoint  = var.ops_email
}

# --- Service liveness ------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "service_down" {
  alarm_name          = "${var.name_prefix}-api-down"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 2
  metric_name         = "RunningTaskCount"
  namespace           = "ECS/ContainerInsights"
  period              = 60
  statistic           = "Average"
  threshold           = 1
  alarm_description   = "Conduit API has no running task."
  treat_missing_data  = "breaching"
  dimensions          = { ClusterName = var.cluster_name, ServiceName = var.service_name }
  alarm_actions       = [aws_sns_topic.ops.arn]
  ok_actions          = [aws_sns_topic.ops.arn]
}

# --- RDS health ------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  alarm_name          = "${var.name_prefix}-rds-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 85
  alarm_description   = "Conduit RDS CPU sustained high."
  dimensions          = { DBInstanceIdentifier = var.db_instance_id }
  alarm_actions       = [aws_sns_topic.ops.arn]
}

resource "aws_cloudwatch_metric_alarm" "rds_storage" {
  alarm_name          = "${var.name_prefix}-rds-storage-low"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 2147483648 # 2 GiB
  alarm_description   = "Conduit RDS free storage below 2 GiB."
  dimensions          = { DBInstanceIdentifier = var.db_instance_id }
  alarm_actions       = [aws_sns_topic.ops.arn]
}

# --- Timer sweeper: oldest unfired timer age (custom metric, app-emitted) --

resource "aws_cloudwatch_metric_alarm" "timer_age" {
  alarm_name          = "${var.name_prefix}-oldest-unfired-timer"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "OldestUnfiredTimerAgeSeconds"
  namespace           = "Conduit/Engine"
  period              = 60
  statistic           = "Maximum"
  threshold           = var.timer_age_threshold_seconds
  alarm_description   = "A due timer has not fired within tolerance — sweeper watchdog."
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.ops.arn]
}

# --- Failed state transitions must never be silent -------------------------

resource "aws_cloudwatch_log_metric_filter" "failed_transitions" {
  name           = "${var.name_prefix}-failed-transitions"
  log_group_name = var.log_group
  pattern        = "failed_transition"
  metric_transformation {
    name          = "FailedTransitions"
    namespace     = "Conduit/Engine"
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "failed_transitions" {
  alarm_name          = "${var.name_prefix}-failed-transitions"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "FailedTransitions"
  namespace           = "Conduit/Engine"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "A lifecycle state transition failed."
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.ops.arn]
}
