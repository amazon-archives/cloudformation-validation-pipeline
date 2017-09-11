import boto3
import crhelper
import re
import uuid

# initialise logger
logger = crhelper.log_config({"RequestId": "CONTAINER_INIT"})
logger.info('Logging configured')
init_failed = False


def get_regions(region, service):
    if region == 'ALL':
        s = boto3.session.Session(region_name='us-east-1')
        return s.get_available_regions(service)
    else:
        return [region]


def get_all_stacks():
    regions = get_regions('ALL', 'cloudformation')
    stacks = {}
    for region in regions:
        stacks[region] = []
        cfn_client = boto3.client('cloudformation', region_name=region)
        response = cfn_client.list_stacks(StackStatusFilter=[
            'CREATE_FAILED', 'CREATE_COMPLETE', 'ROLLBACK_COMPLETE',
            'UPDATE_COMPLETE', 'UPDATE_ROLLBACK_COMPLETE', 'DELETE_FAILED'])
        for stack in response['StackSummaries']:
            describe_response = cfn_client.describe_stacks(StackName=stack['StackName'])
            for tag in describe_response['Stacks'][0]['Tags']:
                if tag['Key'] == 'cfn_cicd_pipeline':
                    stacks[region].append({
                        'name': stack['StackName'], 'id': stack['StackId'], 'pipeline': tag['Value'],
                        'status': stack['StackStatus'], 'created': stack['CreationTime'].replace(tzinfo=None),
                        'tags': describe_response['Stacks'][0]['Tags'], 'region': region})
    return stacks


def iter_stacks(stacks, filter_func, filter_val):
    filtered_stacks = {}
    for region in stacks.keys():
        filtered_stacks[region] = []
        for stack in stacks[region]:
            if filter_func(stack, filter_val):
                filtered_stacks[region].append(stack)
    return filtered_stacks


def filter_pipeline_name(stack, pipeline_name):
    for tag in stack['tags']:
        if tag['Key'] == 'cfn_cicd_pipeline' and tag['Value'] == pipeline_name:
            return True
    return False


def delete_provisioned_product(provisioned_product_id, stack_id, region, cfn_client):
    """Deletes a particular provisioned product and all the other related Service Catalog artifacts.

    Args:
        Provisioned product (str): provisioned_product_id for provisioned product to be deleted
    """
    sc_client = boto3.client('servicecatalog', region_name=region)
    try:
        logger.debug("Deleting provisioned product %s in %s" % (provisioned_product_id, region))
        response = sc_client.scan_provisioned_products(AccessLevelFilter={'Key': 'Account', 'Value': 'self'})
        while 'PageToken' in response:
            for item in response['ProvisionedProducts']:
                if item['Id'] == provisioned_product_id:
                    record_id = item['LastRecordId']
            response = sc_client.scan_provisioned_products(AccessLevelFilter={'Key': 'Account', 'Value': 'self'},
                                                           PageSize=1,
                                                           PageToken=response['PageToken']
                                                           )
        for item in response['ProvisionedProducts']:
            if item['Id'] == provisioned_product_id:
                record_id = item['LastRecordId']
        response = sc_client.describe_record(Id=record_id)
        product_id = response['RecordDetail']['ProductId']
        try:
            response = sc_client.terminate_provisioned_product(ProvisionedProductId=provisioned_product_id,
                                                               TerminateToken=str(uuid.uuid4()))
            logger.debug("Provisioned product %s terminated" % provisioned_product_id)
        except Exception as e:
            logger.error("Failed to terminate provisioned product %s. Falling back to deleting the CloudFormation stack instead" % (provisioned_product_id), exc_info=1)
            try:
                logger.debug("Deleting stack %s in %s" % (stack_id, region))
                cfn_client.delete_stack(StackName=stack_id)
            except Exception as e:
                logger.error("Failed to delete stack %s in %s" % (stack_id, region), exc_info=1)
                raise e
        response = sc_client.list_portfolios_for_product(ProductId=product_id)
        portfolio_id = response['PortfolioDetails'][0]['Id']
        response = sc_client.list_principals_for_portfolio(PortfolioId=portfolio_id)
        principal_arn = response['Principals'][0]['PrincipalARN']
        response = sc_client.disassociate_principal_from_portfolio(PortfolioId=portfolio_id, PrincipalARN=principal_arn)
        logger.debug("Principal %s disassociated from portfolio %s" % (principal_arn, portfolio_id))
        response = sc_client.list_constraints_for_portfolio(PortfolioId=portfolio_id)
        constraint_id = response['ConstraintDetails'][0]['ConstraintId']
        response = sc_client.delete_constraint(Id=constraint_id)
        logger.debug("Constraint %s deleted from portfolio %s" % (constraint_id, portfolio_id))
        response = sc_client.disassociate_product_from_portfolio(ProductId=product_id, PortfolioId=portfolio_id)
        logger.debug("Product %s disassociated from portfolio %s" % (product_id, portfolio_id))
        response = sc_client.delete_product(Id=product_id)
        logger.debug("Product %s deleted from %s" % (product_id, region))
        response = sc_client.delete_portfolio(Id=portfolio_id)
        logger.debug("Portfolio %s deleted from %s" % (portfolio_id, region))
        return {'status': "success", 'stackid': stack_id, 'region': region, 'detail': None}
    except Exception as e:
        logger.error("Failed to delete provisioned product %s with stack %s in %s" % (provisioned_product_id,
                                                                                      stack_id,
                                                                                      region), exc_info=1)


def delete_stacks(stacks):
    for region in stacks.keys():
        if len(stacks[region]) > 0:
            cfn_client = boto3.client('cloudformation', region_name=region)
            for stack in stacks[region]:
                # Check for Service Catalog stacks
                match = re.search(r'(pp-)\w+', stack['id'])
                if match is not None:
                    logger.debug('Service Catalog product detected: %s with provisioned product id %s' % (stack, match.group()))
                    delete_provisioned_product(match.group(), stack['id'], region, cfn_client)
                else:
                    print('deleting stack %s in %s from pipeline %s' % (stack['name'], region, stack['pipeline']))
                    cfn_client.delete_stack(StackName=stack['name'])


def create(event, context):
    physical_resource_id = "cleanup_stacks_on_delete"
    response_data = {}
    return physical_resource_id, response_data


def update(event, context):
    physical_resource_id = event['PhysicalResourceId']
    response_data = {}
    return physical_resource_id, response_data


def delete(event, context):
    pipeline = event['ResourceProperties']['Pipeline']
    stacks = get_all_stacks()
    filtered_stacks = iter_stacks(stacks, filter_pipeline_name, pipeline)
    delete_stacks(filtered_stacks)
    return


def lambda_handler(event, context):
    # update the logger with event info
    global logger
    logger = crhelper.log_config(event, loglevel='debug')
    return crhelper.cfn_handler(event, context, create, update, delete, logger,
                                init_failed)
