from awsclients import AwsClients
from cfnpipeline import CFNPipeline
from datetime import datetime
from logger import Logger
import re

loglevel = 'debug'
logger = Logger(loglevel=loglevel)
logger.info('New Lambda container initialised, logging configured.')
clients = AwsClients(logger)
pipeline_run = CFNPipeline(logger, clients)


def get_latest_ami(ami_id, regions):
    latest_ami = False
    for region in regions:
        ec2_client = clients.get('ec2', region)
        try:
            name = ec2_client.describe_images(ImageIds=[ami_id])['Images'][0]['Name']
            latest_ami = ami_id
        except Exception as e:
            if "The image id '[%s]' does not exist" % ami_id in e.args[0]:
                if not latest_ami:
                    latest_ami = 'invalid'
                    continue
            else:
                raise
            for m in re.findall('20[1-2][0-9]\.[0-9][0-9]\.[0-9]*', name):
                name = name.replace(m, '*')
            logger.info("Searching for newer AMI using name filter: %s" % name)
            results = ec2_client.describe_images(Filters=[{'Name': 'name', 'Values': [name]}])
            latest = datetime.strptime('1970-01-01T00:00:00.000Z', "%Y-%m-%dT%H:%M:%S.%fZ")
            for result in results['Images']:
                if datetime.strptime(result['CreationDate'], "%Y-%m-%dT%H:%M:%S.%fZ") > latest:
                    latest = datetime.strptime(result['CreationDate'], "%Y-%m-%dT%H:%M:%S.%fZ")
                    latest_ami = result['ImageId']
    return latest_ami


def match_startswith(obj, val):
    return obj.startswith(val)


def find_ami_ids(templates):
    matches = []
    pipeline_run.find_in_obj(templates, 'ami-', match_startswith, matches)
    return matches


def lambda_handler(event, context):
    try:
        logger.config(context.aws_request_id)
        logger.debug("Handler starting...")
        logger.debug(event)
        pipeline_run.consume_event(event, context, loglevel=loglevel)
        logger.info({'event': 'new_invoke'})
        logger.debug(pipeline_run.ci_configs)
        templates = pipeline_run.get_templates()
        matches = find_ami_ids(templates)
        logger.debug(matches)
        success = []
        failure = []
        for match in matches:
            logger.info("checking ami %s" % match['value'])
            if len(match['regions']) == 0:
                match['error'] = "cannot map a region from the ami-id this likely indicates that this template will only be able to launch in one region"
                failure.append(match)
            else:
                latest = get_latest_ami(match['value'], match['regions'])
                if latest == 'invalid':
                    match['error'] = "ami %s cannot be found in regions %s" % (match['value'], match['regions'])
                    failure.append(match)
                elif latest == match['value']:
                    success.append(match)
                else:
                    match['error'] = "ami is out of date, latest ami is %s" % latest
                    failure.append(match)
        if len(failure) > 0:
            logger.error(failure)
            pipeline_run.put_job_failure(str(failure))
        else:
            logger.info(success)
            pipeline_run.put_job_success(str(success))
    except Exception as e:
        logger.error("unhandled exception!", exc_info=1)
        pipeline_run.put_job_failure(str(e))
