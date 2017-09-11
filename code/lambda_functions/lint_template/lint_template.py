import time
from awsclients import AwsClients
import botocore
from cfnpipeline import CFNPipeline
from logger import Logger
import os

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
                template = [artifact, config['tests'][test]['template_file']]
                if template not in templates:
                    templates.append(template)
    return templates


def lint_template(artifact, template_name, pipeline_name, cfn_nag_version):
    codebuild_client = clients.get('codebuild')
    try:
        build_response = codebuild_client.start_build(projectName='CFN-Lint-' + pipeline_name,
                                                      buildspecOverride="""version: 0.1

phases:
  install:
    commands:
      - apt-get  -y update
      - apt-get -y install ruby-full
      - apt-get -y install jq
      - gem install cfn-nag""" + cfn_nag_version + """
  pre_build:
    commands:
      - echo Nothing to do in the pre_build phase...
  build:
    commands:
      - echo Build started on `date`
      - cfn_nag_scan --input-path templates/""" + template_name + """ --debug
  post_build:
    commands:
      - echo Build completed on `date`""")

        build_id = build_response['build']['id']
        build_status = build_response['build']['buildStatus']

        while build_status == 'IN_PROGRESS':
            time.sleep(5)
            check_response = {'builds': [{}]}
            retry = 0
            while not ('phases' in check_response['builds'][0] and 'buildStatus' in check_response['builds'][0]):
                if retry > 4:
                    raise KeyError("Cannot get buildStatus or phases from CodeBuild response")
                elif retry > 0:
                    time.sleep(10)
                retry += 1
                check_response = codebuild_client.batch_get_builds(ids=[build_id])
            build_status = check_response['builds'][0]['buildStatus']
            phases = check_response['builds'][0]['phases']
            print(check_response)

        if build_status != 'SUCCEEDED':
            error_message = 'linting of template ' + template_name + ' failed'
            for phase in phases:
                if 'phaseStatus' in phase and phase['phaseStatus'] != 'SUCCEEDED':
                    for context in phase['contexts']:
                        error_message += context['message'] + ' - ' + context['statusCode']
            return error_message

    except botocore.exceptions.ClientError as exception:
        return exception.message


def lambda_handler(event, context):
    try:
        logger.config(context.aws_request_id)
        logger.debug("Handler starting...")
        logger.debug(event)
        pipeline_run.consume_event(event, context, loglevel=loglevel)
        logger.info({'event': 'new_invoke'})
        errors = []
        successes = []
        cfn_nag_version = os.environ['TOOLVERSION']
        if cfn_nag_version.lower() == 'latest':
            cfn_nag_version = ""
        else:
            cfn_nag_version = ' -v %s' % cfn_nag_version
        for artifact, template_name in get_templates(pipeline_run.ci_configs):
            lint_failed = lint_template(artifact, template_name, pipeline_run.pipeline_name, cfn_nag_version)
            if lint_failed:
                errors.append([artifact, template_name, lint_failed])
            else:
                successes.append('%s/%s' % (artifact, template_name))
        if len(errors) > 0:
            msg = "%s lint failures %s" % (len(errors), errors)
            pipeline_run.put_job_failure(msg)
            logger.error(msg)
        else:
            pipeline_run.put_job_success("Successfully linted: %s" % successes)
            logger.info("Successfully linted: %s" % successes)
    except Exception as exception:
        logger.error("unhandled exception!", exc_info=1)
        pipeline_run.put_job_failure(str(exception))
