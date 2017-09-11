import unittest
import mock
import json
import shutil
import sys
import os
import zipfile

os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

if os.getcwd().endswith('tests') and 'lambda_functions' in os.listdir('../'):
    relative_path_prefix = '../lambda_functions'
    artifact_path = './test_artifact.zip'
    basepath = './'
elif os.getcwd().endswith('tests') and 'source' in os.listdir('../'):
    relative_path_prefix = '../code/lambda_functions'
    artifact_path = './test_artifact.zip'
    basepath = './'
elif 'lambda_functions' in os.listdir('./'):
    relative_path_prefix = './lambda_functions'
    artifact_path = './tests/test_artifact.zip'
    basepath = './tests/'
else:
    relative_path_prefix = './code/lambda_functions'
    artifact_path = './code/tests/test_artifact.zip'
    basepath = './code/tests/'

sys.path.append(relative_path_prefix + "/lib/")

if not os.path.exists(basepath + 'test_artifact.zip'):
    orig_path = os.getcwd()
    os.chdir(basepath)
    ziph = zipfile.ZipFile('./test_artifact.zip', 'w', zipfile.ZIP_DEFLATED)
    if 'demo_source' in os.listdir('../'):
        os.chdir('../demo_source')
    else:
        os.chdir('../../demo_source')
    for root, dirs, files in os.walk('./'):
        for f in files:
            if f == 'config.yml':
                shutil.copyfile(os.path.join(root, f), '/tmp/config.yml')
                fh = open('/tmp/config.yml', 'a')
                fh.write("""
    built_stacks:
      "eu-west-1": 
        - test1
      "us-east-1":
        - test2
""")
                fh.close()
                ziph.write('/tmp/config.yml', 'ci/config.yml')
            else:
                ziph.write(os.path.join(root, f))
    ziph.close()
    os.chdir(orig_path)

from cfnpipeline import CFNPipeline
from logger import Logger

os.environ['execution_role'] = 'TestExecutionRole'

logger = Logger(loglevel="critical")

event = {
    "CodePipeline.job": {
        "id": str(''),
        "data": {
            "inputArtifacts": [
                {
                    'location': {
                        's3Location': {
                            'bucketName': "bucketName",
                            'objectKey': "objectKey"
                        }
                    },
                    "name": "TemplateArtifact"
                }
            ],
            "outputArtifacts": [
                {
                    'location': {
                        's3Location': {
                            'bucketName': "bucketName",
                            'objectKey': "objectKey"
                        }
                    },
                    "name": "StackArtifact"
                }
            ],
            'actionConfiguration': {
                'configuration': {
                    'UserParameters': None
                }
            },
            'artifactCredentials': {
                'accessKeyId': "xxx",
                'secretAccessKey': "yyy",
                'sessionToken': "zzz"
            }
        }
    }
}


class MockContext(object):
    def __init__(self):
        self.aws_request_id = str('')

class MockLogsClient(object):

    def __init__(self):
        pass

    def filter_log_events(self, logGroupName, filterPattern):
        return {
            "events": [
                {
                    u'message': u'{"time_stamp": "2017-04-26 08:31:48,044", "log_level": "ERROR", "data": {"stage_name": "StackCreation", "artifact_revision_id": "252fa4013a402614f4849a7472ef151ed570f917", "pipeline_name": "test15-MainPipeline-WZV9PVAL9REQ-CfnCicdPipeline-8NKZ06J53KX7", "pipeline_execution_id": "752da445-d9ba-457f-9ed2-fb6b7eef09c1", "request_id": "c85dc0fb-2a5a-11e7-8e14-43ef64dbe4b1", "pipeline_action": "CFN_Create_Stacks", "message": {"event": "return_continue"}, "original_job_id": "36d1b810-3150-4e73-b973-5ad605fb9b57", "job_id": "e90bbb29-1f53-46e3-a5f9-69e392e86757"}}\n'

                },
                {
                    u'message': u'{"time_stamp": "2017-04-26 08:32:17,150", "log_level": "WARNING", "data": {"stage_name": "StackCreation", "artifact_revision_id": "252fa4013a402614f4849a7472ef151ed570f917", "pipeline_name": "test15-MainPipeline-WZV9PVAL9REQ-CfnCicdPipeline-8NKZ06J53KX7", "pipeline_execution_id": "752da445-d9ba-457f-9ed2-fb6b7eef09c1", "request_id": "daf3e6c5-2a5a-11e7-bed9-4961190bacb3", "pipeline_action": "CFN_Create_Stacks", "message": {"event": "new_invoke"}, "original_job_id": "7f1c3ec2-9fe0-40bd-866d-ff74a60d45f6", "job_id": "e90bbb29-1f53-46e3-a5f9-69e392e86757"}}\n'
                }
            ]
        }

