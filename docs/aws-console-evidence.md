# AWS console evidence (dev, us-east-2)

Screenshots of the deployed `novabank-dev` environment, taken in the AWS console on
2026-11-27, the day after the Terraform apply. The environment was torn down on
2026-11-28 (T30), so these resources no longer exist. They show the resources described in the
[AWS resource inventory](aws-resource-inventory.md). All data shown is synthetic.

## Compute: AWS Lambda
All 10 functions (7 services, 3 workers), Python 3.13, zip packages deployed by the pipeline.

![Lambda: the 10 novabank-dev functions](screenshots/aws/lambda-functions.webp)

The ledger function has no trigger and no public route. Only the account and transfer
services may invoke it.

![Lambda: novabank-dev-ledger with no triggers](screenshots/aws/lambda-ledger.webp)

## API: Amazon API Gateway
One regional HTTP API, `novabank-dev-api`.

![API Gateway: novabank-dev-api](screenshots/aws/apigateway-api.webp)

Every route has the Cognito JWT authorizer attached.

<img src="screenshots/aws/apigateway-jwt-routes.webp" alt="API Gateway: routes with JWT Auth" width="420">

## Identity: Amazon Cognito
User pool `novabank-dev-users`, with the three role groups the API checks.

![Cognito: novabank-dev-users overview](screenshots/aws/cognito-user-pool.webp)

![Cognito: auditors, customers and fraud-reviewers groups](screenshots/aws/cognito-groups.webp)

## Data: Amazon DynamoDB
Nine on-demand tables.

![DynamoDB: the 9 novabank-dev tables](screenshots/aws/dynamodb-tables.webp)

The ledger table, the financial system of record, with point-in-time recovery on.
PITR is enabled on the financial tables only. `novabank-dev-notifications` holds derived
data and has it off by design (`terraform/modules/dynamodb`).

![DynamoDB: novabank-dev-ledger with PITR on](screenshots/aws/dynamodb-ledger-pitr.webp)

## Events: Amazon EventBridge
The custom bus `novabank-dev-events` with its archive rule and the two rules that route
events to the audit and notification queues.

![EventBridge: rules on novabank-dev-events](screenshots/aws/eventbridge-bus-rules.webp)

The two scheduled jobs: outbox reconciliation (every 5 minutes) and ledger
reconciliation (every hour).

![EventBridge: scheduled rules](screenshots/aws/eventbridge-schedules.webp)

## Messaging: Amazon SQS
Seven queues, all encrypted (SSE-SQS). Every dead-letter queue is at 0 messages.

![SQS: the 7 novabank-dev queues](screenshots/aws/sqs-queues.webp)

`novabank-dev-outbox-stream-failures` holds 1 message. It captures DynamoDB Stream
batches the outbox publisher could not process. Its alarm (below) fired for this message.
The outbox reconciliation job republishes pending events, so the event itself is not
lost, but the message should be inspected and the queue cleared.

## Storage: Amazon S3
The four project buckets: Terraform state and Lambda artifacts (bootstrap), plus the
private website bucket and the versioned, KMS-encrypted evidence bucket.

![S3: the 4 novabank buckets](screenshots/aws/s3-buckets.webp)

## Monitoring: Amazon CloudWatch
Alarms by service: 30 OK, 1 in alarm (the stream-failures queue above).

![CloudWatch: overview](screenshots/aws/cloudwatch-overview.webp)

The 31 `novabank-dev-*` alarms.

![CloudWatch: alarms](screenshots/aws/cloudwatch-alarms.webp)

One log group per function plus the API access log, each with 2-week retention.

![CloudWatch: log groups](screenshots/aws/cloudwatch-log-groups.webp)

## Security: AWS IAM
One role per function (least privilege, shared permissions boundary), plus the GitHub
roles that trust only the GitHub OIDC provider.

![IAM: novabank roles](screenshots/aws/iam-roles.webp)

## Cost: AWS Budgets
The `novabank-dev-monthly` cost budget ($25, filtered on the Project tag). It shows
$0.00 spent so far. No alert thresholds are set because no notification e-mail was
configured. Setting `alert_email` in `terraform/envs/dev` adds alerts at 50%, 80% and
100% of actual spend and 100% of forecast spend.

![Budgets: novabank-dev-monthly](screenshots/aws/budget.webp)

## After teardown (T30, 2026-11-28)
The same console pages after the `cleanup` workflow: no Lambda functions, no DynamoDB
tables and no CloudWatch alarms or dashboards left in us-east-2.

![Lambda after teardown: 0 functions](screenshots/aws/teardown-lambda.webp)

![DynamoDB after teardown: 0 tables](screenshots/aws/teardown-dynamodb.webp)

![CloudWatch after teardown: 0 alarms, 0 dashboards](screenshots/aws/teardown-cloudwatch.webp)
