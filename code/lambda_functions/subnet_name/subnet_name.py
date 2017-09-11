from awsclients import AwsClients
from cfnpipeline import CFNPipeline
from logger import Logger

# Initialise logging
loglevel = 'debug'
logger = Logger(loglevel=loglevel)
logger.info('New Lambda container initialised, logging configured.')

# Initialise boto client factory
clients = AwsClients(logger)

# Initialise CFNPipeline helper library
pipeline_run = CFNPipeline(logger, clients)


def test_subnet_name(region, stackid, logical_resource_id, physical_resource_id):

    logger.debug({"test_subnet_name": "starting"})
    # Create an empty list to put errors into (so you can have more than 1 error per test)
    error_msg = []

    # Setup our output object, if there are errors we will flip the "success" key to False
    results = {"success": True,
               "logical_resource_id": logical_resource_id,
               "physical_resource_id": physical_resource_id,
               "region": region,
               "stackid": stackid}

    try:
        # Get a boto3 client and describe the subnet
        ec2_client = clients.get('ec2', region)
        response = ec2_client.describe_subnets(SubnetIds=[physical_resource_id])
        logger.debug({"test_subnet_name:describe_subnets": response})

        # Initialise subnet_type
        subnet_type = None

        # If there are no tags the subnet has no name, so raise an exception
        if 'Tags' not in response['Subnets'][0].keys():
            raise ValueError('Subnet name is not defined')

        # Loop through subnet tags looking for the "Name" tag
        for tag in response['Subnets'][0]['Tags']:
            if tag['Key'] == 'Name':
                # Check if "PRIV" or "DMZ" are in the name
                if 'PRIV' in tag['Value'] and 'DMZ' not in tag['Value']:
                    subnet_type = 'PRIV'
                elif 'DMZ' in tag['Value'] and 'PRIV' not in tag['Value']:
                    subnet_type = 'DMZ'
                # If the name contains both, that's wrong, so raise an exception
                elif 'PRIV' in tag['Value'] and 'DMZ' in tag['Value']:
                    raise ValueError('Cannot have both "PRIV" and "DMZ" in subnet name')
        # If there were no "Name" tags containing 'DMZ' or 'PRIV' raise an exception
        if not subnet_type:
            raise ValueError('Subnet name does not contain "PRIV" or "DMZ"')

    # catch all exceptions and treat them as test failures
    except Exception as e:
        # Log the exception, including a traceback
        logger.error({"test_subnet_name": str(e)}, exc_info=1)
        # If we're here the test failed, flip success to False and add exception message to the error list
        results["success"] = False
        error_msg.append({"exception": str(e)})
    finally:
        # If there are error messages, append them to the output
        if len(error_msg) > 0:
            results["error_msg"] = error_msg

        # return our findings
        return results


def lambda_handler(event, context):
    # Wrap everything in try/except to make sure we alway respond to CodePipeline
    try:
        # Add pipeline execution details to logging
        logger.config(context.aws_request_id, loglevel=loglevel)
        logger.debug("Handler starting...")
        logger.debug(event)
        pipeline_run.consume_event(event, context, loglevel=loglevel)
        logger.info({'event': 'new_invoke'})
        logger.debug(pipeline_run.artifacts)
        logger.debug({'ci_configs': pipeline_run.ci_configs})

        # Call the test runner, specifying the name of the test function and the types of resources to test
        results = pipeline_run.test_stacks(test_subnet_name, resource_types=["AWS::EC2::Subnet"])

        # if there are any tests that failed return a failure to CodePipeline, else return success
        if len(results['error']) > 0:
            pipeline_run.put_job_failure("%s tests failed: %s" % (len(results['error']), results['error']))
        else:
            pipeline_run.put_job_success(results['success'])
        return

    # something went wrong that we weren't expecting, probably a fault in the test logic
    except Exception as e:
        logger.error("Unhandled exception!", exc_info=1)
        pipeline_run.put_job_failure(str(e))
