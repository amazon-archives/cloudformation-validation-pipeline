import mock
import unittest
import sys
import os
import zipfile

os.environ['TOOLVERSION'] = 'latest'

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
sys.path.append(relative_path_prefix + "/lint_template/")

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

from lint_template import lambda_handler

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

class MockCodeBuildClient(object):

    def __init__(self):
        pass

    def start_build(self, projectName, buildspecOverride):
        return {
            "build": {"id": "test_id", "buildStatus": "IN_PROGRESS"}
        }

    def batch_get_builds(self,ids):
        return {
            "builds": [{"buildStatus": "SUCCEEDED", "phases": None}]
        }


class MockBotoClient(object):
    def __init__(self):
        pass
    def get(self, service, region=None, access_key=None, secret_key=None, session_token=None, s3v4=True):
        if service == 'codebuild':
            return MockCodeBuildClient()
        else:
            raise ValueError("no api mock available for %s" % service)


class TestLambdaHandler(unittest.TestCase):

    @mock.patch('lint_template.clients', MockBotoClient())
    @mock.patch('lint_template.pipeline_run')
    def test_handler_success(self, cfnpl):
        cfnpl.put_job_success.return_value = None
        cfnpl.ci_configs = {"TemplateArtifact": [{"tests": {"default": {"template_file": "template_file.template"}}}]}
        cfnpl.consume_event(event, MockContext(), 'critical')
        self.assertEqual(lambda_handler(event, MockContext()), None)
        cfnpl.put_job_success.assert_called()


    @mock.patch('lint_template.pipeline_run.put_job_failure')
    @mock.patch('lint_template.pipeline_run.consume_event')
    def test_handler_failure(self, consume_event, put_job_failure):
        consume_event.side_effect = raise_exception
        self.assertEqual(lambda_handler(event, MockContext()), None)
        put_job_failure.assert_called()

if __name__ == '__main__':
    unittest.main()