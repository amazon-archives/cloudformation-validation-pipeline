import json
import logging


class Logger(object):
    """Wrapper for a logging object that logs in json and appends AWS CodePipeline identifiers to each log message"""

    def __init__(self, request_id='CONTAINER_INIT', original_job_id=None, job_id=None,
                 loglevel='warning', botolevel='critical'):
        """Initializes logging with minimal settings of request_id, original_job_id and job_id"""
        self.request_id = request_id
        self.original_job_id = original_job_id
        self.job_id = job_id
        self.config(request_id, original_job_id, job_id, loglevel=loglevel, botolevel=botolevel)
        return

    def config(self, request_id='CONTAINER_INIT', original_job_id=None, job_id=None,
               artifact_revision_id=None, pipeline_execution_id=None, pipeline_action=None,
               stage_name=None, pipeline_name=None, loglevel='warning', botolevel='critical'):
        """Configures logging object

        Args:
            request_id (str): lambda request id.
            original_job_id (str): [optional] pipeline job_id from first request in this run.
            job_id (str): [optional] pipeline job_id for the current invocation (differs from original_job_id if this is
                          a continuation invocation).
            artifact_revision_id (str): [optional] commit id for current revision.
            pipeline_execution_id (str): [optional] pipeline execution id (same for all actions/stages in this pipeline
                                         run).
            pipeline_action (str): [optional] pipeline action name.
            stage_name (str): [optional] pipeline stage name.
            pipeline_name (str): [optional] pipeline name.
            loglevel (str): [optional] logging verbosity, defaults to warning.
            botolevel (str): [optional] boto logging verbosity, defaults to critical.
        """

        loglevel = getattr(logging, loglevel.upper(), 20)
        botolevel = getattr(logging, botolevel.upper(), 40)
        mainlogger = logging.getLogger()
        mainlogger.setLevel(loglevel)
        logging.getLogger('boto3').setLevel(botolevel)
        logging.getLogger('botocore').setLevel(botolevel)
        logging.getLogger('nose').setLevel(botolevel)
        logging.getLogger('s3transfer').setLevel(botolevel)
        logfmt = '{"time_stamp": "%(asctime)s", "log_level": "%(levelname)s", "data": %(message)s}\n'
        if len(mainlogger.handlers) == 0:
            mainlogger.addHandler(logging.StreamHandler())
        mainlogger.handlers[0].setFormatter(logging.Formatter(logfmt))
        self.log = logging.LoggerAdapter(mainlogger, {})
        self.request_id = request_id
        self.original_job_id = original_job_id
        self.job_id = job_id
        self.pipeline_execution_id = pipeline_execution_id
        self.artifact_revision_id = artifact_revision_id
        self.pipeline_action = pipeline_action
        self.stage_name = stage_name
        self.pipeline_name = pipeline_name

    def set_boto_level(self, botolevel):
        """Sets boto logging level

        Args:
        botolevel (str): boto3 logging verbosity (critical|error|warning|info|debug)
        """

        botolevel = getattr(logging, botolevel.upper(), 40)
        logging.getLogger('boto3').setLevel(botolevel)
        logging.getLogger('botocore').setLevel(botolevel)
        logging.getLogger('nose').setLevel(botolevel)
        logging.getLogger('s3transfer').setLevel(botolevel)
        return

    def _format(self, message):
        """formats log message in json

        Args:
        message (str): log message, can be a dict, list, string, or json blob
        """

        try:
            message = json.loads(message)
        except Exception:
            pass
        try:
            return json.dumps({
                'request_id': self.request_id, 'original_job_id': self.original_job_id,
                'pipeline_execution_id': self.pipeline_execution_id, 'pipeline_name': self.pipeline_name,
                'stage_name': self.stage_name, 'artifact_revision_id': self.artifact_revision_id,
                'pipeline_action': self.pipeline_action, 'job_id': self.job_id, "message": message
            })
        except Exception:
            return json.dumps({
                'request_id': self.request_id, 'original_job_id': self.original_job_id,
                'pipeline_execution_id': self.pipeline_execution_id, 'pipeline_name': self.pipeline_name,
                'stage_name': self.stage_name, 'artifact_revision_id': self.artifact_revision_id,
                'pipeline_action': self.pipeline_action, 'job_id': self.job_id, "message": str(message)
            })

    def debug(self, message, **kwargs):
        """Wrapper for logging.debug call"""
        self.log.debug(self._format(message), **kwargs)

    def info(self, message, **kwargs):
        """Wrapper for logging.info call"""
        self.log.info(self._format(message), **kwargs)

    def warning(self, message, **kwargs):
        """Wrapper for logging.warning call"""
        self.log.warning(self._format(message), **kwargs)

    def error(self, message, **kwargs):
        """Wrapper for logging.error call"""
        self.log.error(self._format(message), **kwargs)

    def critical(self, message, **kwargs):
        """Wrapper for logging.critical call"""
        self.log.critical(self._format(message), **kwargs)
