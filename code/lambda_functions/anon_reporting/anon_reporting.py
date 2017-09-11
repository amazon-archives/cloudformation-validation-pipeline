import crhelper
from datetime import datetime
from hashlib import sha256
import json
import uuid
import urllib2

# initialise logger
logger = crhelper.log_config({"RequestId": "CONTAINER_INIT"})
logger.info('Logging configured')
init_failed = False


def send_data(uuid, solution_id, stack_event, region, stack_id):
    logger.info("Sending anonymous data")
    data_dict = {
        'TimeStamp': str(datetime.utcnow().isoformat()),
        'UUID': uuid,
        'Data': {
            "status": "stack_" + stack_event.lower(),
            "stack_hash": sha256(stack_id).hexdigest(),
            "region": region
        },
        'Solution': solution_id,
    }
    data_json = json.dumps(data_dict)
    logger.info("Data: %s", data_json)
    url = 'https://oszclq8tyh.execute-api.us-east-1.amazonaws.com/prod/generic'
    headers = {'content-type': 'application/json'}
    req = urllib2.Request(url, data_json, headers)
    rsp = urllib2.urlopen(req)
    rspcode = rsp.getcode()
    content = rsp.read()
    logger.info("Response from APIGateway: %s, %s", rspcode, content)


def create(event, context):
    physical_resource_id = str(uuid.uuid4())
    response_data = {}
    send_data(
        physical_resource_id,
        event['ResourceProperties']['SolutionID'],
        event['RequestType'],
        event['StackId'].split(':')[3],
        event['StackId']
    )
    return physical_resource_id, response_data


def update(event, context):
    physical_resource_id = event['PhysicalResourceId']
    response_data = {}
    send_data(
        physical_resource_id,
        event['ResourceProperties']['SolutionID'],
        event['RequestType'],
        event['StackId'].split(':')[3],
        event['StackId']
    )
    return physical_resource_id, response_data


def delete(event, context):
    physical_resource_id = event['PhysicalResourceId']
    send_data(
        physical_resource_id,
        event['ResourceProperties']['SolutionID'],
        event['RequestType'],
        event['StackId'].split(':')[3],
        event['StackId']
    )
    return


def lambda_handler(event, context):
    # update the logger with event info
    global logger
    logger = crhelper.log_config(event, loglevel='debug')
    return crhelper.cfn_handler(event, context, create, update, delete, logger,
                                init_failed)
