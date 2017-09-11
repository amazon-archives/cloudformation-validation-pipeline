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
        pipeline_run.build_execution_report(
            pipeline_id=pipeline_run.pipeline_name, region=pipeline_run.region,
            sns_topic=pipeline_run.report_sns_topic, s3_bucket=pipeline_run.report_s3_bucket,
            s3_prefix=pipeline_run.report_s3_prefix, s3_region=pipeline_run.region,
            execution_id=pipeline_run.pipeline_execution_id
        )
        pipeline_run.put_job_success("report generated successfully")
        return

    except Exception as e:
        logger.error("Unhandled exception!", exc_info=1)
        pipeline_run.put_job_failure(str(e))
