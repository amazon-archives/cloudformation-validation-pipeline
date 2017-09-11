from awsclients import AwsClients
from botocore.exceptions import ClientError
from cfnpipeline import CFNPipeline
from logger import Logger


loglevel = 'debug'
logger = Logger(loglevel=loglevel)
logger.info('New Lambda container initialised, logging configured.')
clients = AwsClients(logger)
pipeline_run = CFNPipeline(logger, clients)


def get_templates(configs):
    templates = []
    for artifact in configs.keys():
            for config in configs[artifact]:
                for test in config['tests'].keys():
                    t = [artifact, config['tests'][test]['template_file']]
                    if t not in templates:
                        templates.append(t)
    logger.debug(templates)
    return templates


def validate_template(artifact, template_name):
    url = pipeline_run.upload_template(artifact, template_name, pipeline_run.user_params["ScratchBucket"],
                                       pipeline_run.region)
    cfn_client = clients.get('cloudformation')
    try:
        cfn_client.validate_template(TemplateURL=url)
    except ClientError as e:
        return e.message


def lambda_handler(event, context):
    try:
        logger.config(context.aws_request_id)
        logger.debug("Handler starting...")
        logger.debug(event)
        pipeline_run.consume_event(event, context, loglevel=loglevel)
        logger.info({'event': 'new_invoke'})
        errors = []
        successes = []
        for a, t in get_templates(pipeline_run.ci_configs):
            validation_failed = validate_template(a, t)
            if validation_failed:
                errors.append([a, t, validation_failed])
            else:
                successes.append('%s/%s' % (a, t))
        if len(errors) > 0:
            msg = "%s validation failures %s" % (len(errors), errors)
            pipeline_run.put_job_failure(msg)
            logger.error(msg)
        else:
            pipeline_run.put_job_success("Successfully validated: %s" % successes)
            logger.info("Successfully validated: %s" % successes)
    except Exception as e:
        logger.error("unhandled exception!", exc_info=1)
        pipeline_run.put_job_failure(str(e))
