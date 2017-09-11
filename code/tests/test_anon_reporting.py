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
sys.path.append(relative_path_prefix + "/anon_reporting/")

from anon_reporting import lambda_handler
from anon_reporting import send_data

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
        "SolutionID": "a-solution-id"
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

class MockUrlopen(object):
    def __init__(self, req):
        pass
    def getcode(self):
        return 200
    def read(self):
        return ''

class TestLambdaHandler(unittest.TestCase):

    @mock.patch("anon_reporting.urllib2.Request", mock.Mock(return_value=None))
    @mock.patch("anon_reporting.urllib2.urlopen", MockUrlopen)
    def test_send_data(self):
        self.assertEqual(None, send_data('uuid', 'solution_id', 'stack_event', 'region', 'stack_id'))

    @mock.patch("anon_reporting.send_data", mock.Mock(return_value=None))
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