class MockSCClient(object):

    def __init__(self):
        pass

    def scan_provisioned_products(self, AccessLevelFilter):
        return {
            "ProvisionedProducts": [
                {
                    "Id": "pp-ProvisionedProductId",
                    "LastRecordId": "LastRecordId",
                    "Status": "CREATE_COMPLETE"
                }
            ]
        }

    def describe_record(self, Id):
        return {
            "RecordDetail": {
                "ProductId": "ProductId"
            }
        }

    def terminate_provisioned_product(self, ProvisionedProductId, TerminateToken):
        return None

    def list_portfolios_for_product(self, ProductId):
        return {
            'PortfolioDetails': [{"Id": "PortfolioId"}]
        }

    def list_principals_for_portfolio(self, PortfolioId):
        return {
            'Principals': [{"PrincipalARN": "PrincipalARN"}]
        }

    def disassociate_product_from_portfolio(self, ProductId, PortfolioId):
        return None

    def disassociate_principal_from_portfolio(self, PortfolioId, PrincipalARN):
        return None

    def list_constraints_for_portfolio(self, PortfolioId):
        return {
            'ConstraintDetails': [{"ConstraintId": "ConstraintId"}]
        }

    def delete_constraint(self, Id):
        return None

    def delete_product(self, Id):
        return None

    def delete_portfolio(self, Id):
        return None

    def create_portfolio(self, **kwargs):
        return {
            "PortfolioDetail": {"Id": "PortfolioId"}
        }

    def create_product(self, **kwargs):
        return {
            'ProductViewDetail': {'ProductViewSummary': {'ProductId': "ProductId"}},
            "ProvisioningArtifactDetail": {"Id": "ProvisioningArtifactDetailId"}
        }

    def associate_product_with_portfolio(self, **kwargs):
        return None

    def associate_principal_with_portfolio(self, **kwargs):
        return None

    def create_constraint(self, **kwargs):
        return {
            "ConstraintDetail": {"ConstraintId": "ConstraintId"}
        }

    def provision_product(self, **kwargs):
        return {
            "RecordDetail": {"ProvisionedProductId": "pp-ProvisionedProductId"}
        }

class MockSnsClient(object):

    def __init__(self):
        pass

    def publish(self, Message, Subject, TopicArn):
        return None

class MockEC2Client(object):

    def __init__(self):
        pass

    def create_key_pair(self, KeyName):
        return {
            "KeyMaterial": "MyPrivateKey"
        }

    def describe_availability_zones(self, Filters=None):
        return {
            "AvailabilityZones": [
                {"ZoneName": "us-east-1a"},
                {"ZoneName": "us-east-1b"},
                {"ZoneName": "us-east-1c"}
            ]
        }

    def describe_regions(self):
        return {
            "Regions": [
                {
                    "RegionName": 'us-east-1'
                },
                {
                    "RegionName": 'us-west-1'
                }
            ]
        }

