from awsclients import AwsClients
from cfnpipeline import CFNPipeline
from logger import Logger


loglevel = 'debug'
logger = Logger(loglevel=loglevel)
logger.info('New Lambda container initialised, logging configured.')
clients = AwsClients(logger)
pipeline_run = CFNPipeline(logger, clients)


def lambda_handler(event, context):
    try:
        logger.config(context.aws_request_id, loglevel=loglevel)
        logger.debug("Handler starting...")
        logger.debug(event)
        pipeline_run.consume_event(event, context, loglevel=loglevel)
        logger.info({'event': 'new_invoke'})
        pipeline_run.deploy_to_s3()
        pipeline_run.put_job_success("S3 bucket updated successfully")
        return

    except Exception as e:
        logger.error("Unhandled exception!", exc_info=1)
        pipeline_run.put_job_failure(str(e))
