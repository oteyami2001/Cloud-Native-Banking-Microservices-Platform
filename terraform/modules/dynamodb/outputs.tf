output "table_names" {
  value = { for k, t in aws_dynamodb_table.this : k => t.name }
}

output "table_arns" {
  value = { for k, t in aws_dynamodb_table.this : k => t.arn }
}

output "outbox_stream_arn" {
  value = aws_dynamodb_table.this["outbox"].stream_arn
}
