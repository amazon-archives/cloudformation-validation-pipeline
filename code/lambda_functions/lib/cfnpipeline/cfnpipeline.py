import botocore
from cStringIO import StringIO
from datetime import datetime
from functools import partial
from hashlib import sha256
import json
from multiprocessing.dummy import Pool as ThreadPool
import os
import random
import re
import shutil
import string
import time
from urllib2 import Request
from urllib2 import urlopen
import uuid
import yaml
from zipfile import ZipFile


class CFNPipeline(object):

    """Helper class for working with AWS CloudFormation templates and stacks in AWS CodePipeline."""

    def __init__(self, logger, clients):
        """Initializes several variables, many are set in the consume_event method.

        Args:
            logger (obj): provide a logging object to use
            clients (obj): provide an instance of AwsClients to use for fetching boto3 clients
        """

        self.logger = logger
        self.clients = clients
        self.job_id = None
        self.original_job_id = None
        self.job_data = None
        self.artifacts = None
        self.user_params = None
        self.output_artifacts = None
        self.ci_test_path = None
        self.continuation_data = None
        self.continuation_event = False
        self.ci_configs = None
        self.stack_statuses = {
            "failed": [
                'CREATE_FAILED', 'ROLLBACK_FAILED', 'ROLLBACK_COMPLETE', 'DELETE_FAILED',
                'UPDATE_ROLLBACK_FAILED', 'UPDATE_ROLLBACK_COMPLETE'
            ],
            "inprogress": [
                'CREATE_IN_PROGRESS', 'REVIEW_IN_PROGRESS', 'ROLLBACK_IN_PROGRESS', 'DELETE_IN_PROGRESS',
                'UPDATE_IN_PROGRESS', 'UPDATE_COMPLETE_CLEANUP_IN_PROGRESS', 'UPDATE_ROLLBACK_IN_PROGRESS',
                'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS'
            ],
            "complete": ['CREATE_COMPLETE', 'DELETE_COMPLETE', 'UPDATE_COMPLETE']
        }
        self.event_statuses = {
            "failed": ['CREATE_FAILED', 'DELETE_FAILED', 'UPDATE_FAILED'],
            "inprogress": ['CREATE_IN_PROGRESS', 'DELETE_IN_PROGRESS', 'UPDATE_IN_PROGRESS'],
            "complete": ['CREATE_COMPLETE', 'DELETE_COMPLETE', 'DELETE_SKIPPED', 'UPDATE_COMPLETE']
        }
        self.ignore_event_failure_reasons = ['Resource creation cancelled']
        self.region = os.environ['AWS_DEFAULT_REGION']
        self.codepipeline_client = self.clients.get('codepipeline')
        self.pipeline_context = None
        self.pipeline_name = None
        self.stage_name = None
        self.pipeline_action = None
        self.pipeline_state = None
        self.pipeline_execution_id = None
        self.artifact_revision_data = None
        self.artifact_revision_id = None
        self.artifact_type = None
        self.report_s3_bucket = None
        self.report_s3_prefix = ''
        self.report_sns_topic = None
        self.report_sns_region = None
        self.uuid_ns = uuid.UUID('{550eda57-0a18-4dd4-9876-c340f2d77dc7}')
        self.anon_usage_reporting_url = 'https://oszclq8tyh.execute-api.us-east-1.amazonaws.com/prod/generic'
        return

    def put_job_success(self, message):
        """Sends a success response for this action's job id to AWS CodePipeline.

        Args:
            message (str): informational message to include in response
        """
        self.logger.info({'event': 'return_success'})
        self.anon_reporting(message, 'action_success')
        self.codepipeline_client.put_job_success_result(jobId=self.job_id)

    def put_job_failure(self, message):
        """Sends a failure response for this action's job id to AWS CodePipeline.

        Args:
            message (str): informational error message to include in response
        """
        self.logger.info({'event': 'return_failure'})
        self.logger.error(message)
        self.anon_reporting(message, 'action_failure')
        if len(message) > 265:
            message = message[0:211] + '... For full details see CloudWatch logs.'
        self.codepipeline_client.put_job_failure_result(
            jobId=self.job_id,
            failureDetails={'message': message, 'type': 'JobFailed'}
        )

    def continue_job_later(self, message):
        """Sends a continuation response for this action's job id to AWS CodePipeline.

        Results in AWS CodePipeline re-firing this event later, including a continuation token.
        The continuation-token is a json blob containing the message and original job_id.
        The message can contain json if there is state data to be passed to subsequent executions

        Args:
            message (str): informational message to include in response
        """

        self.logger.info({'event': 'return_continue'})
        continuation_token = json.dumps({'job_id': self.original_job_id, 'message': message})
        if len(continuation_token) > 2048:
            continuation_token = json.dumps({
                'job_id': self.original_job_id,
                's3': self._put_continuation_data(message)
            })
        self.codepipeline_client.put_job_success_result(
            jobId=self.job_id,
            continuationToken=continuation_token
        )

    def anon_reporting(self, message, status):
        """Sends anonymous usage report data to AWS.

        Sends anonymous data about pipeline actions. Can be opted out by setting the usage reporting
        parameter in the AWS CloudFormation stack, or manually by setting the SEND_ANONYMOUS_DATA
        AWS Lambda environment variable to 'No'.

        Args:
            message (str): informational message to include in response
            status (str): type of message, eg.: "action_failure" or "action_success"
        """
        try:
            if self.enable_anon_usage_reporting != 'Yes':
                return
            time_stamp = str(datetime.utcnow().isoformat())
            try:
                json.dumps(message)
            except Exception:
                self.logging.debug("anon_reporting: Failed to dump message to json", exc_info=1)
                message = str(message)
            message = {
                "region": self.region,
                "stage_name": self.stage_name,
                "pipeline_action": self.pipeline_action,
                "artifact_type": self.artifact_type,
                "pipeline_hash": sha256(self.pipeline_name).hexdigest(),
                "execution_hash": sha256(self.pipeline_execution_id).hexdigest(),
                "revision_hash": sha256(self.artifact_revision_id).hexdigest(),
                "status": status,
                "message": message
            }
            postDict = {
                'Data': message,
                'TimeStamp': time_stamp,
                'Solution': 'SO0025a',
                'UUID': self.anon_usage_reporting_uuid
            }
            headers = {'content-type': 'application/json'}
            req = Request(self.anon_usage_reporting_url, json.dumps(postDict), headers)
            rsp = urlopen(req)
            content = rsp.read()
            rspcode = rsp.getcode()
            self.logger.debug('Response Code: {}'.format(rspcode))
            self.logger.debug('Response Content: {}'.format(content))
        except Exception:
            self.logger.debug("anon_reporting: Failed to report usage", exc_info=1)
        return

    def _put_continuation_data(self, message):
        self.logger.debug("Putting continuationToken message on s3...")
        s3_client = self.clients.get('s3')
        bucket = self.user_params['ScratchBucket']
        key = "continuationTokens/%s" % self.original_job_id
        s3_client.put_object(Bucket=bucket, Key=key, Body=StringIO(json.dumps(message)).read())
        return {'bucket': bucket, 'key': key}

    def _fetch_continuation_data(self):
        self.logger.debug("Getting continuationToken...")
        token = json.loads(self.job_data['continuationToken'])
        self.original_job_id = token['job_id']
        if "s3" in token.keys():
            self.logger.debug("Getting continuationToken message from s3...")
            s3_client = self.clients.get('s3')
            body = s3_client.get_object(
                Bucket=token['s3']['bucket'],
                Key=token['s3']['key']
            )['Body']
            message = json.loads(body.read())
            token['message'] = message
            token.pop('s3')
        return token

    def consume_event(self, event, context, loglevel='info'):
        """Handles the input event AWS Lambda receives from AWS CodePipeline.

        Fetches several variables from the event for re-use in the class.
        Gets information about the running action in AWS CodePipeline (name,stage,executionid, etc).
        Configures the logger to add several ids to the log format
        fetches artifacts from s3 and parses the ci config files

        Args:
            event (dict): lambda event
            context (obj): lambda context
            loglevel (str): optionally set log verbosity
        """

        self.logger.debug("Split event into usable pieces...")
        self.job_id = event['CodePipeline.job']['id']
        self.job_data = event['CodePipeline.job']['data']
        if 'continuationToken' not in self.job_data:
            self.original_job_id = self.job_id
        else:
            self.continuation_data = self._fetch_continuation_data()
        self.logger.config(context.aws_request_id, job_id=self.job_id, original_job_id=self.original_job_id,
                           loglevel=loglevel)
        cp = self.clients.get('codepipeline')
        response = cp.get_job_details(jobId=self.job_id)
        self.logger.debug({"api": "get_job_details", "response": response})
        self.pipeline_context = response['jobDetails']['data']['pipelineContext']
        self.pipeline_name = self.pipeline_context['pipelineName']
        self.stage_name = self.pipeline_context['stage']['name']
        self.pipeline_action = self.pipeline_context['action']['name']
        response = cp.get_pipeline_state(name=self.pipeline_name)
        self.logger.debug({"api": "get_pipeline_state", "response": response})
        self.pipeline_state = response
        for stage in self.pipeline_state['stageStates']:
            if stage['stageName'] == self.stage_name:
                self.pipeline_execution_id = stage['latestExecution']['pipelineExecutionId']
        response = cp.get_pipeline_execution(pipelineName=self.pipeline_name,
                                             pipelineExecutionId=self.pipeline_execution_id)
        self.logger.debug({"api": "get_pipeline_execution", "response": response})
        self.artifact_revision_data = response['pipelineExecution']['artifactRevisions'][0]
        self.artifact_revision_id = self.artifact_revision_data['revisionId']
        self.logger.config(context.aws_request_id, job_id=self.original_job_id, original_job_id=self.job_id,
                           pipeline_execution_id=self.pipeline_execution_id, stage_name=self.stage_name,
                           pipeline_action=self.pipeline_action, pipeline_name=self.pipeline_name,
                           artifact_revision_id=self.artifact_revision_id, loglevel=loglevel)
        self.artifacts = self.job_data['inputArtifacts']
        self.output_artifacts = self.job_data['outputArtifacts']
        try:
            self.user_params = json.loads(
                self.job_data['actionConfiguration']['configuration']['UserParameters'])
        except Exception as e:
            self.logger.error("Failed to parse user parameters", exc_info=1)
            msg = "Failed to parse user parameters (\"%s\") %s"
            self.put_job_failure(msg % (
                self.job_data['actionConfiguration']['configuration']['UserParameters'], str(e)))
            raise ValueError(msg % (
                self.job_data['actionConfiguration']['configuration']['UserParameters'], str(e)))
        if "CITestPath" not in self.user_params.keys():
            self.put_job_failure("CITestPath missing from user parameters, cannot continue...")
            self.logger.error("CITestPath missing from user parameters, cannot continue...")
            raise ValueError("CITestPath missing from user parameters, cannot continue...")
        if "CleanupNonFailed" in self.user_params:
            if self.user_params["CleanupNonFailed"] == 'No':
                self.cleanup_non_failed = False
            else:
                self.cleanup_non_failed = True
        if "CleanupFailed" in self.user_params:
            if self.user_params["CleanupFailed"] == 'Yes':
                self.cleanup_failed = True
            else:
                self.cleanup_failed = False
        if "CleanupPrevious" in self.user_params:
            if self.user_params["CleanupPrevious"] == 'No':
                self.cleanup_previous = False
            else:
                self.cleanup_previous = True
        if 'continuationToken' not in self.job_data:
            self.logger.debug("This is a new pipeline run...")
            self.continuation_event = False
            self.continuation_data = None
            self._fetch_artifact()
            self.ci_configs = self._get_ci_configs()
        else:
            self.logger.debug("This is a continuation event...")
            self.continuation_event = True
            self.ci_configs = self.continuation_data['message']['configs']
        if 'ReportBucket' in self.user_params:
            self.report_s3_bucket = self.user_params['ReportBucket']
        if 'ReportKey' in self.user_params:
            self.report_s3_prefix = self.user_params['ReportKey']
        if 'SNSTopic' in self.user_params:
            self.report_sns_topic = self.user_params['SNSTopic']
            self.report_sns_region = self.report_sns_topic.split(':')[3]
        try:
            self.enable_anon_usage_reporting = os.environ['SEND_ANONYMOUS_DATA']
        except Exception:
            self.enable_anon_usage_reporting = 'Yes'
        try:
            sts_client = self.clients.get('sts')
            self.account_id = sts_client.get_caller_identity()['Account']
            pl_ns = "%s:%s:%s" % (self.account_id, self.region, self.pipeline_name)
            self.anon_usage_reporting_uuid = str(uuid.uuid5(self.uuid_ns, pl_ns))
        except Exception:
            self.anon_usage_reporting_uuid = str(self.uuid_ns)
        return

    def _fetch_artifact(self):
        """Fetches input artifact from S3 and unzips it in /tmp/artifacts/"""

        s3_client = self.clients.get(
            's3',
            region=None,
            access_key=self.job_data['artifactCredentials']['accessKeyId'],
            secret_key=self.job_data['artifactCredentials']['secretAccessKey'],
            session_token=self.job_data['artifactCredentials']['sessionToken'],
            s3v4=True
        )
        a = self.artifacts[0]
        a_path = '/tmp/artifacts/%s' % (self.pipeline_name)
        try:
            shutil.rmtree(a_path)
        except Exception:
            pass
        os.makedirs(a_path)
        bucket = a['location']['s3Location']['bucketName']
        key = a['location']['s3Location']['objectKey']
        self.logger.debug(bucket)
        self.logger.debug(key)
        response = s3_client.get_object(Bucket=bucket, Key=key)
        f = open('/tmp/artifact.zip', 'wb')
        f.write(response['Body'].read())
        f.close()
        ZipFile('/tmp/artifact.zip').extractall('%s/%s' % (a_path, a['name']))
        os.remove('/tmp/artifact.zip')
        self.logger.debug("Fetched artifacts from s3...")
        paths = []
        for root, dirs, files in os.walk(a_path):
            paths.append([root, dirs, files])
            self.logger.debug({"event": "artifact_contents", "files": [root, dirs, files]})
        self.artifact_type = 'template'
        if len(paths) == 2:
            if paths[1][1] == [] and paths[1][2] == ["artifact.json"]:
                self.artifact_type = 'stack'
        return

    def _get_ci_configs(self):
        """parses ci config yaml files.

        returns a dict containing lists of parsed contents of each config file
        in each artifact (only 1 artifact supported at present).

        Config file can contain any valid yaml, but must contain at least one test
        that specifies at least parameter_input and template_file, for example:

        If artifact contains a template repo, then config is fetched from all .yml
        files in /ci/ folder.
        If there are duplicate keys defined in different config files they are
        overwritten in alphabetical filename order::

            tests:
              defaults:
                parameter_input: aws-vpc-defaults.json
                template_file: aws-vpc.template

        Returns:
            dict: key is config file name, value is the yaml contents converted to a python dict
        """
        a = self.artifacts[0]["name"]
        if self.artifact_type == 'template':
            configs = {}
            configs[a] = []
            log_msg = "getting configs from /tmp/artifacts/%s/%s/%s" % (
                self.pipeline_name, a, self.user_params["CITestPath"])
            self.logger.debug(log_msg)
            for root, dirs, files in os.walk("/tmp/artifacts/%s/%s/%s" % (
                    self.pipeline_name, a, self.user_params["CITestPath"])):
                self.logger.debug({"event": "configs_contents", "files": [root, dirs, files]})
                for file in files:
                    if file.endswith(".yml"):
                        with open(os.path.join(root, file), 'r') as stream:
                            configs[a].append(yaml.load(stream))
        elif self.artifact_type == 'stack':
            with open("/tmp/artifacts/%s/%s/artifact.json" % (self.pipeline_name, a), 'r') as stream:
                configs = json.load(stream)
            for s in configs["Stacks"]:
                for a in configs["Configs"][s['artifact']]:
                    if s['testname'] in a["tests"].keys():
                        if 'built_stacks' not in a["tests"][s['testname']].keys():
                            a["tests"][s['testname']]['built_stacks'] = {}
                        if s['region'] not in a["tests"][s['testname']]['built_stacks'].keys():
                            a["tests"][s['testname']]['built_stacks'][s['region']] = []
                        a["tests"][s['testname']]['built_stacks'][s['region']].append(s['stackid'])
            configs = configs["Configs"]
        return configs

    def _check_stack_status(self, stack):
        """checks the status of a particular stack

        Args:
            stack (dict): contains region and stackid keys describing a cloudformation stack
        """
        try:
            self.logger.debug('check_stack_status: %s' % stack)
            region = stack['region']
            stack_id = stack['stackid']
            cfn = self.clients.get('cloudformation', region)
            self.logger.debug("Checking stack status %s in %s" % (stack_id, region))
            s = cfn.describe_stacks(StackName=stack_id)['Stacks'][0]
            artifact, testname = None, None
            for tag in s['Tags']:
                if tag['Key'] == 'cfn_cicd_artifact':
                    artifact = tag['Value']
                if tag['Key'] == 'cfn_cicd_testname':
                    testname = tag['Value']
            if s['StackStatus'] in self.stack_statuses["failed"]:
                stack_events = cfn.describe_stack_events(StackName=s['StackId'])['StackEvents']
                error_events = []
                for e in stack_events:
                    is_failed = e['ResourceStatus'] in self.event_statuses['failed']
                    if 'ResourceStatusReason' in e:
                        dont_ignore = e['ResourceStatusReason'] not in self.ignore_event_failure_reasons
                    else:
                        dont_ignore = True
                    if is_failed and dont_ignore:
                        error_events.append(
                            [e['ResourceStatus'], e['LogicalResourceId'], e['ResourceStatusReason']]
                        )
                try:
                    state = [s['StackStatus'], s['StackStatusReason'], error_events]
                except Exception:
                    try:
                        state = [s['StackStatus'], error_events]
                    except Exception:
                        state = [s['StackStatus']]

                results = {'status': 'error', 'detail': state}
            elif s['StackStatus'] in self.stack_statuses["inprogress"]:
                results = {'status': 'inprogress', 'detail':  s['StackStatus']}
            elif s['StackStatus'] in self.stack_statuses["complete"]:
                results = {'status': 'success', 'detail':  s['StackStatus']}
            else:
                raise NameError("Encountered unsupported StackStatus %s" % s['StackStatus'])
            if artifact and testname:
                results.update({'artifact': artifact, 'testname': testname})
            results.update({'stackid': s['StackId'], 'region': region})
            return results
        except Exception:
            self.logger.error("_check_stack_status failed", exc_info=1)
            raise

    def check_statuses(self, stacks):
        """Checks status of a list of stacks

        Args:
            stacks (list): a list containing dicts describing AWS CloudFormation stacks (region and stackid)
        """
        successes = []
        errors = []
        inprogress = []
        regions = []
        for s in stacks:
            if s['region'] not in regions:
                regions.append(s['region'])
        if len(regions) > 0:
            self.logger.debug("check_statuses: %s" % stacks)
            pool = ThreadPool(len(regions))
            results = pool.map(self._check_stack_status, stacks)
            pool.close()
            pool.join()
            for r in results:
                if r['status'] == 'success':
                    successes.append(r)
                elif r['status'] == 'inprogress':
                    inprogress.append(r)
                else:
                    errors.append(r)
        self.logger.debug("stack statuses: %s " % [successes, inprogress, errors])
        return {"success": successes, "inprogress": inprogress, "error": errors}

    def cleanup_previous_stacks(self):
        """Deletes stacks from previous pipeline runs

        Returns:
            list: AWS CloudFormation stackids
        """
        stacks = []
        self.logger.debug("configs: %s" % str(self.ci_configs))
        for artifact in self.ci_configs.keys():
            for config in self.ci_configs[artifact]:
                self.logger.debug("config: %s" % str(config))
                for testname in config['tests']:
                    self.logger.debug("testname: %s" % str(testname))
                    test = config['tests'][testname]
                    self.logger.debug("test %s" % str(test))
                    regions = self._build_regions(config, test)
                    self.logger.debug("regions %s" % str(regions))
                    pool = ThreadPool(len(regions))
                    func = partial(self._get_previous, artifact=artifact, testname=testname)
                    results = pool.map(func, regions)
                    pool.close()
                    pool.join()
                    self.logger.debug("Stacks to add to delete list: %s" % results)
                    for r in results:
                        stacks += r
        self.logger.debug("Deleting Stacks: %s" % str(stacks))
        return self.delete_stacks(stacks)

    def _get_previous(self, r, artifact, testname):
        """gets a list of stacks that are not deleted and associated with previous pipeline runs.

        Args:
            r (str): region
            artifact (str): artifact name
            testname (str): name of test as defined in the ci config file
        """

        stacks = []
        cfn = self.clients.get('cloudformation', r)
        response = cfn.describe_stacks()
        for s in response['Stacks']:
            self.logger.debug("stack: %s" % str(s))
            tags = {t['Key']: t['Value'] for t in s['Tags']}
            if set(["cfn_cicd_artifact", "cfn_cicd_jobid", "cfn_cicd_testname"]).issubset(tags.keys()):
                if tags["cfn_cicd_artifact"] == artifact and testname == tags["cfn_cicd_testname"] and tags['cfn_cicd_pipeline'] == self.pipeline_name:
                    stacks.append({'artifact': artifact, 'testname': testname, 'region': r,
                                   'stackid': s['StackId']})
        return stacks

    def delete_provisioned_product(self, provisioned_product_id, stack_id, region):
        """Deletes a particular provisioned product and all the other related AWS Service Catalog artifacts.

        Args:
            Provisioned product (str): provisioned_product_id for provisioned product to be deleted
        """
        sc = self.clients.get('servicecatalog', region)
        cfn = self.clients.get('cloudformation', region)
        try:
            self.logger.debug("Deleting provisioned product %s in %s" % (provisioned_product_id, region))
            response = sc.scan_provisioned_products(AccessLevelFilter={'Key': 'Account', 'Value': 'self'})
            while 'PageToken' in response:
                for item in response['ProvisionedProducts']:
                    if item['Id'] == provisioned_product_id:
                        record_id = item['LastRecordId']
                response = sc.scan_provisioned_products(AccessLevelFilter={'Key': 'Account', 'Value': 'self'},
                                                        PageSize=1,
                                                        PageToken=response['PageToken']
                                                        )
            for item in response['ProvisionedProducts']:
                if item['Id'] == provisioned_product_id:
                    record_id = item['LastRecordId']
            response = sc.describe_record(Id=record_id)
            product_id = response['RecordDetail']['ProductId']
            try:
                response = sc.terminate_provisioned_product(ProvisionedProductId=provisioned_product_id, TerminateToken=str(uuid.uuid4()))
                self.logger.debug("Provisioned product %s terminated" % provisioned_product_id)
            except Exception as e:
                self.logger.error("Failed to terminate provisioned product %s. Falling back to deleting the CloudFormation stack instead" % (provisioned_product_id), exc_info=1)
                try:
                    self.logger.debug("Deleting stack %s in %s" % (stack_id, region))
                    cfn.delete_stack(StackName=stack_id)
                except Exception as e:
                    self.logger.error("Failed to delete stack %s in %s" % (stack_id, region), exc_info=1)
                    raise e
            response = sc.list_portfolios_for_product(ProductId=product_id)
            portfolio_id = response['PortfolioDetails'][0]['Id']
            response = sc.list_principals_for_portfolio(PortfolioId=portfolio_id)
            principal_arn = response['Principals'][0]['PrincipalARN']
            response = sc.disassociate_principal_from_portfolio(PortfolioId=portfolio_id, PrincipalARN=principal_arn)
            self.logger.debug("Principal %s disassociated from portfolio %s" % (principal_arn, portfolio_id))
            response = sc.list_constraints_for_portfolio(PortfolioId=portfolio_id)
            constraint_id = response['ConstraintDetails'][0]['ConstraintId']
            response = sc.delete_constraint(Id=constraint_id)
            self.logger.debug("Constraint %s deleted from portfolio %s" % (constraint_id, portfolio_id))
            response = sc.disassociate_product_from_portfolio(ProductId=product_id, PortfolioId=portfolio_id)
            self.logger.debug("Product %s disassociated from portfolio %s" % (product_id, portfolio_id))
            response = sc.delete_product(Id=product_id)
            self.logger.debug("Product %s deleted from %s" % (product_id, region))
            response = sc.delete_portfolio(Id=portfolio_id)
            self.logger.debug("Portfolio %s deleted from %s" % (portfolio_id, region))
            return {'status': "success", 'stackid': stack_id, 'region': region, 'detail': None}
        except Exception as e:
            self.logger.error("Failed to delete provisioned product %s with stack %s in %s" % (provisioned_product_id,
                                                                                               stack_id,
                                                                                               region), exc_info=1)
            return {'status': "error", 'stackid': stack_id, 'region': region, 'detail': str(e)}

    def _delete_stack(self, stack):
        """Deletes a particular stack.

        Args:
            stack (str): stackid (arn) for stack to be deleted
        """
        self.logger.debug('delete_stack: %s' % stack)
        region = stack['region']
        stack_id = stack['stackid']
        # Check for Service Catalog stacks
        match = re.search(r'(pp-)\w+', stack_id)
        if match is not None:
            self.logger.debug('Service Catalog product detected: %s with provisioned product id %s' % (stack, match.group()))
            return self.delete_provisioned_product(match.group(), stack_id, region)
        else:
            cfn = self.clients.get('cloudformation', region)
            try:
                self.logger.debug("Deleting stack %s in %s" % (stack_id, region))
                cfn.delete_stack(StackName=stack_id)
                return {'status': "success", 'stackid': stack_id, 'region': region, 'detail': None}
            except Exception as e:
                self.logger.error("Failed to delete stack %s in %s" % (stack_id, region), exc_info=1)
                return {'status': "error", 'stackid': stack_id, 'region': region, 'detail': str(e)}

    def delete_stacks(self, stacks):
        """Deletes one or more AWS CloudFormation stacks.

        Args:
            stacks (list): a list containing dicts describing AWS CloudFormation stacks (region and stackid)

        Returns:
            dict: contains one or more of "success", "inprogress" or "error" keys, each containing a list of stackids
        """
        successes = []
        errors = []
        regions = []
        for s in stacks:
            if s['region'] not in regions:
                regions.append(s['region'])
        if len(regions) > 0:
            pool = ThreadPool(len(regions))
            results = pool.map(self._delete_stack, stacks)
            pool.close()
            pool.join()
            for r in results:
                if r['status'] == 'success':
                    successes.append(r)
                else:
                    errors.append(r)
        if len(errors) > 0:
            return {"success": successes, "inprogress": [], "error": errors}
        return self.check_statuses(successes)

    def _create_stack(self, region, artifact, testname, template_url, parameter_input,
                      role_arn, key_bucket, disable_rollback=True):
        """creates a CloudFormation stack.

        Args:
            region (str): region name
            artifact (str): artifact name
            testname (str): ci test name from config yaml file
            template_url (str): s3 url to template
            parameter_input (list): a list of parameter key value pairs
            role_arn (str): role to launch stack with
            key_bucket (str): bucket to store keypairs in
            disable_rollback (bool): [optional] specify whether to disable rollback on failure, defaults to True
        """

        self.logger.debug("creating stacks for artifact: %s, testname: %s, region: %s" % (
            artifact, testname, region))
        cfn = self.clients.get('cloudformation', region)
        stack_name = 'ci-' + testname + '-' + self._random_string(8)
        self._create_keypair(stack_name, key_bucket, region)
        self.logger.debug("parameter_input pre: %s" % parameter_input)
        rendered_params = self._render_param_variables(parameter_input, region, stack_name)
        self.logger.debug("parameter_input rendered_params: %s" % rendered_params)
        try:
            response = cfn.create_stack(
                StackName=stack_name,
                TemplateURL=template_url,
                Parameters=rendered_params,
                RoleARN=role_arn,
                DisableRollback=disable_rollback,
                Capabilities=[
                    'CAPABILITY_IAM',
                    'CAPABILITY_NAMED_IAM'
                ],
                Tags=[
                    {
                        'Key': 'cfn_cicd_artifact',
                        'Value': artifact
                    },
                    {
                        'Key': 'cfn_cicd_jobid',
                        'Value': self.job_id
                    },
                    {
                        'Key': 'cfn_cicd_executionid',
                        'Value': self.pipeline_execution_id
                    },
                    {
                        'Key': 'cfn_cicd_testname',
                        'Value': testname
                    },
                    {
                        'Key': 'cfn_cicd_pipeline',
                        'Value': self.pipeline_name
                    }
                ]
            )
            return {'status': 'success', 'stackid': response['StackId'], 'region': region,
                    'detail':  None, 'artifact': artifact, 'testname': testname}
            # return [None, response['StackId'], region]
        except Exception as e:
            self.logger.error("CreateStack Failed", exc_info=1)
            try:
                stackid = response['StackId']
            except Exception:
                stackid = None
            return {'status': 'error', 'stackid': stackid, 'region': region,
                    'detail':  str(e), 'artifact': artifact, 'testname': testname}

    def create_stacks(self):
        """Creates all AWS CloudFormation stacks defined by the ci config

        Returns:
            dict: contains one or more of "success" or "error" keys, each containing a list of stackids
        """

        errors = []
        successes = []
        for artifact in self.ci_configs.keys():
            for config in self.ci_configs[artifact]:
                for testname in config['tests']:
                    test = config['tests'][testname]
                    regions = self._build_regions(config, test)
                    template_url = self.upload_template(
                        artifact, test['template_file'], self.user_params['ScratchBucket'],
                        self.region
                    )
                    self.logger.debug("template_url: %s" % template_url)
                    try:
                        self.logger.debug("parameter_input: %s" % test['parameter_input'])
                        parameter_input = self._get_parameter_input(artifact, test['parameter_input'])

                        pool = ThreadPool(len(regions))
                        func = partial(
                            self._create_stack, artifact=artifact, testname=testname,
                            template_url=template_url, parameter_input=parameter_input,
                            role_arn=self.user_params['StackCreationRoleArn'],
                            key_bucket=self.user_params['KeyBucket']
                        )
                        results = pool.map(func, regions)
                        pool.close()
                        pool.join()
                        for result in results:
                            if result['status'] == 'error':
                                errors.append(result)
                            else:
                                successes.append(result)
                    except Exception:
                        self.logger.error("Stack creation failed for artifact %s testname %s" % (
                            artifact, testname), exc_info=1)
                        raise
        self.logger.debug("Created Stacks: %s" % str([errors, successes]))
        results = self.check_statuses(successes)
        results["error"] += errors
        return results

    def _provision_product(self, region, artifact, testname, template_url, parameter_input,
                           role_arn, key_bucket, disable_rollback=True):
        """publishes a service catalog product.

        Args:
            region (str): region name
            artifact (str): artifact name
            testname (str): ci test name from config yaml file
            template_url (str): s3 url to template
            parameter_input (list): a list of parameter key value pairs
            role_arn (str): role to launch stack with
            key_bucket (str): bucket to store keypairs in
            disable_rollback (bool): [optional] specify whether to disable rollback on failure, defaults to True
        """

        self.logger.debug("publishing products for artifact: %s, testname: %s, region: %s" % (
            artifact, testname, region))
        sc = self.clients.get('servicecatalog', region)
        cfn = self.clients.get('cloudformation', region)
        product_name = 'ci-' + testname + '-' + self._random_string(8)
        self._create_keypair(product_name, key_bucket, region)
        self.logger.debug("parameter_input pre: %s" % parameter_input)
        rendered_params = self._render_param_variables(parameter_input, region, product_name)
        for parm in rendered_params:
            parm['Value'] = parm.pop('ParameterValue')
            parm['Key'] = parm.pop('ParameterKey')
        self.logger.debug("parameter_input rendered_params: %s" % rendered_params)
        token = str(uuid.uuid4())
        try:
            response = sc.create_portfolio(DisplayName="PipelineTestPortfolio" + self._random_string(8),
                                           Description="An ephemeral test portfolio for the use of testing product\
                                                        publishing",
                                           IdempotencyToken=token, ProviderName="pipeline_ops")
            portfolio_id = response['PortfolioDetail']['Id']
            self.logger.debug("Portfolio %s created in %s" % (portfolio_id, region))
            response = sc.create_product(Name=product_name, Owner='Pipeline_Ops',
                                         ProductType='CLOUD_FORMATION_TEMPLATE',
                                         ProvisioningArtifactParameters={
                                                                        'Name': 'v1',
                                                                        'Description': 'test version 1',
                                                                        'Info': {
                                                                                'LoadTemplateFromURL': template_url
                                                                                },
                                                                        'Type': 'CLOUD_FORMATION_TEMPLATE'
                                                                        },
                                         IdempotencyToken=token
                                        )
            product_id = response['ProductViewDetail']['ProductViewSummary']['ProductId']
            self.logger.debug("Product %s created in %s" % (product_id, region))
            execution_role = os.environ['execution_role']
            provisioning_artifact_id = response['ProvisioningArtifactDetail']['Id']
            response = sc.associate_product_with_portfolio(PortfolioId=portfolio_id, ProductId=product_id)
            self.logger.debug("Product %s associated with portfolio %s" % (product_id, portfolio_id))
            response = sc.associate_principal_with_portfolio(PortfolioId=portfolio_id, PrincipalARN=execution_role,
                                                             PrincipalType='IAM')
            self.logger.debug("Principal %s associated with portfolio %s" % (execution_role, portfolio_id))
            launch_constraint_parameter = '{\"RoleArn\":\"' + role_arn + '\"}'
            response = sc.create_constraint(Description="Launch role constraint",
                                            IdempotencyToken=token,
                                            Parameters=launch_constraint_parameter,
                                            PortfolioId=portfolio_id,
                                            ProductId=product_id,
                                            Type="LAUNCH")
            constraint_id = response['ConstraintDetail']['ConstraintId']
            self.logger.debug("Constraint %s added to product %s in portfolio %s" % (constraint_id, product_id, portfolio_id))
            while True:
                try:
                    response = sc.provision_product(ProductId=product_id,
                                                    ProvisioningArtifactId=provisioning_artifact_id,
                                                    ProvisionedProductName=product_name,
                                                    ProvisioningParameters=rendered_params,
                                                    ProvisionToken=token,
                                                    Tags=[
                                                        {
                                                            'Key': 'cfn_cicd_artifact',
                                                            'Value': artifact
                                                        },
                                                        {
                                                            'Key': 'cfn_cicd_jobid',
                                                            'Value': self.job_id
                                                        },
                                                        {
                                                            'Key': 'cfn_cicd_executionid',
                                                            'Value': self.pipeline_execution_id
                                                        },
                                                        {
                                                            'Key': 'cfn_cicd_testname',
                                                            'Value': testname
                                                        },
                                                        {
                                                            'Key': 'cfn_cicd_pipeline',
                                                            'Value': self.pipeline_name
                                                        }
                                                    ]
                                                    )
                    provisioned_product_id = response['RecordDetail']['ProvisionedProductId']
                    self.logger.debug(response)
                    self.logger.debug("Product %s in the %s region, has been provisioned as %s from portfolio %s" % (product_id,
                                                                                                   region,
                                                                                                   provisioned_product_id,
                                                                                                   portfolio_id))
                    break
                except botocore.exceptions.ClientError as e:
                    if e.response['Error']['Code'] == 'ResourceNotFoundException':
                        self.logger.error('Product not ready yet. Retrying in 5 seconds...', exc_info=1)
                        time.sleep(5)
                    else:
                        self.logger.error(e)
                        raise
            # Following section is to use the provisoned product id to get the stack ID and return it to the pipeline
            filters = ['CREATE_IN_PROGRESS',
                       'CREATE_FAILED', 'CREATE_COMPLETE',
                       'ROLLBACK_IN_PROGRESS', 'ROLLBACK_FAILED',
                       'ROLLBACK_COMPLETE', 'DELETE_IN_PROGRESS',
                       'DELETE_FAILED', 'UPDATE_IN_PROGRESS',
                       'UPDATE_COMPLETE_CLEANUP_IN_PROGRESS',
                       'UPDATE_COMPLETE', 'UPDATE_ROLLBACK_IN_PROGRESS',
                       'UPDATE_ROLLBACK_FAILED',
                       'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS',
                       'UPDATE_ROLLBACK_COMPLETE', 'REVIEW_IN_PROGRESS']
            found = False
            response = sc.scan_provisioned_products(AccessLevelFilter={'Key': 'Account', 'Value': 'self'})
            while 'PageToken' in response:
                for item in response['ProvisionedProducts']:
                    if item['Id'] == provisioned_product_id:
                        self.logger.debug('Provisioned product status: ' + item['Status'])
                response = sc.scan_provisioned_products(AccessLevelFilter={'Key': 'Account', 'Value': 'self'},
                                                        PageSize=1,
                                                        PageToken=response['PageToken']
                                                        )
            for item in response['ProvisionedProducts']:
                if item['Id'] == provisioned_product_id:
                    self.logger.debug('Provisioned product status: ' + item['Status'])
            self.logger.debug('Starting search for: ' + provisioned_product_id)
            count = 0
            while found is False:
                count += 1
                if count == 5:
                    try:
                        response = sc.terminate_provisioned_product(ProvisionedProductId=provisioned_product_id, TerminateToken=str(uuid.uuid4()))
                        self.logger.debug("Stack not found, provisioned product %s terminated" % provisioned_product_id)
                    except Exception as e:
                        self.logger.error('Unable to terminate the failed provision product: ', exc_info=1)
                    raise Exception('Stack not found using provisioned product ID.')
                time.sleep(3)
                response_stack = cfn.list_stacks(StackStatusFilter=filters)
                stacks = []
                while 'NextToken' in response_stack:
                    for stack_summary in response_stack['StackSummaries']:
                        stacks.append(stack_summary['StackId'])
                    response_stack = cfn.list_stacks(NextToken=response_stack['NextToken'], StackStatusFilter=filters)
                for stack_summary in response_stack['StackSummaries']:
                    stacks.append(stack_summary['StackId'])
                for stack in stacks:
                    match = re.search(r'(pp-)\w+', stack)
                    if match is not None:
                        provisioned_stack_id = stack
                        found_provisioned_product_id = match.group()
                        if provisioned_product_id == found_provisioned_product_id:
                            found = True
                            self.logger.debug("Stack %s has been found using the provisioned product ID %s" % (provisioned_stack_id, provisioned_product_id))
                            break
            return {'status': 'success', 'stackid': provisioned_stack_id, 'region': region,
                    'detail':  None, 'artifact': artifact, 'testname': testname}
        except Exception as e:
            self.logger.error("Provisioning product failed", exc_info=1)
            self.logger.error(e)
            try:
                if portfolio_id in locals() and execution_role in locals():
                    response = sc.disassociate_principal_from_portfolio(PortfolioId=portfolio_id, PrincipalARN=execution_role)
                    self.logger.debug("Principal %s disassociated from portfolio %s" % (execution_role, portfolio_id))
                if constraint_id in locals and portfolio_id in locals():
                    response = sc.delete_constraint(Id=constraint_id)
                    self.logger.debug("Constraint %s deleted from portfolio %s" % (constraint_id, portfolio_id))
                if product_id in locals and portfolio_id in locals():
                    response = sc.disassociate_product_from_portfolio(ProductId=product_id, PortfolioId=portfolio_id)
                    self.logger.debug("Product %s disassociated from portfolio %s" % (product_id, portfolio_id))
                if product_id in locals:
                    response = sc.delete_product(Id=product_id)
                    self.logger.debug("Product %s deleted from %s" % (product_id, region))
                if portfolio_id in locals():
                    response = sc.delete_portfolio(Id=portfolio_id)
                    self.logger.debug("Portfolio %s deleted from %s" % (portfolio_id, region))
            except Exception:
                self.logger.error("Failed to cleanup all of the Service Catalog artifacts. This will have to be manually completed on portfolio: %" % (portfolio_id))
            return {'status': 'error', 'stackid': provisioned_product_id, 'region': region,
                    'detail':  str(e), 'artifact': artifact, 'testname': testname}

    def provision_product(self):
        """Creates all AWS Service Catalog provisioned products defined by the ci config

        Returns:
            dict: contains one or more of "success" or "error" keys, each containing a list of stackids
        """

        errors = []
        successes = []
        for artifact in self.ci_configs.keys():
            for config in self.ci_configs[artifact]:
                for testname in config['tests']:
                    test = config['tests'][testname]
                    regions = self._build_regions(config, test)
                    template_url = self.upload_template(
                        artifact, test['template_file'], self.user_params['ScratchBucket'],
                        self.region
                    )
                    self.logger.debug("template_url: %s" % template_url)
                    try:
                        self.logger.debug("parameter_input: %s" % test['parameter_input'])
                        parameter_input = self._get_parameter_input(artifact, test['parameter_input'])

                        pool = ThreadPool(len(regions))
                        func = partial(
                            self._provision_product, artifact=artifact, testname=testname,
                            template_url=template_url, parameter_input=parameter_input,
                            role_arn=self.user_params['StackCreationRoleArn'],
                            key_bucket=self.user_params['KeyBucket']
                        )
                        results = pool.map(func, regions)
                        pool.close()
                        pool.join()
                        for result in results:
                            if result['status'] == 'error':
                                errors.append(result)
                            else:
                                successes.append(result)
                    except Exception:
                        self.logger.error("Product publishing failed for artifact %s testname %s" % (
                            artifact, testname), exc_info=1)
                        raise
        self.logger.debug("Created Stacks: %s" % str([errors, successes]))
        results = self.check_statuses(successes)
        results["error"] += errors
        return results

    def upload_template(self, artifact, template_name, bucket, region):
        """Uploads a template to S3

        Args:
            artifact (str): artifact name
            template_name (str): template filename
            bucket (str): S3 bucket name
            region (str): S3 bucket region

        Returns:
            str: url for s3 object
        """

        fname = '/tmp/artifacts/%s/%s/templates/%s' % (self.pipeline_name, artifact, template_name)
        key = 'scratch/%s/%s-%s/%s' % (
            artifact,
            datetime.now().strftime('%y%m%d-%H%M%S-%f'),
            self.job_id,
            template_name
        )
        s3_client = self.clients.get('s3')
        s3_client.upload_file(fname, bucket, key)
        endpoint = 's3-%s.amazonaws.com' % region
        if region == 'us-east-1':
            endpoint = 's3.amazonaws.com'
        url = 'https://%s/%s/%s' % (endpoint, bucket, key)
        return url

    def _get_parameter_input(self, artifact, filename):
        """parses CloudFormation input parameter file

        Args:
            artifact (str): artifact name
            filename (str): parameter filename
        """

        fname = '/tmp/artifacts/%s/%s/templates/%s' % (self.pipeline_name, artifact, filename)
        if not os.path.isfile(fname):
            fname = '/tmp/artifacts/%s/%s/ci/%s' % (self.pipeline_name, artifact, filename)
        with open(fname) as json_data:
            params = json.load(json_data)
        return params

    def _render_param_variables(self, params, region, stack_name, replace_cikey=True):
        """processes variables defined in cloudfomration parameter Values

        Will render specific ParameterValue values:
        $[alfred_genaz_x] - generates a list of az's of x length in the specified region
        $[alfred_genpass_x] - generates a password of x characters length
        $[alfred_getkeypair] - generates an ec2 keypair
        $[alfred_genuuid] - generate a uuid
        cikey - same as $[alfred_getkeypair], the default keyname specified by AWS QuickStart ci config files.

        Args:
            params (list): list of CloudFormation input parameter key/value pairs
            region (str): region name
            stack_name (str): used as name for keypair
            replace_cikey (bool): [optional] whether to replace the cikey value used by AWS QuickStart, defaults to True
        """

        self.logger.debug("render_param_variables got region as %s" % region)
        self.logger.debug("params: %s:" % params)
        rendered_params = []
        for p in params:
            newval = {'ParameterKey': p['ParameterKey'], 'ParameterValue': p['ParameterValue']}
            if '$[' in p['ParameterValue']:
                if p['ParameterValue'].startswith('$[alfred_genaz_') or p['ParameterValue'].startswith('$[alfred_getaz_'):
                    az_count = int(p['ParameterValue'].split('_')[2].replace(']', ''))
                    newval['ParameterValue'] = ','.join(self._get_azs(region, az_count))
                    self.logger.debug("render_param_variables got azs as %s" % p['ParameterValue'])
                elif p['ParameterValue'].startswith('$[alfred_genpass_'):
                    pw_length = int(p['ParameterValue'].split('_')[2].replace(']', ''))
                    newval['ParameterValue'] = self._random_string(pw_length, False)
                elif p['ParameterValue'] == '$[alfred_getkeypair]':
                    newval['ParameterValue'] = stack_name
                elif '$[alfred_genuuid]' in p['ParameterValue'] or '$[alfred_genguid]' in p['ParameterValue']:
                    newval['ParameterValue'] = p['ParameterValue'].replace('$[alfred_genguid]', str(uuid.uuid4())).replace('$[alfred_genuuid]',str(uuid.uuid4()))
                else:
                    raise NameError('found unsupported variable %s in parameter file' % p['ParameterValue'])
            elif p['ParameterValue'] == 'cikey' and replace_cikey:
                newval['ParameterValue'] = stack_name
            rendered_params.append(newval)
        self.logger.debug("rendered_params: %s:" % rendered_params)
        return rendered_params

    def _random_string(self, length, alphanum=True):
        """Generates a random string, by default only including letters and numbers

        Args:
            length (int): length of string to generate
            alphanum (bool): [optional] if False it will also include ';:=+!@#%^&*()[]{}' in the character set
        """

        additional = ''
        if not alphanum:
            additional = ';:=+!@#%^&*()[]{}'
        chars = string.ascii_uppercase + string.ascii_lowercase + string.digits + additional
        return ''.join(random.SystemRandom().choice(chars) for _ in range(length))

    def _create_keypair(self, name, bucket, region):
        """Creates a ec2 keypair and uploads the private key to S3

        Args:
            name (str): name for keypair
            bucket (str): bucket name
            region (str): region to create keypair in
        """

        ec2_client = self.clients.get('ec2', region)
        key = ec2_client.create_key_pair(KeyName=name)['KeyMaterial']
        s3_client = self.clients.get('s3')
        s3_client.put_object(Bucket=bucket, Key="keys/%s/%s" % (region, name), Body=StringIO(key).read())

    def _get_regions(self):
        """Gets a list of AWS region names"""

        ec2_client = self.clients.get('ec2')
        return [r['RegionName'] for r in ec2_client.describe_regions()['Regions']]

    def _build_regions(self, config, test):
        """returns a list of regions by evaluating ci config for region constraints

        Args:
            config: ci config dict
            test: ci test dict
        """

        if 'regions' in test.keys():
            regions = test['regions']
        elif 'regions' in config['global']:
            regions = config['global']['regions']
        else:
            regions = self._get_regions()
        regions = list(set(regions))
        if 'exclude-regions' in test.keys():
            for excl in test['exclude-regions']:
                try:
                    regions.remove(excl)
                except ValueError:
                    pass
        elif 'exclude-regions' in config['global']:
            for excl in config['global']['exclude-regions']:
                try:
                    regions.remove(excl)
                except ValueError:
                    pass
        return regions

    def _get_azs(self, region, qty):
        """gets a predefined quantity of (random) az's from a specified region

        Args:
            region (str): region name
            qty: quantity of az's to return

        Returns:
            list: availability zone names
        """
        self.logger.debug("_get_azs input: region %s qty %s" % (region, qty))
        ec2 = self.clients.get('ec2', region)
        response = ec2.describe_availability_zones(Filters=[{'Name': 'state', 'Values': ['available']}])
        az_list = [r['ZoneName'] for r in response['AvailabilityZones']]
        self.logger.debug("_get_azs output: %s" % az_list)
        return random.sample(az_list, qty)

    def handle_deletes(self, deleted_stacks, stacks=None, suffix='pre'):
        """Checks whether stack deletes are still in progress, or failed and responds to AWS CodePipeline if needed

        Args:
            deleted_stacks (list): list of lists of stack states
            stacks (list): list of completed stacks to pass through to continuationToken
            suffix (str): either 'pre' or 'post', used to define where the continuation invocation starts off

        Returns:
            bool: returns True if there are any failed or inprogress stacks
        """
        self.logger.debug("deleted_stacks: %s" % deleted_stacks)
        if len(deleted_stacks['inprogress']) > 0:
            msg = "DeleteStack in progress..."
            data = {
                "status": msg,
                'configs': self.ci_configs,
                'deleting': deleted_stacks['inprogress'],
                '%s-delete' % suffix: True
            }
            if stacks:
                data['stacks'] = stacks
            self.continue_job_later(data)
            return True
        elif len(deleted_stacks['error']) > 0:
            msg = "%s DeleteStack failures: %s" % (len(deleted_stacks['error']), deleted_stacks['error'])
            self.put_job_failure(msg)
            return True
        return False

    def upload_output_artifact(self, successes):
        """Uploads a json file containing stackids to S3

        Args:
            successes (list): a list of stackid's
        """

        data = {"Stacks": successes, "Configs": self.ci_configs, "JobId": self.original_job_id}
        bucket = self.output_artifacts[0]['location']['s3Location']['bucketName']
        s3key = self.output_artifacts[0]['location']['s3Location']['objectKey']
        artifact_file = '/tmp/output_artifacts/%s_files/artifact.json' % s3key
        zipped_artifact_file = '/tmp/output_artifacts/%s' % s3key
        try:
            shutil.rmtree('/tmp/output_artifacts/%s_files/' % s3key)
        except Exception:
            pass
        try:
            os.remove(zipped_artifact_file)
        except Exception:
            pass
        os.makedirs('/tmp/output_artifacts/%s_files/' % s3key)
        with open(artifact_file, 'w') as outfile:
            json.dump(data, outfile)
        with ZipFile(zipped_artifact_file, 'w') as zipped_artifact:
            zipped_artifact.write(artifact_file, os.path.basename(artifact_file))
        s3_client = self.clients.get(
            's3',
            region=None,
            access_key=self.job_data['artifactCredentials']['accessKeyId'],
            secret_key=self.job_data['artifactCredentials']['secretAccessKey'],
            session_token=self.job_data['artifactCredentials']['sessionToken'],
            s3v4=True
        )
        s3_client.upload_file(zipped_artifact_file, bucket, s3key,
                              ExtraArgs={"ServerSideEncryption": "aws:kms"})

    def _test_stacks_resource(self, arg, test_func):
        """executes a user defined test function against a particular AWS resource

        Args:
            arg (dict): contains stackid, region, logical_resource_id and physical_resource_id
            test_func (func): function to execute
        """
        region = arg['region']
        stackid = arg['stackid']
        logical_resource_id = arg['logical_resource_id']
        physical_resource_id = arg['physical_resource_id']
        return test_func(
            region=region,
            stackid=stackid,
            logical_resource_id=logical_resource_id,
            physical_resource_id=physical_resource_id
        )

    def _test_stacks_stackid(self, stackid, region, artifact, config, test, test_func,
                             logical_resource_ids, resource_types, logical_resource_id_prefix):
        """threads user defined tests for a stack per matched resource.

        Args:
            stackid (str): cfn StackId
            region (str): region name
            artifact (str): artifact name
            config (str): config name
            test (str): test name
            test_func (function): function that performs the test
            logical_resource_ids (list): [optional] list of logical id's that the test should run against
            resource_types (list): [optional] list of resource types that the test should run against
            logical_resource_id_prefix (str): [optional] prefix filter for logical resource id's
        """

        try:
            testresources = []
            if not logical_resource_ids and not resource_types:
                return [test_func(region=region, stackid=stackid)]
            elif logical_resource_ids:
                for lid in logical_resource_ids:
                    testresources.append({"region": region, "stackid": stackid, "logical_resource_id": lid,
                                          "physical_resource_id": None})
            elif resource_types:
                resources = self.get_stack_resources(stackid, region)
                self.logger.debug({"test_stacks:resources": resources})
                testresources = []
                for resource in resources:
                    self.logger.debug({"test_stacks:resourceType": resource['ResourceType']})
                    if resource['ResourceType'] in resource_types:
                        matched = False
                        if logical_resource_id_prefix:
                            if resource['LogicalResourceId'].startswith(logical_resource_id_prefix):
                                matched = True
                        else:
                            matched = True
                        if matched:
                            testresources.append({"region": region, "stackid": stackid,
                                                  "logical_resource_id": resource['LogicalResourceId'],
                                                  "physical_resource_id": resource['PhysicalResourceId']})
                            self.logger.debug({"test_stacks": "Matched a resource, running test"})
            if len(testresources) == 0:
                self.logger.warning(
                    "No tests performed on %s in %s - no resources in stack matched test criteria"
                    % (stackid, region)
                )
                return None
            pool = ThreadPool(len(testresources))
            func = partial(self._test_stacks_resource, test_func=test_func)
            outputs = pool.map(func, testresources)
            pool.close()
            pool.join()
            return outputs
        except Exception:
            self.logger.error({"_test_stacks_stackid": "unhandled exception"}, exc_info=1)
            raise

    def _test_stacks_region(self, region, artifact, config, test, test_func, logical_resource_ids,
                            resource_types, logical_resource_id_prefix):
        """threads user defined tests per region.

        Args:
            region (str): region name
            artifact (str): artifact name
            config (str): config name
            test (str): test name
            test_func (function): function that performs the test
            logical_resource_ids (list): [optional] list of logical id's that the test should run against
            resource_types (list): [optional] list of resource types that the test should run against
            logical_resource_id_prefix (str): [optional] prefix filter for logical resource id's
        """
        try:
            pool = ThreadPool(len(config['tests'][test]["built_stacks"][region]))
            func = partial(self._test_stacks_stackid, region=region, artifact=artifact, config=config, test=test,
                           resource_types=resource_types, logical_resource_id_prefix=logical_resource_id_prefix,
                           test_func=test_func, logical_resource_ids=logical_resource_ids)
            results = pool.map(func, config['tests'][test]["built_stacks"][region])
            pool.close()
            pool.join()
            return [o for o in results if o is not None]
        except Exception:
            self.logger.error({"_test_stacks_region": "unhandled exception"}, exc_info=1)
            raise

    def test_stacks(self, test_func, logical_resource_ids=None, resource_types=None,
                    logical_resource_id_prefix=None):
        """Helper function to parallelize running a test function against stacks.

        The test_func argument is passed the function to be executed as input, which needs to take at least region and stackid as arguments
        optionally logical_resource_id and physical_resource_id can also be accepted if the test is designed to run against a particular resource.
        Arguments are positional and must be in the order above, for example:

        def my_test_function(region, stackid, logical_resource_id, physical_resource_id):
            ...

        test_stacks(my_test_function)

        Args:
            test_func (function): function that performs the test
            logical_resource_ids (list): [optional] list of logical id's that the test should run against
            resource_types (list): [optional] list of resource types that the test should run against
            logical_resource_id_prefix (str): [optional] prefix filter for logical resource id's

        Returns:
            dict: contains one or more of "success" or "error" keys, each containing a list of test results
        """
        self.logger.debug({"test_stacks": "starting..."})
        results = {"success": [], "error": []}
        for artifact in self.ci_configs.keys():
            self.logger.debug({"test_stacks:artifact": self.ci_configs[artifact]})
            for config in self.ci_configs[artifact]:
                self.logger.debug({"test_stacks:config": config})
                for test in config['tests'].keys():
                    self.logger.debug({"test_stacks:test": config['tests'][test]})
                    pool = ThreadPool(len(config['tests'][test]["built_stacks"].keys()))
                    func = partial(self._test_stacks_region, artifact=artifact, config=config, test=test,
                                   test_func=test_func, logical_resource_ids=logical_resource_ids,
                                   resource_types=resource_types,
                                   logical_resource_id_prefix=logical_resource_id_prefix)
                    outputs = pool.map(func, config['tests'][test]["built_stacks"].keys())
                    pool.close()
                    pool.join()
                    for outputlist in outputs:
                        for innerlist in outputlist:
                            for output in innerlist:
                                self.logger.debug({"test_stacks:output": output})
                                result = {"stackid": output["stackid"], "region": output["region"],
                                          "testname": test, "artifact": artifact}
                                try:
                                    result["logical_resource_id"] = output["logical_resource_id"]
                                    result["physical_resource_id"] = output["physical_resource_id"]
                                except Exception:
                                    pass
                                if output["success"]:
                                    results["success"].append(result)
                                else:
                                    if 'error_msg' in output.keys():
                                        result["error_msg"] = output['error_msg']
                                    results["error"].append(result)
        return results

    def get_stack_resources(self, stackid, region=None):
        """Fetches resource details from a given AWS CloudFormation stack

        Args:
            stackid (str): cloudfomration stack id(arn) can also be a stack name for stacks that are not in DELETE_COMPLETE state
            region (str): [conditional] only required if stack name (not full arn) is provided for the stackid

        Returns:
            list: stack resources
        """

        resources = []
        if not region:
            region = stackid.split(':')[3]
        cfn_client = self.clients.get("cloudformation", region=region)
        response = cfn_client.list_stack_resources(StackName=stackid)
        resources += response['StackResourceSummaries']
        while 'NextToken' in response:
            response = cfn_client.list_stack_resources(StackName=stackid, NextToken=response['NextToken'])
            resources += response['StackResourceSummaries']
        self.logger.debug({"get_stack_resources:resources": resources})
        return resources

    def deploy_to_s3(self):
        """Deploys input artifact to S3

        S3 key is defined as s3://DeployBucket/DeployKey/artifact_revision_id.

        DeployKey and DeployBucket are defined in the pipeline User Parameters for the action.

        artifact_revision_id is the commit id for the artifact.

        In addition to the above the artifact is also deployed to s3://DeployBucket/DeployKey/latest/ so that the latest approved revision can be easily tracked.
        """

        s3_client = self.clients.get('s3')
        bucket = self.user_params['DeployBucket']
        key = self.user_params['DeployKey']
        local_directory = '/tmp/artifacts/%s/%s' % (self.pipeline_name, self.artifacts[0]['name'])
        for prefix in ["%s/latest" % key, "%s/%s" % (key, self.artifact_revision_id)]:
            response = s3_client.list_objects(Bucket=bucket, Prefix=prefix)
            self.logger.debug(response)
            if 'Contents' in response.keys():
                s3_client.delete_objects(
                    Bucket=bucket,
                    Delete={'Objects': [{"Key": dkey['Key']} for dkey in response['Contents']]}
                )
            while 'NextMarker' in response:
                response = s3_client.list_objects(Bucket=bucket, Prefix=prefix, Marker=response['NextMarker'])
                if 'Contents' in response.keys():
                    s3_client.delete_objects(
                        Bucket=bucket,
                        Delete={'Objects': [{"Key": dkey['Key']} for dkey in response['Contents']]}
                    )
            for root, dirs, files in os.walk(local_directory):
                for filename in files:
                    local_path = os.path.join(root, filename)
                    relative_path = os.path.relpath(local_path, local_directory)
                    s3_path = os.path.join(prefix, relative_path)
                    args = {'Metadata': {'git_revision_id': self.artifact_revision_id}}
                    s3_client.upload_file(local_path, bucket, s3_path, ExtraArgs=args)

    def get_templates(self):
        """Fetches templates defined in ci_config tests from artifacts and converts them to python dict.

        Returns:
            dict: template filename for keys, template converted to a python dict for values
        """

        templates = {}
        for config in self.ci_configs.keys():
            for config_file in self.ci_configs[config]:
                for test in config_file['tests'].keys():
                    fname = config_file['tests'][test]['template_file']
                    if fname not in templates.keys():
                        a_path = '/tmp/artifacts/%s/%s/templates/%s' % (
                            self.pipeline_name,
                            config,
                            config_file['tests'][test]['template_file'])
                        with open(a_path, 'r') as f:
                            templates[fname] = f.read()
                        try:
                            templates[fname] = json.loads(templates[fname])
                        except ValueError as e:
                            if e.args[0] == 'No JSON object could be decoded':
                                templates[fname] = yaml.load(templates[fname])
                                if 'Resources' not in templates[fname].keys():
                                    raise ValueError("Could not decode template from json or yaml")
                            else:
                                raise
        return templates

    def find_in_obj(self, obj, val, matching_func, matches, path="", case_sensitive=True):
        """Finds values in a nested dict (AWS CloudFormation template).

        Args:
            obj (dict): cfn template
            val (str or int): a value to search for
            matching_func (func): a function that takes 2 variables and returns True if they are deemed to be a match
            matches (list): an externally defined list to place matching values into
            path (str): base path, used for recursion, defaults to "" do not change
            case_sensitive (bool): if False both the obj and val will be made lower case. Default: True

        Returns:
            nothing - output is placed into the matches input list
        """

        if isinstance(val, type("")):
            val = unicode(val)
        if isinstance(obj, type("")):
            obj = unicode(obj)

        if not case_sensitive and isinstance(obj, unicode) and isinstance(val, unicode):
            obj = obj.lower()
            val = val.lower()

        if isinstance(obj, type(val)):
            if matching_func(obj, val):
                matches.append({"value": obj, "path": path, "regions": self._get_ec2_regions(path)})
        elif isinstance(obj, dict):
            for o in obj.keys():
                self.find_in_obj(obj[o], val, matching_func, matches, "%s[%s]" % (path, o), case_sensitive)
        elif isinstance(obj, list):
            index = 0
            for o in obj:
                self.find_in_obj(o, val, matching_func, matches, "%s[%s]" % (path, index), case_sensitive)
                index += 1

    def _get_ec2_regions(self, path):
        """extracts ec2 region names from a string.

        Args:
            path (str): a string that may contain aws region names

        Returns:
            list: valid region names
        """
        ec2_client = self.clients.get('ec2')
        valid_regions = [r['RegionName'] for r in ec2_client.describe_regions()['Regions']]
        regions = []
        for r in set(re.findall('[a-zA-Z]*-[a-zA-Z]*-[0-9]', path)):
            if r in valid_regions:
                regions.append(r)
        return regions

    def _parse_logs(self, logs):
        """json decodes cloudtrail logs

        Args:
            logs (list): a list of json cloudtrail log entries

        Returns:
            list: decoded log entries
        """
        parsed = []
        for l in logs:
            parsed.append(json.loads(l['message']))
        return parsed

    def build_execution_report(
            self, pipeline_id=None, region=None,
            sns_topic=None, s3_bucket=None, s3_prefix='',
            s3_region=None, execution_id=None):
        """Builds a text report for a pipeline execution, if arguments are omitted it will fetch them from the class

        Args:
            pipeline_id (str): pipeline id to use. default: self.pipeline_id
            region (str): region where pipeline resides. default: self.region
            sns_topic (str): optional arn for sns topic to send report to. default: None
            s3_bucket: (str): optional bucket name to place report. default: None
            s3_prefix: (str): optional s3 prefix to place report. default: ''
            s3_region: (str): optional s3 bucket region. default: self.region
            execution_id: (str): optional pipeline execution id to base report on

        Returns:
            string: text formatted report of pipeline execution
        """

        cp_client = self.clients.get('codepipeline', region)
        response = cp_client.get_pipeline_state(name=pipeline_id)

        if not pipeline_id:
            pipeline_id = self.pipeline_name
        if not region:
            region = self.region
        if not s3_region:
            s3_region = self.region
        if sns_topic:
            sns_region = sns_topic.split(':')[3]
        if len(s3_prefix) > 0 and not s3_prefix.endswith('/'):
            s3_prefix += '/'
        if not execution_id and self.pipeline_execution_id:
            execution_id = self.pipeline_execution_id
        elif not execution_id:
            execution_id = response['stageStates'][0]['latestExecution']['pipelineExecutionId']

        lambdas = []
        for stage in cp_client.get_pipeline(name=pipeline_id)['pipeline']['stages']:
            for action in stage['actions']:
                if action['actionTypeId']['category'] == 'Invoke':
                    lambdas.append(action["configuration"]["FunctionName"])
                if action['actionTypeId']['category'] == 'Source':
                    repo = action['configuration']['RepositoryName']

        logs_client = self.clients.get('logs', region)
        logs = []
        pattern = '{ ($.data.pipeline_execution_id = "%s") && ($.log_level != "DEBUG") }'
        for l in lambdas:
            self.logger.debug("logGroupName: /aws/lambda/%s" % l)
            try:
                response = logs_client.filter_log_events(
                    logGroupName='/aws/lambda/%s' % l,
                    filterPattern=pattern % execution_id
                )
                logs += self._parse_logs(response['events'])
                while 'nextToken' in response:
                    response = logs_client.filter_log_events(
                        logGroupName='/aws/lambda/%s' % l,
                        filterPattern=pattern % execution_id
                    )
                    logs += self._parse_logs(response['events'])
            except Exception as e:
                if str(e) == "An error occurred (ResourceNotFoundException) when calling the FilterLogEvents operation: The specified log group does not exist.":
                    self.logger.debug("no logs found for %s" % l)
                else:
                    raise
        structured_report = {}
        warnings = []
        errors = []
        for log in logs:
            artifact_revision_id = log["data"]["artifact_revision_id"]
            stage_name = log["data"]["stage_name"]
            pipeline_action = log["data"]["pipeline_action"]
            if artifact_revision_id not in structured_report.keys():
                structured_report[artifact_revision_id] = {}
            if stage_name not in structured_report[artifact_revision_id].keys():
                structured_report[artifact_revision_id][stage_name] = {}
            if pipeline_action not in structured_report[artifact_revision_id][stage_name].keys():
                structured_report[artifact_revision_id][stage_name][pipeline_action] = []
            try:
                message = json.dumps(log["data"]["message"])
            except Exception:
                message = log["data"]["message"]
            event = {'log_level': log['log_level'],
                     'time_stamp': log["time_stamp"],
                     "message": message}
            structured_report[artifact_revision_id][stage_name][pipeline_action].append(event)
            if log['log_level'] == 'WARNING':
                warnings.append(log)
            elif log['log_level'] == 'ERROR':
                errors.append(log)

        commit_url = "https://%s.console.aws.amazon.com/codecommit/home#/repository/%s/commit/%s"
        output = "Report for %s execution %s\n\n" % (pipeline_id, execution_id)

        if len(errors) > 0:
            output += "Errors:\n"
            for error in errors:
                output += "    %s    %s    %s    %s\n" % (
                    error['time_stamp'],
                    error['data']["stage_name"],
                    error['data']['pipeline_action'],
                    error['data']['message'])
            output += "\n"
        if len(warnings) > 0:
            output += "Warnings:\n"
            for warning in warnings:
                output += "    %s    %s    %s    %s\n" % (
                    warning['time_stamp'],
                    warning['data']["stage_name"],
                    warning['data']['pipeline_action'],
                    warning['data']['message'])
            output += "\n"
        output += "Events:\n"
        for commit in structured_report.keys():
            output += "    source commit level: %s\n" % (commit_url % (region, repo, commit))
            for stage in structured_report[commit].keys():
                output += "        stage: %s\n" % stage
                for action in structured_report[commit][stage].keys():
                    output += "            action: %s\n" % action
                    for event in structured_report[commit][stage][action]:
                        output += "                [%s] %s - %s\n" % (
                            event['log_level'],
                            event['time_stamp'],
                            event['message'])
                        report_time = event['time_stamp']
        if sns_topic:
            sns_client = self.clients.get('sns', sns_region)
            subject = "Pipeline Report - %s" % (pipeline_id)
            sns_client.publish(TopicArn=sns_topic, Subject=subject[:100], Message=output)
        if s3_bucket:
            s3_client = self.clients.get('s3', s3_region)
            handle = StringIO(output)
            report_time = datetime.strptime(report_time, '%Y-%m-%d %H:%M:%S,%f').strftime('%Y-%m-%dT%H:%M')
            s3_key = "%s%s/%s-%s.txt" % (s3_prefix, pipeline_id, report_time, structured_report.keys()[0])
            s3_client.put_object(Bucket=s3_bucket, Key=s3_key, Body=handle.read())
        return output
