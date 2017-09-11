import sys
import os
import shutil
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


import unittest
from threading import Lock
import mock
from awsclients import AwsClients
from logger import Logger
import boto3

logger = Logger()

class MockClientConfig(object):
    def __init__(self):
        self.region_name = "us-east-2"

class MockS3Client(object):

    def __init__(self):
        self._client_config = MockClientConfig()
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

class MockBotoClient(object):
    def __init__(self):
        self.session = MockBotoSession()
        pass

    def client(self, service, region_name=None, access_key=None, secret_key=None, session_token=None, s3v4=True):
        if service == 's3':
            return MockS3Client()
        else:
            raise ValueError("no api mock available for %s" % service)
    def session(self, *args):
        return None


class MockBotoSession(object):
    def __init__(self):
        pass
    def Session(self, *args, **kwargs):
        return MockBotoSessionClass()
    def get_session(self):
        return MockBotoSessionClass()


class MockBotoSessionClass(object):
    def __init__(self):
        pass
    def get_available_regions(self, *args, **kwargs):
        return ['us-east-1']
    def client(self, service):
        return MockBotoClient().client(service)


class TestAwsClients(unittest.TestCase):
    def test___init__(self):
        aws_clients = AwsClients(logger)
        self.assertEqual({"default_role": {}}, aws_clients._clients)
        self.assertEqual(type(Lock()),type(aws_clients._lock))
        self.assertEqual(logger, aws_clients.logger)

    @mock.patch("awsclients.AwsClients._create_client", mock.MagicMock(return_value=MockBotoClient().client('s3')))
    def test_get(self):
        aws_clients = AwsClients(logger)
        self.assertEqual('us-east-2', aws_clients.get('s3', region='us-east-2')._client_config.region_name)
        self.assertIn('default_sig_version', aws_clients._clients['default_role']['us-east-2']['s3'].keys())
        self.assertIn('session', aws_clients._clients['default_role']['us-east-2'].keys())

    def test_get_available_regions(self):
        aws_clients = AwsClients(logger)
        session = boto3.session.Session()
        regions = session.get_available_regions('s3')
        self.assertEqual(regions, aws_clients.get_available_regions('s3'))

if __name__ == '__main__':
    unittest.main()