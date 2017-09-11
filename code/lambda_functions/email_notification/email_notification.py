from awsclients import AwsClients
import boto3
from cfnpipeline import CFNPipeline
from logger import Logger
import os


message = """\
A pipeline action has failed:

Pipeline: %s
Region: %s
Stage: %s
Action: %s
Link: %s
Error: %s

"""
link_template = "https://%s.console.aws.amazon.com/codepipeline/home?region=%s#/view/%s"

table_name = os.environ['table_name']

loglevel = 'debug'
logger = Logger(loglevel=loglevel)
logger.info('New Lambda container initialised, logging configured.')
clients = AwsClients(logger)
pipeline_run = CFNPipeline(logger, clients)


def get_pipeline_failures(pipeline, region):
    cp_client = boto3.client('codepipeline', region_name=region)
    pl_state = cp_client.get_pipeline_state(name=pipeline)
    print(pl_state)
    issues = []
    for stage in pl_state['stageStates']:
        for action in stage['actionStates']:
            if 'latestExecution' in action.keys():
                if action['latestExecution']['status'] == 'Failed':
                    stage_name = stage['stageName']
                    action_name = action['actionName']
                    error = action['latestExecution']['errorDetails']['message']
                    lastchange = action['latestExecution']['lastStatusChange'].replace(
                        tzinfo=None
                    ).strftime('%s')
                    issues.append([stage_name, action_name, error, lastchange])
    if len(issues) > 0:
        return issues
    return None


def is_new_issue(error_id, lastchange):
    ddb_table = boto3.resource('dynamodb').Table(table_name)
    response = ddb_table.get_item(Key={"FailureId": error_id})
    if 'Item' in response.keys():
        if response['Item']['LastChange'] == lastchange:
            return False
    ddb_table.put_item(Item={'FailureId': error_id, 'LastChange': lastchange})
    return True


def lambda_handler(event, context):
    print(event)
    pipeline = event['pipeline']
    region = event['region']
    topic = event['topic']
    sns_region = topic.split(':')[3]

    issues = get_pipeline_failures(pipeline, region)
    if issues:
        for stage, action, error, lastchange in issues:
            error_id = "%s::%s::%s::%s" % (region, pipeline, stage, action)
            if is_new_issue(error_id, lastchange):
                sns_client = boto3.client('sns', region_name=sns_region)
                subject = "Pipeline Failure - %s - %s" % (pipeline, stage)
                link = link_template % (region, region, pipeline)
                body = message % (pipeline, region, stage, action, link, error)
                body += '\n\n'
                body += pipeline_run.build_execution_report(
                    pipeline_id=pipeline, region=region,
                    sns_topic=None, s3_bucket=None, s3_prefix='',
                    s3_region=None, execution_id=None
                )
                sns_client.publish(TopicArn=topic, Subject=subject[:100], Message=body)
