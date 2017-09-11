from awsclients import AwsClients
import botocore
from cfnpipeline import CFNPipeline
from cStringIO import StringIO
from datetime import datetime
import json
from logger import Logger
import random
import string
from time import sleep
from zipfile import ZIP_DEFLATED
from zipfile import ZipFile
from zipfile import ZipInfo


loglevel = 'debug'
logger = Logger(loglevel=loglevel)
logger.info('New Lambda container initialised, logging configured.')
clients = AwsClients(logger)
pipeline_run = CFNPipeline(logger, clients)


def random_string(length, alphanum=True):
    additional = ''
    if not alphanum:
        additional = ';:=+!@#%%^&*()[]{}'
    chars = string.ascii_uppercase + string.ascii_lowercase + string.digits + additional
    return ''.join(random.SystemRandom().choice(chars) for _ in range(length))


function_code = """import socket
import sys

def tcp_connect(address, port):
    s = socket.socket()
    s.settimeout(4)
    print("Attempting to connect to %s on port %s" % (address, port))
    s.connect((address, port))
    print("Connection to %s on port %s succeeded" % (address, port))
    return {"success": True}

def lambda_handler(event, context):
    print(event)
    address = event['address']
    port = int(event['port'])
    try:
        return tcp_connect(address, port)
    except Exception as e:
        print("%s:%s %s" % (address, port, str(e)))
        raise
"""

assume_role_policy = """\
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}\
"""

iam_policy = """\
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "VpcRequirements",
      "Effect": "Allow",
      "Action": [
        "ec2:CreateNetworkInterface",
        "ec2:DeleteNetworkInterface",
        "ec2:DescribeNetworkInterfaces",
        "ec2:DetachNetworkInterface"
      ],
      "Resource": [
        "*"
      ]
    },
    {
      "Sid": "LogRequirements",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": [
        "*"
      ]
    }
  ]
}\
"""

iam_role_arn = None
iam_policy_arn = None


def get_iam_role():
    global iam_role_arn
    recreate = False
    iam_client = clients.get("iam")
    if not iam_role_arn:
        recreate = True
        iam_name = 'test_subnet_%s' % random_string(8)
    else:
        try:
            iam_name = iam_role_arn.split('/')[-1]
            iam_client.get_role(RoleName=iam_name)
        except Exception as e:
            logger.debug({"get_iam_role:get_role": str(e)})
            recreate = True
    if recreate:
        iam_role_arn = iam_client.create_role(
            RoleName=iam_name,
            AssumeRolePolicyDocument=assume_role_policy
        )['Role']['Arn']
        logger.debug({"get_iam_role:iam_role": iam_role_arn})
        iam_client.put_role_policy(RoleName=iam_name, PolicyName=iam_name,
                                   PolicyDocument=iam_policy)
    return iam_role_arn


def delete_iam_role():
    global iam_role_arn
    if iam_role_arn:
        iam_client = clients.get("iam")
        iam_name = iam_role_arn.split('/')[-1]
        iam_client.delete_role_policy(RoleName=iam_name, PolicyName=iam_name)
        iam_client.delete_role(RoleName=iam_name)
        iam_role_arn = None
    return