class MockCfnClient(object):

    def __init__(self):
        pass

    def describe_stacks(self, StackName=None):
        if StackName == 'StackId1':
            return {
                "Stacks": [
                    {
                        "Tags": [
                            {
                                "Key": "cfn_cicd_artifact",
                                "Value": "cfn_cicd_artifact"
                            },
                            {
                                "Key": "cfn_cicd_testname",
                                "Value": "cfn_cicd_testname"
                            }
                        ],
                        "StackStatus": "CREATE_FAILED",
                        "StackId": "StackId1"
                    }
                ]
            }
        elif StackName == 'StackId2':
            return {
            "Stacks": [
                {
                    "Tags": [
                        {
                            "Key": "cfn_cicd_artifact",
                            "Value": "cfn_cicd_artifact"
                        },
                        {
                            "Key": "cfn_cicd_testname",
                            "Value": "cfn_cicd_testname"
                        }
                    ],
                    "StackStatus": "CREATE_COMPLETE",
                    "StackId": "StackId2"
                }
            ]
        }
        elif StackName == 'StackId3':
            return {
                "Stacks": [
                    {
                        "Tags": [
                            {
                                "Key": "cfn_cicd_artifact",
                                "Value": "cfn_cicd_artifact"
                            },
                            {
                                "Key": "cfn_cicd_testname",
                                "Value": "cfn_cicd_testname"
                            }
                        ],
                        "StackStatus": "CREATE_IN_PROGRESS",
                        "StackId": "StackId3"
                    }
                ]
            }
        else:
            return {
                "Stacks": [
                    {
                        "Tags": [
                            {
                                "Key": "cfn_cicd_artifact",
                                "Value": "TemplateArtifact"
                            },
                            {
                                "Key": "cfn_cicd_testname",
                                "Value": "defaults"
                            },
                            {
                                "Key": "cfn_cicd_pipeline",
                                "Value": "pipelineName"
                            },
                            {
                                "Key": "cfn_cicd_jobid",
                                "Value": "cfn_cicd_jobid"
                            }
                        ],
                        "StackStatus": "CREATE_IN_PROGRESS",
                        "StackId": "StackId3"
                    },
                    {
                        "Tags": [
                            {
                                "Key": "cfn_cicd_artifact",
                                "Value": "TemplateArtifact"
                            },
                            {
                                "Key": "cfn_cicd_testname",
                                "Value": "defaults"
                            },
                            {
                                "Key": "cfn_cicd_pipeline",
                                "Value": "pipelineName"
                            },
                            {
                                "Key": "cfn_cicd_jobid",
                                "Value": "cfn_cicd_jobid"
                            }
                        ],
                        "StackStatus": "CREATE_FAILED",
                        "StackId": "StackId1"
                    },
                    {
                        "Tags": [
                            {
                                "Key": "cfn_cicd_artifact",
                                "Value": "TemplateArtifact"
                            },
                            {
                                "Key": "cfn_cicd_testname",
                                "Value": "defaults"
                            },
                            {
                                "Key": "cfn_cicd_pipeline",
                                "Value": "pipelineName"
                            },
                            {
                                "Key": "cfn_cicd_jobid",
                                "Value": "cfn_cicd_jobid"
                            }
                        ],
                        "StackStatus": "CREATE_COMPLETE",
                        "StackId": "StackId2"
                    }
                ]
            }


    def describe_stack_events(self, StackName):
        return {
            "StackEvents": [
                {
                    "ResourceStatus": "CREATE_FAILED",
                    "LogicalResourceId": "LogicalResourceId",
                    "ResourceStatusReason": "ResourceStatusReason"
                }
            ]
        }

    def delete_stack(self, StackName):
        return None

    def create_stack(self, **kwargs):
        return {
            "StackId": "StackId1"
        }

    def list_stack_resources(self, StackName):
        return {
            "StackResourceSummaries": [
                {
                    "ResourceType": "AWS::ResourceType",
                    "LogicalResourceId": "LogicalResourceId",
                    "PhysicalResourceId": "PhysicalResourceId"
                }
            ]
        }

    def list_stacks(self, **kwargs):
        return {
            "StackSummaries": [
                {
                    "StackId": "pp-ProvisionedProductId"
                }
            ]
        }

