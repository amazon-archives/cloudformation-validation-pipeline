import mock
import unittest
import sys
import os
from datetime import datetime
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
sys.path.append(relative_path_prefix + "/cleanup_on_stack_delete/")

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

from cleanup_on_stack_delete import lambda_handler

def raise_exception(*args, **kwargs):
    raise Exception("Test Exception")

event = {
    "RequestId": 'a-request-id',
    "ResponseURL": "http://a.response.url",
    "StackId": "arn:::a-stack-id",
    "LogicalResourceId": "a-logical-resource-id",
    "PhysicalResourceId": "a-physical-resource-id",
    "ResourceProperties": {
        "loglevel": "error",
        "botolevel": "error",
        "SolutionID": "a-solution-id",
        "Pipeline": "pipelineName"
    }
}

class MockContext(object):

    def __init__(self):
        self.aws_request_id = 'some-request-id'
        self.log_stream_name = 'a-logstream'

    def get_remaining_time_in_millis(self):
        return 15000

class MockPut(object):
    def __init__(self, url, data, headers):
        self.reason = 'a-response'

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
                        "StackId": "pp-StackId1"
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
                        "StackId": "pp-StackId3"
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
                        "StackId": "pp-StackId2"
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
                    "StackId": "pp-ProvisionedProductId",
                    "StackName": "pp-ProvisionedProductId",
                    "StackStatus": "CREATE-COMPLETE",
                    "CreationTime": datetime.now()
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
        self.session = MockBotoSession()
        pass

    def client(self, service, region_name=None, access_key=None, secret_key=None, session_token=None, s3v4=True):
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
    def session(self, *args):
        return None


class MockBotoSession(object):
    def __init__(self):
        pass
    def Session(self, *args, **kwargs):
        return MockBotoSessionClass()

class MockBotoSessionClass(object):
    def __init__(self):
        pass
    def get_available_regions(self, *args, **kwargs):
        return ['us-east-1']

class TestLambdaHandler(unittest.TestCase):

    @mock.patch("cleanup_on_stack_delete.boto3", MockBotoClient())
    @mock.patch("botocore.vendored.requests.put", MockPut)
    @mock.patch("crhelper.timeout",mock.Mock(return_value=None))
    def test_handler_success(self):
        event['RequestType'] = "Create"
        self.assertEqual(None, lambda_handler(event, MockContext()))
        event['RequestType'] = "Update"
        self.assertEqual(None, lambda_handler(event, MockContext()))
        event['RequestType'] = "Delete"
        self.assertEqual(None, lambda_handler(event, MockContext()))


if __name__ == '__main__':
    unittest.main()