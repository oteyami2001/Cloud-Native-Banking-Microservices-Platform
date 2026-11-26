# Reference container image for running a NovaBank service outside Lambda.
# Not built by CI in the MVP.
FROM public.ecr.aws/lambda/python:3.13
COPY shared/ ${LAMBDA_TASK_ROOT}/shared/
COPY services/ ${LAMBDA_TASK_ROOT}/services/
COPY workers/ ${LAMBDA_TASK_ROOT}/workers/
ARG SERVICE=ledger
ENV SERVICE_NAME=${SERVICE}
CMD ["services.ledger.handler.handler"]
