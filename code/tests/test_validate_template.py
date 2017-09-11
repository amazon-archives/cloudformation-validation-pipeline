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
sys.path.append(relative_path_prefix + "/validate_template/")

from validate_template import lambda_handler


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

class MockCfnClient(object):

    def __init__(self):
        pass

    def validate_template(self, TemplateUrl):
        return None

class MockBotoClient(object):
    def __init__(self):
        pass
    def get(self, service, region=None, access_key=None, secret_key=None, session_token=None, s3v4=True):
        if service == 'cloudformation':
            return MockCfnClient()
        else:
            raise ValueError("no api mock available for %s" % service)

class MockCFNPipeline(object):

    def __init__(self):
        self.ci_configs = {"ScratchBucket": "scratch_bucket_name"}
        self.user_params = {"ScratchBucket": "scratch_bucket_name" }

pipeline_run = mock.MagicMock(pipeline_run=None)


class TestLambdaHandler(unittest.TestCase):

    @mock.patch('validate_template.pipeline_run')
    @mock.patch('validate_template.clients', mock.Mock(return_value=MockBotoClient()))
    @mock.patch('cfnpipeline.CFNPipeline.put_job_success')
    def test_handler_success(self, put_job_success, cfnpl):
        cfnpl.user_params = {"ScratchBucket": "scratch_bucket_name" }
        cfnpl.enable_anon_usage_reporting = 'No'
        cfnpl.ci_configs = {"artifact": [{"tests": {"test": {"template_file": "file.template"}}}]}
        cfnpl.upload_template.return_value = 'https://my-template.url/hahaha.template'
        cfnpl.put_job_success.return_value = None
        self.assertEqual(lambda_handler(event, MockContext()), None)
        cfnpl.put_job_success.assert_called()


    @mock.patch('validate_template.pipeline_run.put_job_failure')
    @mock.patch('validate_template.pipeline_run.consume_event')
    def test_handler_failure(self, consume_event, put_job_failure):
        consume_event.side_effect = raise_exception
        self.assertEqual(lambda_handler(event, MockContext()), None)
        put_job_failure.assert_called()

if __name__ == '__main__':
    unittest.main()