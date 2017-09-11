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

print relative_path_prefix

sys.path.append(relative_path_prefix + "/lib/")
sys.path.append(relative_path_prefix + "/create_stack/")

from create_stack import lambda_handler

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


class TestLambdaHandler(unittest.TestCase):

    @mock.patch('create_stack.pipeline_run')
    def test_handler_success(self, cfnpl):
        cfnpl.continue_job_later.return_value = None
        cfnpl.create_stacks.return_value = {'inprogress': ['inprogress'], 'success': [], 'error': []}
        self.assertEqual(lambda_handler(event, MockContext()), None)
        cfnpl.continue_job_later.assert_called()
        cfnpl.continue_job_later.return_value = None
        cfnpl.create_stacks.return_value = {'inprogress': [], 'success': [], 'error': ['error']}
        self.assertEqual(lambda_handler(event, MockContext()), None)
        cfnpl.continue_job_later.assert_called()
        cfnpl.cleanup_failed = False
        cfnpl.continue_job_later.return_value = None
        self.assertEqual(lambda_handler(event, MockContext()), None)
        cfnpl.continue_job_later.assert_called()
        cfnpl.put_job_success.return_value = None
        cfnpl.create_stacks.return_value = {'inprogress': [], 'success': ['success'], 'error': []}
        self.assertEqual(lambda_handler(event, MockContext()), None)
        cfnpl.put_job_success.assert_called()
        cfnpl.continuation_data = {'message': {"stacks": {'inprogress': ['inprogress'], 'success': [], 'error': []}}}
        cfnpl.put_job_success.return_value = None
        self.assertEqual(lambda_handler(event, MockContext()), None)
        cfnpl.put_job_success.assert_called()
        cfnpl.continuation_data = {'message': {"pre-delete":True, "deleting": ['inprogress']}}
        cfnpl.check_statuses.return_value = []
        cfnpl.put_job_success.return_value = None
        self.assertEqual(lambda_handler(event, MockContext()), None)
        cfnpl.put_job_success.assert_called()
        cfnpl.continuation_data = {'message': {'invalid': True}}
        cfnpl.check_statuses.return_value = []
        cfnpl.put_job_success.return_value = None
        self.assertEqual(lambda_handler(event, MockContext()), None)
        cfnpl.put_job_success.assert_called()
        cfnpl.continuation_event = None
        cfnpl.put_job_success.return_value = None
        self.assertEqual(lambda_handler(event, MockContext()), None)
        cfnpl.put_job_success.assert_called()


    @mock.patch('create_stack.pipeline_run.put_job_failure')
    @mock.patch('create_stack.pipeline_run.consume_event')
    def test_handler_failure(self, consume_event, put_job_failure):
        consume_event.side_effect = raise_exception
        self.assertEqual(lambda_handler(event, MockContext()), None)
        put_job_failure.assert_called()

if __name__ == '__main__':
    unittest.main()