# Runbook: DLQ and outbox recovery

All consumers are idempotent on `event_id`, so redriving is always safe.

## Consumer DLQs (`novabank-dev-notification-dlq`, `novabank-dev-audit-dlq`)
1. Inspect without consuming:
   ```bash
   aws sqs receive-message --queue-url <dlq-url> --max-number-of-messages 5 --visibility-timeout 0 --attribute-names All
   ```
2. Fix the cause (bad release → roll back; fault injection → turn off).
3. Redrive to the source queue:
   ```bash
   aws sqs start-message-move-task --source-arn <dlq-arn> --destination-arn <queue-arn>
   aws sqs list-message-move-tasks --source-arn <dlq-arn>
   ```
4. Confirm DLQ depth returns to 0 and the alarm clears.

## EventBridge delivery DLQ (`novabank-dev-eventbridge-delivery`)
Messages contain the original event plus error attributes. Re-send the `detail`
with `aws events put-events` or replay from the bus archive:
```bash
aws events start-replay --replay-name fix-$(date +%s) --event-source-arn <bus-arn> \
  --event-start-time <t1> --event-end-time <t2> --destination Arn=<bus-arn>
```

## Outbox
* `stream-failures` alarm: a stream batch exhausted 5 retries. The outbox items
  are still `PENDING`; the scheduled **outbox-reconciliation** job (every 5 min)
  republishes them. Invoke it on demand:
  `aws lambda invoke --function-name novabank-dev-outbox-reconciliation:live out.json`.
* `outbox-dead`: items reached `FAILED_PUBLISH` after 10 attempts. They are
  retained. After fixing the cause, set them back to pending:
  ```bash
  aws dynamodb update-item --table-name novabank-dev-outbox --key '{"PK":{"S":"EVENT#..."},"SK":{"S":"METADATA"}}' \
    --update-expression "SET #s = :p, pending_partition = :p, publish_attempts = :z" \
    --expression-attribute-names '{"#s":"status"}' --expression-attribute-values '{":p":{"S":"PENDING"},":z":{"N":"0"}}'
  ```
Committed financial transactions are never rolled back because publication failed.