class MockS3Client(object):

    def __init__(self):
        pass

    def get_object(self, Bucket, Key):
        return {
            "Body": open(artifact_path, 'rb')
        }

    def put_object(self,Bucket, Key, Body):
        return None

    def upload_file(self, fname, bucket, key, ExtraArgs=None):
        return None

    def list_objects(self, Bucket, Prefix):
        return {
            "Contents": [
                {
                    "Key": "an_s3_key"
                }
            ]
        }

    def delete_objects(self, Bucket, Delete):
        return None

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
                    }
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

class MockBotoClient(object):
    def __init__(self):
        pass
    def get(self, service, region=None, access_key=None, secret_key=None, session_token=None, s3v4=True):
        if service == 'codepipeline':
            return MockCodePipelineClient()
        elif service == 's3':
            return MockS3Client()
        elif service == 'cloudformation':
            return MockCfnClient()
        elif service == 'ec2':
            return MockEC2Client()
        elif service == 'logs':
            return MockLogsClient()
        elif service == 'sns':
            return MockSnsClient()
        elif service == 'servicecatalog':
            return MockSCClient()
        else:
            raise ValueError("no api mock available for %s" % service)


clients = MockBotoClient()

def MockRequest(url, post_data, headers):
        return None

class MockUrlOpen(object):

    def __init__(self):
        pass

    def read(self):
        return None

    def getcode(self):
        return None

