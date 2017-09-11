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
sys.path.append(relative_path_prefix + "/ami_check/")

from ami_check import lambda_handler

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

class MockEC2Client(object):

    def __init__(self):
        pass

    def describe_images(self, ImageIds):
        if ImageIds == ['ami-test']:
            return {
                "Images": [
                    {"Name": "ami-test"}
                ]
            }
        elif ImageIds == ['ami-testDated']:
            return {
                "Images": [
                    {"Name": "ami-testLatest"}
                ]
            }
        else:
            raise Exception("The image id '[%s]' does not exist" % ImageIds[0])

class MockBotoClient(object):
    def __init__(self):
        pass
    def get(self, service, region=None, access_key=None, secret_key=None, session_token=None, s3v4=True):
        if service == 'ec2':
            return MockEC2Client()
        else:
            raise ValueError("no api mock available for %s" % service)

class MockCFNPipeline(object):

    def __init__(self):
        self.ci_configs = {"ScratchBucket": "scratch_bucket_name"}
        self.user_params = {"ScratchBucket": "scratch_bucket_name" }

pipeline_run = mock.MagicMock(pipeline_run=None)


class TestLambdaHandler(unittest.TestCase):

    @mock.patch('ami_check.pipeline_run')
    @mock.patch('ami_check.find_ami_ids')
    @mock.patch('ami_check.clients', MockBotoClient())
    @mock.patch('cfnpipeline.CFNPipeline.put_job_success')
    def test_handler_success(self, put_job_success, find_ami_ids, cfnpl):
        cfnpl.put_job_success.return_value = None
        cfnpl.get_templates.return_value = None
        find_ami_ids.return_value = [{'value': "ami-test", 'regions': ['us-east-1']}]
        self.assertEqual(lambda_handler(event, MockContext()), None)
        cfnpl.put_job_success.assert_called()
        cfnpl.put_job_success.return_value = None
        find_ami_ids.return_value = [{'value': "ami-testDated", 'regions': ['us-east-1']}]
        self.assertEqual(lambda_handler(event, MockContext()), None)
        cfnpl.put_job_success.assert_called()
        cfnpl.put_job_failure.return_value = None
        find_ami_ids.return_value = [{'value': "ami-test", 'regions': []}]
        self.assertEqual(lambda_handler(event, MockContext()), None)
        cfnpl.put_job_failure.assert_called()
        cfnpl.put_job_failure.return_value = None
        find_ami_ids.return_value = [{'value': "ami-test-fail", 'regions': ['us-east-1']}]
        self.assertEqual(lambda_handler(event, MockContext()), None)
        cfnpl.put_job_failure.assert_called()


    @mock.patch('ami_check.pipeline_run.put_job_failure')
    @mock.patch('ami_check.pipeline_run.consume_event')
    def test_handler_failure(self, consume_event, put_job_failure):
        consume_event.side_effect = raise_exception
        self.assertEqual(lambda_handler(event, MockContext()), None)
        put_job_failure.assert_called()

if __name__ == '__main__':
    unittest.main()
