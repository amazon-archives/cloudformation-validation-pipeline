import mock
import unittest
import sys
import os
from datetime import datetime

os.environ['table_name'] = 'some-table-name'

os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

if os.getcwd().endswith('tests') and 'lambda_functions' in os.listdir('../'):
    relative_path_prefix = '../lambda_functions'
elif os.getcwd().endswith('tests') and 'source' in os.listdir('../'):
    relative_path_prefix = '../code/lambda_functions'
elif 'lambda_functions' in os.listdir('./'):
    relative_path_prefix = './lambda_functions'
else:
    relative_path_prefix = './code/lambda_functions'
sys.path.append(relative_path_prefix + "/lib/")
sys.path.append(relative_path_prefix + "/email_notification/")

from email_notification import lambda_handler

def raise_exception(*args, **kwargs):
    raise Exception("Test Exception")

class MockCodePipelineClient(object):

    def __init__(self):
        pass

    def put_job_failure_result(self, jobId, failureDetails):
        return None

    def put_job_success_result(self, jobId, continuationToken=None):
        return None

    def get_job_details(self, jobId):
        return {
            'jobDetails': {
                'data': {
                    'pipelineContext': {
                        "pipelineName": str("pipelineName"),
                        "stage": {
                            "name": str("stage_name")
                        },
                        'action': {
                            'name': "action_name"
                        }
                    }
                }
            }
        }

    def get_pipeline_state(self, name):
        return {
            'stageStates': [
                {
                    "stageName": "stage_name",
                    'latestExecution': {
                        'pipelineExecutionId': "pipelineExecutionId"
                    },
                    "actionStates": [
                        {
                            "actionName": "actionName",
                            'latestExecution': {
                                'pipelineExecutionId': "pipelineExecutionId",
                                "status": "Failed",
                                "errorDetails": {
                                    "message": "an error message"
                                },
                                "lastStatusChange": datetime.now()
                            }
                        }
                    ]
                }
            ]
        }

    def get_pipeline_execution(self, pipelineName, pipelineExecutionId):
        return {
            'pipelineExecution': {
                'artifactRevisions': [
                    {
                        'revisionId': "revisionId"
                    }
                ]
            }
        }

    def get_pipeline(self, name):
        return {
            "pipeline": {
                "stages": [
                    {
                        "actions": [
                            {
                                "actionTypeId": {
                                    "category": "Invoke"
                                },
                                "configuration": {
                                    "FunctionName": "TestLambda"
                                }
                            },
                            {
                                "actionTypeId": {
                                    "category": "Source"
                                },
                                "configuration": {
                                    "RepositoryName": "TestRepo"
                                }
                            }
                        ]
                    }
                ]
            }
        }

class MockSNSClient(object):

    def __init__(self):
        pass

    def publish(self, TopicArn, Subject, Message):
        return None

class MockDDBResource(object):

    def __init__(self):
        pass

    def Table(self, table_name):
        return MockDDBTable()

class MockDDBTable(object):

    def __init__(self):
        pass

    def get_item(self, Key):
        return {}

    def put_item(self, Item):
        return None

class MockBotoClient(object):
    def __init__(self):
        pass
    def client(self, service, region_name=None, access_key=None, secret_key=None, session_token=None, s3v4=True):
        if service == 'codepipeline':
            return MockCodePipelineClient()
        elif service == 'sns':
            return MockSNSClient()
        else:
            raise ValueError("no api mock available for %s" % service)
    def resource(self, service, region_name=None, access_key=None, secret_key=None, session_token=None, s3v4=True):
        if service == 'dynamodb':
            return MockDDBResource()
        else:
            raise ValueError("no api mock available for %s" % service)

event = {
    "pipeline": "test-pipeline",
    "topic": "arn:::test-sns-topic",
    "region": "us-east-1"
}

class MockContext(object):

    def __init__(self):
        self.aws_request_id = 'some-request-id'

pipeline_run = mock.MagicMock(pipeline_run=None)

pipeline_run = mock.MagicMock(pipeline_run=None)

class TestLambdaHandler(unittest.TestCase):

    @mock.patch('email_notification.boto3', MockBotoClient())
    @mock.patch('email_notification.pipeline_run')
    def test_handler_success(self, cfnpl):
        self.assertEqual(lambda_handler(event, MockContext()), None)

if __name__ == '__main__':
    unittest.main()