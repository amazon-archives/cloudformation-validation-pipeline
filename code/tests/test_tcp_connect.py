import mock
import unittest
import sys
import os
import StringIO

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
sys.path.append(relative_path_prefix + "/tcp_connect/")

from tcp_connect import lambda_handler
from tcp_connect import test_subnet_connectivity

def raise_exception(*args, **kwargs):
    raise Exception("Test Exception")

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
        self.aws_request_id = 'some-request-id'

pipeline_run = mock.MagicMock(pipeline_run=None)

class MockEC2Client(object):

    def __init__(self):
        pass

    def describe_subnets(self, SubnetIds):
        return {
            "Subnets": [
                {
                    "Tags": [
                        {
                            "Key": "Name",
                            "Value": "PRIV_Subnet_DMZ"
                        }
                    ],
                    "VpcId": "test-vpcid"
                }
            ]
        }

    def create_security_group(self, GroupName, Description, VpcId):
        return {"GroupId": "test-security-group"}

    def describe_network_interfaces(self, Filters):
        return {"NetworkInterfaces": [
            {"NetworkInterfaceId": "test-eni-id"}
        ]}

    def delete_network_interface(self, NetworkInterfaceId):
        return None

    def delete_security_group(self, GroupId):
        return True

class MockLambdaClient(object):

    def __init__(self):
        pass

    def create_function(self, **kwargs):
        return {"success": True}

    def invoke(self, **kwargs):
        resp = StringIO.StringIO()
        resp.write('{}')
        resp.seek(0)
        return {"Payload": resp, "StatusCode": 200}

    def delete_function(self, FunctionName):
        return None

class MockIAMClient(object):

    def __init__(self):
        pass

    def create_role(self, RoleName, AssumeRolePolicyDocument):
        return {"Role": {"Arn": "arn:::iamRole"}}

    def put_role_policy(self, RoleName, PolicyName, PolicyDocument):
        return None

    def delete_role_policy(self, RoleName, PolicyName):
        return None

    def delete_role(self, RoleName):
        return None

class MockBotoClient(object):
    def __init__(self):
        pass
    def get(self, service, region=None, access_key=None, secret_key=None, session_token=None, s3v4=True):
        if service == 'ec2':
            return MockEC2Client()
        elif service == 'lambda':
            return MockLambdaClient()
        elif service == 'iam':
            return MockIAMClient()
        else:
            raise ValueError("no api mock available for %s" % service)
    def get_available_regions(self, service):
        return ['us-east-1']

def mock_test_stacks(test_function, resource_types, logical_resource_id_prefix):
    test_subnet_connectivity('us-east-1', 'stackid', 'LogicalResourceId', "PhysicalResourceId")
    return {"error": [], "success": ["some-id"]}

class TestLambdaHandler(unittest.TestCase):

    @mock.patch('tcp_connect.clients', MockBotoClient())
    @mock.patch('tcp_connect.pipeline_run')
    def test_handler_success(self, cfnpl):
        cfnpl.put_job_success.return_value = None
        cfnpl.test_stacks = mock_test_stacks
        self.assertEqual(lambda_handler(event, MockContext()), None)
        cfnpl.put_job_success.assert_called()


    @mock.patch('tcp_connect.pipeline_run.put_job_failure')
    @mock.patch('tcp_connect.pipeline_run.consume_event')
    def test_handler_failure(self, consume_event, put_job_failure):
        consume_event.side_effect = raise_exception
        self.assertEqual(lambda_handler(event, MockContext()), None)
        put_job_failure.assert_called()

if __name__ == '__main__':
    unittest.main()