class TestCFNPipeline(unittest.TestCase):
    def test___init__(self):
        cfn_pipeline = CFNPipeline(logger, clients)
        self.assertIsNotNone(cfn_pipeline.anon_usage_reporting_url)

    @mock.patch('cfnpipeline.CFNPipeline.anon_reporting', mock.Mock(return_value=None))
    @mock.patch('awsclients.AwsClients.get', mock.Mock(return_value=MockCodePipelineClient()))
    def test_put_job_failure(self):
        cfn_pipeline = CFNPipeline(logger, clients)
        self.assertEqual(None, cfn_pipeline.put_job_failure('failure message'))

    @mock.patch('cfnpipeline.CFNPipeline.anon_reporting', mock.Mock(return_value=None))
    @mock.patch('awsclients.AwsClients.get', mock.Mock(return_value=MockCodePipelineClient()))
    def test_put_job_success(self):
        cfn_pipeline = CFNPipeline(logger, clients)
        self.assertEqual(None, cfn_pipeline.put_job_success('success message'))

    @mock.patch('cfnpipeline.CFNPipeline.anon_reporting', mock.Mock(return_value=None))
    @mock.patch('awsclients.AwsClients.get', mock.Mock(return_value=MockCodePipelineClient()))
    def test_continue_job_later(self):
        cfn_pipeline = CFNPipeline(logger, clients)
        self.assertEqual(None, cfn_pipeline.continue_job_later('continuation message'))
        long_message = ''
        while len(long_message) < 2049:
            long_message += 'a'
        event['CodePipeline.job']['data']['actionConfiguration']['configuration']['UserParameters'] = json.dumps({
            "CITestPath": "ci",
            "ScratchBucket": "ScratchBucket"
        })
        cfn_pipeline.consume_event(event, MockContext(), 'critical')
        self.assertEqual(None, cfn_pipeline.continue_job_later(long_message))

    @mock.patch('urllib2.Request', mock.Mock(return_value=MockRequest))
    @mock.patch('urllib2.urlopen', mock.Mock(return_value=MockUrlOpen))
    @mock.patch('awsclients.AwsClients', mock.Mock(return_value=MockBotoClient()))
    def test_anon_reporting(self):
        cfn_pipeline = CFNPipeline(logger, clients)
        event['CodePipeline.job']['data']['actionConfiguration']['configuration']['UserParameters'] = json.dumps({
            "CITestPath": "ci",
            "ScratchBucket": "ScratchBucket"
        })
        cfn_pipeline.consume_event(event, MockContext(), 'critical')
        self.assertEqual(None, cfn_pipeline.anon_reporting('message', 'status'))

    @mock.patch('awsclients.AwsClients', mock.Mock(return_value=MockBotoClient()))
    def test_consume_event(self):
        cfn_pipeline = CFNPipeline(logger, clients)
        event['CodePipeline.job']['data']['actionConfiguration']['configuration']['UserParameters'] = json.dumps({
            "CITestPath": "ci",
            "ScratchBucket": "ScratchBucket",
            "SNSTopic": "SNSTopic:SNSTopic:SNSTopic:SNSTopic:SNSTopic",
            "ReportKey": "ReportKey",
            "ReportBucket": "ReportBucket"
        })
        self.assertEqual(None, cfn_pipeline.consume_event(event, MockContext(), 'critical'))
        event['CodePipeline.job']['data']['actionConfiguration']['configuration']['UserParameters'] = json.dumps({
            "CITestPath": "ci",
            "ScratchBucket": "ScratchBucket",
            "CleanupPrevious": "Yes",
            "CleanupFailed": "Yes",
            "CleanupNonFailed": "Yes"
        })
        self.assertEqual(None, cfn_pipeline.consume_event(event, MockContext(), 'critical'))
        event['CodePipeline.job']['data']['actionConfiguration']['configuration']['UserParameters'] = json.dumps({
            "CITestPath": "ci",
            "ScratchBucket": "ScratchBucket",
            "CleanupPrevious": "No",
            "CleanupFailed": "No",
            "CleanupNonFailed": "No"
        })
        self.assertEqual(None, cfn_pipeline.consume_event(event, MockContext(), 'critical'))
        event['CodePipeline.job']['data']['actionConfiguration']['configuration']['UserParameters'] = "this isn't json"
        with self.assertRaises(ValueError):
            self.assertRaises(ValueError, cfn_pipeline.consume_event(event, MockContext(), 'critical'))
        event['CodePipeline.job']['data']['actionConfiguration']['configuration']['UserParameters'] = json.dumps({
            "ScratchBucket": "ScratchBucket"
        })
        with self.assertRaises(ValueError):
            cfn_pipeline.consume_event(event, MockContext(), 'critical')

    @mock.patch('awsclients.AwsClients', mock.Mock(return_value=MockBotoClient()))
    def test_check_statuses(self):
        cfn_pipeline = CFNPipeline(logger, clients)
        stacks = [
            {
                'region': 'us-east-1',
                'stackid': 'StackId1'
            },
            {
                'region': 'us-west-1',
                'stackid': 'StackId2'
            },
            {
                'region': 'us-east-1',
                'stackid': 'StackId3'
            }
        ]
        expected_result = {'inprogress': [{'status': 'inprogress', 'stackid': 'StackId3', 'region': 'us-east-1', 'detail': 'CREATE_IN_PROGRESS', 'artifact': 'cfn_cicd_artifact', 'testname': 'cfn_cicd_testname'}], 'success': [{'status': 'success', 'stackid': 'StackId2', 'region': 'us-west-1', 'detail': 'CREATE_COMPLETE', 'artifact': 'cfn_cicd_artifact', 'testname': 'cfn_cicd_testname'}], 'error': [{'status': 'error', 'stackid': 'StackId1', 'region': 'us-east-1', 'detail': ['CREATE_FAILED', [['CREATE_FAILED', 'LogicalResourceId', 'ResourceStatusReason']]], 'artifact': 'cfn_cicd_artifact', 'testname': 'cfn_cicd_testname'}]}
        self.assertEqual(expected_result, cfn_pipeline.check_statuses(stacks))
        # handle invalid states
        # with self.assertRaises(NameError):
        #    cfn_pipeline.check_statuses(stacks)

    def test_cleanup_previous_stacks(self):
        cfn_pipeline = CFNPipeline(logger, clients)
        cfn_pipeline.consume_event(event, MockContext(), 'critical')
        expected = {'inprogress': [{'status': 'inprogress', 'stackid': 'StackId3', 'region': 'us-east-1', 'detail': 'CREATE_IN_PROGRESS', 'artifact': 'cfn_cicd_artifact', 'testname': 'cfn_cicd_testname'}, {'status': 'inprogress', 'stackid': 'StackId3', 'region': 'eu-west-1', 'detail': 'CREATE_IN_PROGRESS', 'artifact': 'cfn_cicd_artifact', 'testname': 'cfn_cicd_testname'}], 'success': [{'status': 'success', 'stackid': 'StackId2', 'region': 'us-east-1', 'detail': 'CREATE_COMPLETE', 'artifact': 'cfn_cicd_artifact', 'testname': 'cfn_cicd_testname'}, {'status': 'success', 'stackid': 'StackId2', 'region': 'eu-west-1', 'detail': 'CREATE_COMPLETE', 'artifact': 'cfn_cicd_artifact', 'testname': 'cfn_cicd_testname'}], 'error': [{'status': 'error', 'stackid': 'StackId1', 'region': 'us-east-1', 'detail': ['CREATE_FAILED', [['CREATE_FAILED', 'LogicalResourceId', 'ResourceStatusReason']]], 'artifact': 'cfn_cicd_artifact', 'testname': 'cfn_cicd_testname'}, {'status': 'error', 'stackid': 'StackId1', 'region': 'eu-west-1', 'detail': ['CREATE_FAILED', [['CREATE_FAILED', 'LogicalResourceId', 'ResourceStatusReason']]], 'artifact': 'cfn_cicd_artifact', 'testname': 'cfn_cicd_testname'}]}
        self.assertEqual(expected, cfn_pipeline.cleanup_previous_stacks())

    def test_delete_stacks(self):
        cfn_pipeline = CFNPipeline(logger, clients)
        stacks = [
            {
                'region': 'us-east-1',
                'stackid': 'StackId1'
            },
            {
                'region': 'us-west-1',
                'stackid': 'StackId2'
            },
            {
                'region': 'us-east-1',
                'stackid': 'StackId3'
            }
        ]
        expected = {'inprogress': [{'status': 'inprogress', 'stackid': 'StackId3', 'region': 'us-east-1', 'detail': 'CREATE_IN_PROGRESS', 'artifact': 'cfn_cicd_artifact', 'testname': 'cfn_cicd_testname'}], 'success': [{'status': 'success', 'stackid': 'StackId2', 'region': 'us-west-1', 'detail': 'CREATE_COMPLETE', 'artifact': 'cfn_cicd_artifact', 'testname': 'cfn_cicd_testname'}], 'error': [{'status': 'error', 'stackid': 'StackId1', 'region': 'us-east-1', 'detail': ['CREATE_FAILED', [['CREATE_FAILED', 'LogicalResourceId', 'ResourceStatusReason']]], 'artifact': 'cfn_cicd_artifact', 'testname': 'cfn_cicd_testname'}]}
        self.assertEqual(expected, cfn_pipeline.delete_stacks(stacks))

    def test_create_stacks(self):
        cfn_pipeline = CFNPipeline(logger, clients)
        event['CodePipeline.job']['data']['actionConfiguration']['configuration']['UserParameters'] = json.dumps({
            "CITestPath": "ci",
            "ScratchBucket": "ScratchBucket",
            "SNSTopic": "SNSTopic:SNSTopic:SNSTopic:SNSTopic:SNSTopic",
            "ReportKey": "ReportKey",
            "ReportBucket": "ReportBucket",
            "StackCreationRoleArn": "arn::::StackCreationRoleArn",
            "KeyBucket": "KeyBucket"
        })
        cfn_pipeline.consume_event(event, MockContext(), 'critical')
        expected = {'inprogress': [], 'success': [], 'error': [{'status': 'error', 'stackid': 'StackId1', 'region': 'us-east-1', 'detail': ['CREATE_FAILED', [['CREATE_FAILED', 'LogicalResourceId', 'ResourceStatusReason']]], 'artifact': 'cfn_cicd_artifact', 'testname': 'cfn_cicd_testname'}, {'status': 'error', 'stackid': 'StackId1', 'region': 'eu-west-1', 'detail': ['CREATE_FAILED', [['CREATE_FAILED', 'LogicalResourceId', 'ResourceStatusReason']]], 'artifact': 'cfn_cicd_artifact', 'testname': 'cfn_cicd_testname'}]}
        self.assertEqual(expected, cfn_pipeline.create_stacks())

    def test_handle_deletes(self):
        cfn_pipeline = CFNPipeline(logger, clients)
        deleted_stacks = {'inprogress': [{'status': 'inprogress', 'stackid': 'StackId3', 'region': 'us-east-1', 'detail': 'CREATE_IN_PROGRESS', 'artifact': 'cfn_cicd_artifact', 'testname': 'cfn_cicd_testname'}], 'success': [{'status': 'success', 'stackid': 'StackId2', 'region': 'us-west-1', 'detail': 'CREATE_COMPLETE', 'artifact': 'cfn_cicd_artifact', 'testname': 'cfn_cicd_testname'}], 'error': [{'status': 'error', 'stackid': 'StackId1', 'region': 'us-east-1', 'detail': ['CREATE_FAILED', [['CREATE_FAILED', 'LogicalResourceId', 'ResourceStatusReason']]], 'artifact': 'cfn_cicd_artifact', 'testname': 'cfn_cicd_testname'}]}
        self.assertEqual(True, cfn_pipeline.handle_deletes(deleted_stacks, [], 'pre'))

    def test_upload_output_artifact(self):
        cfn_pipeline = CFNPipeline(logger, clients)
        cfn_pipeline.consume_event(event, MockContext(), 'critical')
        self.assertEqual(None, cfn_pipeline.upload_output_artifact({}))

    def test_test_stacks(self):
        cfn_pipeline = CFNPipeline(logger, clients)
        event['CodePipeline.job']['data']['actionConfiguration']['configuration']['UserParameters'] = json.dumps({
            "CITestPath": "ci",
            "ScratchBucket": "ScratchBucket",
            "SNSTopic": "SNSTopic:SNSTopic:SNSTopic:SNSTopic:SNSTopic",
            "ReportKey": "ReportKey",
            "ReportBucket": "ReportBucket",
            "StackCreationRoleArn": "arn::::StackCreationRoleArn",
            "KeyBucket": "KeyBucket"
        })
        cfn_pipeline.consume_event(event, MockContext(), 'critical')
        def test_func(**kwargs):
            return {
                "stackid": "stackid",
                "region": "region",
                "logical_resource_id": "logical_resource_id",
                "physical_resource_id": "physical_resource_id",
                "success": True
            }
        expected = {'success': [{'stackid': 'stackid', 'region': 'region', 'logical_resource_id': 'logical_resource_id', 'testname': 'defaults', 'artifact': 'TemplateArtifact', 'physical_resource_id': 'physical_resource_id'}, {'stackid': 'stackid', 'region': 'region', 'logical_resource_id': 'logical_resource_id', 'testname': 'defaults', 'artifact': 'TemplateArtifact', 'physical_resource_id': 'physical_resource_id'}], 'error': []}
        self.assertEqual(expected, cfn_pipeline.test_stacks(test_func))
        logical_resource_ids = ['testResource']
        self.assertEqual(expected, cfn_pipeline.test_stacks(test_func, logical_resource_ids))
        resource_types = ["AWS::ResourceType"]
        expected = {
            'error': [],
            'success': [{'artifact': 'TemplateArtifact',
               'logical_resource_id': 'logical_resource_id',
               'physical_resource_id': 'physical_resource_id',
               'region': 'region',
               'stackid': 'stackid',
               'testname': 'defaults'},
              {'artifact': 'TemplateArtifact',
               'logical_resource_id': 'logical_resource_id',
               'physical_resource_id': 'physical_resource_id',
               'region': 'region',
               'stackid': 'stackid',
               'testname': 'defaults'}]}
        self.assertEqual(expected, cfn_pipeline.test_stacks(test_func, resource_types=resource_types))
        logical_resource_id_prefix = "Logical"
        self.assertEqual(expected, cfn_pipeline.test_stacks(test_func, resource_types=resource_types, logical_resource_id_prefix=logical_resource_id_prefix))
        resource_types = ["AWS::NonExistant"]
        expected = {'error': [], 'success': []}
        self.assertEqual(expected, cfn_pipeline.test_stacks(test_func, resource_types=resource_types))

    def test_deploy_to_s3(self):
        cfn_pipeline = CFNPipeline(logger, clients)
        event['CodePipeline.job']['data']['actionConfiguration']['configuration']['UserParameters'] = json.dumps({
            "CITestPath": "ci",
            "ScratchBucket": "ScratchBucket",
            "SNSTopic": "SNSTopic:SNSTopic:SNSTopic:SNSTopic:SNSTopic",
            "ReportKey": "ReportKey",
            "ReportBucket": "ReportBucket",
            "StackCreationRoleArn": "arn::::StackCreationRoleArn",
            "KeyBucket": "KeyBucket",
            "DeployBucket": "DeployBucket",
            "DeployKey": "DeployKey"
        })
        cfn_pipeline.consume_event(event, MockContext(), 'critical')
        self.assertEqual(None, cfn_pipeline.deploy_to_s3())

    def test_get_templates(self):
        cfn_pipeline = CFNPipeline(logger, clients)
        cfn_pipeline.consume_event(event, MockContext(), 'critical')
        self.assertIn('aws-vpc.template',cfn_pipeline.get_templates().keys())

    def test_find_in_obj(self):
        cfn_pipeline = CFNPipeline(logger, clients)
        obj = {
            "Resources": {
                "TestResource": {
                    "Type": "AWS::TestResource",
                    "Properties": {
                        "TestList": [
                            {
                                "TestKey": "TestVal"
                            }
                        ]
                    }
                }
            }
        }
        matches = []
        def matching_func(obj, val):
            return True
        self.assertEqual(None, cfn_pipeline.find_in_obj(obj, 'testVal', matching_func, matches, case_sensitive=False))
        expected = [{'regions': [], 'path': '[Resources][TestResource][Type]', 'value': u'aws::testresource'}, {'regions': [], 'path': '[Resources][TestResource][Properties][TestList][0][TestKey]', 'value': u'testval'}]
        self.assertEqual(expected, matches)

    def test_build_execution_report(self):
        cfn_pipeline = CFNPipeline(logger, clients)
        cfn_pipeline.consume_event(event, MockContext(), 'critical')
        self.assertEqual(True, cfn_pipeline.build_execution_report(sns_topic=':::TestTopic', s3_bucket='TestBucket').startswith('Report for pipelineName execution pipelineExecutionId'))

    def test__get_regions(self):
        cfn_pipeline = CFNPipeline(logger, clients)
        self.assertEqual(['us-east-1', 'us-west-1'], cfn_pipeline._get_regions())

    def test_delete_provisioned_product(self):
        cfn_pipeline = CFNPipeline(logger, clients)
        expected = {'status': 'success', 'stackid': 'StackId', 'region': 'us-east-1', 'detail': None}
        self.assertEqual(expected, cfn_pipeline.delete_provisioned_product('pp-ProvisionedProductId', 'StackId', 'us-east-1'))

    def test_provision_product(self):
        cfn_pipeline = CFNPipeline(logger, clients)
        cfn_pipeline.consume_event(event, MockContext(), 'error')
        expected = {'inprogress': [{'status': 'inprogress', 'stackid': 'StackId3', 'region': 'us-east-1', 'detail': 'CREATE_IN_PROGRESS', 'artifact': 'TemplateArtifact', 'testname': 'defaults'}, {'status': 'inprogress', 'stackid': 'StackId3', 'region': 'eu-west-1', 'detail': 'CREATE_IN_PROGRESS', 'artifact': 'TemplateArtifact', 'testname': 'defaults'}], 'success': [], 'error': []}
        self.assertEqual(expected, cfn_pipeline.provision_product())


if __name__ == '__main__':
    unittest.main()