def test_subnet_connectivity(region, stackid, logical_resource_id, physical_resource_id,
                             endpoints=[['www.amazon.com', "80"]]):
    logger.debug({"test_subnet_connectivity": "starting"})
    error_msg = []
    if region not in clients.get_available_regions('lambda'):
        msg = "Test for %s %s skipped, %s not supprted by lambda" % (stackid, logical_resource_id, region)
        logger.warning(msg)
        return {"success": True,
                "logical_resource_id": logical_resource_id,
                "physical_resource_id": physical_resource_id,
                "warning": "Test skipped, region %s not supprted by lambda" % region,
                "region": region,
                "stackid": stackid}
    try:
        function_name = 'test_subnet_%s_%s' % (physical_resource_id, random_string(8))
        iam_name = function_name.replace('_', '-')
        lambda_client = clients.get("lambda", region=region)
        ec2_client = clients.get("ec2", region=region)
        iam_role_arn = get_iam_role()
        response = ec2_client.describe_subnets(SubnetIds=[physical_resource_id])
        logger.debug({"test_subnet_connectivity:describe_subnets": response})
        vpc_id = response['Subnets'][0]['VpcId']
        logger.debug({"test_subnet_connectivity:vpc_id": vpc_id})
        security_group_id = ec2_client.create_security_group(
            GroupName=iam_name,
            Description=iam_name,
            VpcId=vpc_id
        )['GroupId']
        logger.debug({"test_subnet_connectivity:security_group_id": security_group_id})
        now = datetime.now()
        zi_timestamp = (now.year, now.month, now.day, now.hour, now.minute, now.second)
        zinfo = ZipInfo('lambda_function.py', zi_timestamp)
        zinfo.external_attr = 0x0744 << 16
        f = StringIO()
        z = ZipFile(f, 'w', ZIP_DEFLATED)
        z.writestr(zinfo, function_code)
        z.close()
        zip_bytes = f.getvalue()
        logger.debug({"test_subnet_connectivity:create_function_input": {"FunctionName": function_name,
                      "Role": iam_role_arn, "Code": {'ZipFile': zip_bytes},
                      "VpcConfig": {'SubnetIds': [physical_resource_id],
                                    'SecurityGroupIds': [security_group_id]}
        }})
        lambda_function = False
        retries = 0
        max_retries = 4
        while not lambda_function:
            try:
                lambda_function = lambda_client.create_function(
                    FunctionName=function_name,
                    Runtime='python2.7',
                    Role=iam_role_arn,
                    Handler='lambda_function.lambda_handler',
                    Code={'ZipFile': zip_bytes},
                    Timeout=120,
                    MemorySize=128,
                    VpcConfig={
                        'SubnetIds': [physical_resource_id],
                        'SecurityGroupIds': [security_group_id]
                    }
                )
            except botocore.exceptions.ClientError as e:
                codes = ['InvalidParameterValueException', 'AccessDeniedException']
                logger.debug("boto exception: ", exc_info=1)
                logger.debug(e.response)
                if "The provided subnets contain availability zone Lambda doesn't support." in e.response['Error']['Message']:
                    raise
                if e.response['Error']['Code'] in codes and retries < max_retries:
                    logger.debug({"test_subnet_connectivity:create_function": str(e)}, exc_info=1)
                    msg = "role not propagated yet, sleeping a bit and then retrying"
                    logger.debug({"test_subnet_connectivity:create_function_retry": msg})
                    retries += 1
                    sleep(10*(retries**2))
                else:
                    raise
        for endpoint in endpoints:
            f = StringIO()
            f.write(json.dumps({"address": endpoint[0], "port": endpoint[1]}))
            payload = f.getvalue()
            f.close()
            response = lambda_client.invoke(FunctionName=function_name, InvocationType='RequestResponse',
                                            Payload=payload)
            response['Payload'] = response['Payload'].read()
            try:
                response['Payload'] = json.loads(response['Payload'])
            except Exception:
                pass
            logger.debug({"test_subnet_connectivity:response": response})

            if response['StatusCode'] != 200 or 'FunctionError' in response.keys():
                results = {"success": False,
                           "logical_resource_id": logical_resource_id,
                           "physical_resource_id": physical_resource_id,
                           "region": region,
                           "stackid": stackid}
                error_msg.append({"endpoint": endpoint, "response": response['Payload']})
            elif response['StatusCode'] == 200 and len(error_msg) == 0:
                results = {"success": True,
                           "logical_resource_id": logical_resource_id,
                           "physical_resource_id": physical_resource_id,
                           "region": region,
                           "stackid": stackid}
    except Exception as e:
        logger.error({"test_subnet_connectivity": str(e)}, exc_info=1)
        if "subnets contain availability zone Lambda doesn't support" in str(e):
            results = {"success": True,
                           "logical_resource_id": logical_resource_id,
                           "physical_resource_id": physical_resource_id,
                           "region": region,
                           "stackid": stackid}
            logger.warning("test skipped as lambda is not supported in the subnet's az. %s" % str(results))
        else:
            results = {"success": False,
                       "logical_resource_id": logical_resource_id,
                       "physical_resource_id": physical_resource_id,
                       "region": region,
                       "stackid": stackid}
        error_msg.append({"exception": str(e)})
    finally:
        try:
            lambda_client.delete_function(FunctionName=function_name)
        except Exception:
            logger.warning("Failed to cleanup lambda function", exc_info=1)
        try:
            logger.debug({"test_subnet_connectivity:security_group_id": security_group_id})
            enis = ec2_client.describe_network_interfaces(Filters=[{'Name': 'group-id',
                                                                    'Values': [security_group_id]}])
            for eni in enis['NetworkInterfaces']:
                if 'Attachment' in eni.keys():
                    logger.debug("Detaching ENI...")
                    ec2_client.detach_network_interface(AttachmentId=eni['Attachment']['AttachmentId'])
                    while 'Attachment' in ec2_client.describe_network_interfaces(
                        NetworkInterfaceIds=[eni['NetworkInterfaceId']]
                    )['NetworkInterfaces'][0].keys():
                        logger.debug("eni still attached, waiting 5 seconds...")
                        sleep(5)
                logger.debug("Deleting ENI %s" % eni['NetworkInterfaceId'])
                ec2_client.delete_network_interface(NetworkInterfaceId=eni['NetworkInterfaceId'])
            sg = False
            retries = 0
            max_retries = 3
            while not sg:
                try:
                    sg = ec2_client.delete_security_group(GroupId=security_group_id)
                except botocore.exceptions.ClientError as e:
                    msg = "has a dependent object"
                    dep_violation = e.response['Error']['Code'] == 'DependencyViolation'
                    logger.debug("boto exception: ", exc_info=1)
                    if dep_violation and msg in str(e) and retries < max_retries:
                        msg = "eni deletion not propagated yet, sleeping a bit and then retrying"
                        logger.debug({"test_subnet_connectivity:delete_sg_retry": security_group_id})
                        retries += 1
                        sleep(5*(retries**2))
                    else:
                        raise
            logger.debug({"test_subnet_connectivity:security_group_id_response": response})
        except Exception:
            logger.warning("Failed to cleanup security group", exc_info=1)
        if len(error_msg) > 0:
            results["error_msg"] = error_msg
        return results


def lambda_handler(event, context):
    try:
        logger.config(context.aws_request_id, loglevel=loglevel)
        logger.debug("Handler starting...")
        logger.debug(event)
        pipeline_run.consume_event(event, context, loglevel=loglevel)
        logger.info({'event': 'new_invoke'})
        logger.debug(pipeline_run.artifacts)
        logger.debug({'ci_configs': pipeline_run.ci_configs})
        results = pipeline_run.test_stacks(test_subnet_connectivity,
                                           resource_types=["AWS::EC2::Subnet"],
                                           logical_resource_id_prefix="PrivateSubnet")
        logger.info(results)
        if len(results['error']) > 0:
            pipeline_run.put_job_failure("%s tests failed: %s" % (len(results['error']), results['error']))
        pipeline_run.put_job_success(results['success'])
        return

    except Exception as e:
        logger.error("Unhandled exception!", exc_info=1)
        pipeline_run.put_job_failure(str(e))

    finally:
        try:
            delete_iam_role()
        except Exception:
            logger.warning("Failed to cleanup IAM role", exc_info=1)
