import mock
import unittest
import sys
import os

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
sys.path.append(relative_path_prefix + "/subnet_name/")

from subnet_name import lambda_handler
from subnet_name import test_subnet_name


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
                    ]
                }
            ]
        }

class MockBotoClient(object):
    def __init__(self):
        pass
    def get(self, service, region=None, access_key=None, secret_key=None, session_token=None, s3v4=True):
        if service == 'ec2':
            return MockEC2Client()
        else:
            raise ValueError("no api mock available for %s" % service)


def mock_test_stacks(test_function, resource_types):
    test_subnet_name('us-east-1', 'stackid', 'LogicalResourceId', "PhysicalResourceId")

class TestLambdaHandler(unittest.TestCase):

    @mock.patch('subnet_name.clients', MockBotoClient())
    @mock.patch('subnet_name.pipeline_run')
    def test_handler_success(self, cfnpl):
        cfnpl.put_job_failure.return_value = None
        cfnpl.test_stacks = mock_test_stacks
        cfnpl.ci_configs = {"TemplateArtifact": [{"tests": {"default": {"template_file": "template_file.template"}}}]}
        cfnpl.consume_event(event, MockContext(), 'critical')
        self.assertEqual(lambda_handler(event, MockContext()), None)
        cfnpl.put_job_failure.assert_called()


    @mock.patch('subnet_name.pipeline_run.put_job_failure')
    @mock.patch('subnet_name.pipeline_run.consume_event')
    def test_handler_failure(self, consume_event, put_job_failure):
        consume_event.side_effect = raise_exception
        self.assertEqual(lambda_handler(event, MockContext()), None)
        put_job_failure.assert_called()

if __name__ == '__main__':
    unittest.main()