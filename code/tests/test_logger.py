import mock
import unittest
import logging
import json
from datetime import datetime
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

from logger import Logger


class Tests(unittest.TestCase):

    @mock.patch('logger.Logger.config')
    def test_init(self, config):
        config.return_value = None
        instance = Logger()
        self.assertEqual(instance.job_id, None)
        self.assertEqual(instance.request_id, 'CONTAINER_INIT')
        self.assertEqual(instance.original_job_id, None)
        config.assert_called()

    def test_config(self):
        instance = Logger()
        self.assertEqual(instance.config(request_id='request_id', original_job_id="original_job_id", job_id='job_id',
                        artifact_revision_id='artifact_revision_id', pipeline_execution_id='pipeline_execution_id',
                        pipeline_action='pipeline_action', stage_name='stage_name', pipeline_name='pipeline_name',
                        loglevel='loglevel', botolevel='botolevel'), None)
        self.assertEqual(type(instance.log), logging.LoggerAdapter)
        self.assertEqual(logging.getLogger('boto3').level, 40)
        self.assertEqual(instance.log.logger.level, 20)
        self.assertEqual(instance.request_id, 'request_id')
        self.assertEqual(instance.original_job_id, 'original_job_id')
        self.assertEqual(instance.job_id, 'job_id')
        self.assertEqual(instance.pipeline_execution_id, 'pipeline_execution_id')
        self.assertEqual(instance.artifact_revision_id, 'artifact_revision_id')
        self.assertEqual(instance.pipeline_action, 'pipeline_action')
        self.assertEqual(instance.stage_name, 'stage_name')

    def test_set_boto_level(self):
        instance = Logger()
        self.assertEqual(instance.set_boto_level('debug'), None)
        self.assertEqual(logging.getLogger('boto3').level, 10)

    def test__format(self):
        instance = Logger()
        log_msg = json.loads(instance._format('test message'))
        self.assertEqual(log_msg['message'], 'test message')
        log_msg = json.loads(instance._format('{"test": "message"}'))
        self.assertEqual(log_msg['message']['test'], 'message')
        log_msg = json.loads(instance._format({"test": datetime(2016, 01, 01)}))
        self.assertEqual(log_msg['message'], "{\'test\': datetime.datetime(2016, 1, 1, 0, 0)}")

    @mock.patch('logging.LoggerAdapter')
    def test_log_levels(self, logger):
        instance = Logger()
        instance.log = logger
        instance.debug('I called a debug')
        instance.info('I called a info')
        instance.warning('I called a warning')
        instance.error('I called a error')
        instance.critical('I called a critical')
        logger.debug.assert_called()
        logger.info.assert_called()
        logger.warning.assert_called()
        logger.error.assert_called()
        logger.critical.assert_called()

if __name__ == '__main__':
    unittest.main()