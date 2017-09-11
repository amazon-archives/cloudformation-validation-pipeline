import os
from boto3 import client
from boto3 import session
from botocore.vendored import requests
from pygit2 import clone_repository
from pygit2 import init_repository
from pygit2 import GitError
from pygit2 import RemoteCallbacks
from pygit2 import Signature
from pygit2 import UserPass
import shutil
from time import sleep
import crhelper
import zipfile

# initialise logger
logger = crhelper.log_config({"RequestId": "CONTAINER_INIT"})
logger.info('Logging configured')
# set global to track init failures
init_failed = False

ci_config = """global:
  regions:
    - ap-southeast-1
    - ca-central-1
    - eu-west-2
    - us-east-2
tests:
  defaults:
    parameter_input: aws-vpc-defaults.json
    template_file: aws-vpc.template"""

try:
    # Place initialization code here
    s3 = client('s3')
    kms = client('kms')
    iam_client = client('iam')
    cc_client = client('codecommit')
    logger.info("Container initialization completed")
except Exception as e:
    logger.error(e, exc_info=True)
    init_failed = e


def get_codecommit_credentials(username, repo_name):
    iam_client.create_user(UserName=username)
    iam_client.attach_user_policy(UserName=username,
                                  PolicyArn="arn:aws:iam::aws:policy/AWSCodeCommitFullAccess")
    response = iam_client.create_service_specific_credential(UserName=username,
                                                             ServiceName="codecommit.amazonaws.com")
    user_id = response['ServiceSpecificCredential']['ServiceSpecificCredentialId']
    username = response['ServiceSpecificCredential']['ServiceUserName']
    print([user_id, username])
    password = response['ServiceSpecificCredential']['ServicePassword']
    while not policy_propagated(repo_name):
        logger.info("waiting for role propogation...")
        sleep(15)
    return user_id, username, password


def policy_propagated(repo_name):
    try:
        cc_client.get_repository(repositoryName=repo_name)
        return True
    except Exception as e:
        logger.debug(str(e), exc_info=1)
        return False


def delete_codecommit_credentials(credential_id, username):
    try:
        iam_client.delete_service_specific_credential(UserName=username,
                                                      ServiceSpecificCredentialId=credential_id)
    except Exception:
        pass
    try:
        iam_client.detach_user_policy(UserName=username,
                                      PolicyArn="arn:aws:iam::aws:policy/AWSCodeCommitFullAccess")
    except Exception:
        pass
    iam_client.delete_user(UserName=username)


def create_repo(repo_path):
    if os.path.exists(repo_path):
            logger.info('Cleaning up repo path...')
            shutil.rmtree(repo_path)
    repo = init_repository(repo_path)
    return repo


def pull_repo(source_url, remote_branch):
    src_prefix = ".".join(source_url.split('.')[:-1])
    src_suffix = source_url.split('/')[-1]
    repo = clone_repository(src_prefix, "/tmp/" + src_suffix, bare=False, remote=init_remote)
    branch_ref = repo.lookup_reference('refs/heads/%s' % remote_branch)
    repo.checkout_tree(repo.get(branch_ref.target))
    branch_ref.set_target(branch_ref.target)
    repo.head.set_target(branch_ref.target)
    return repo


def setup_ci_config(repo, remote_branch):
    f = open('/tmp/src/ci/config.yml', 'w')
    f.write(ci_config)
    f.close()
    index = repo.index
    index.add_all()
    index.write()
    tree = index.write_tree()
    author = Signature('Template Validation Pipeline Clone', 'demo@solutions.amazonaws')
    repo.create_commit('refs/heads/%s' % remote_branch, author, author, 'limit ci to defaults', tree, [repo.head.get_object().hex])


def push_repo(repo, remote_url, creds, remote_branch):
    try:
        repo.remotes.set_url('origin', remote_url)
        repo.remotes.set_push_url('origin', remote_url)
        repo.remotes[0].push(['refs/heads/%s' % remote_branch], creds)
        return True
    except GitError as e:
        logger.info(e)
        if e.args[0] == 'Unexpected HTTP status code: 403':
            return False


def init_remote(repo, name, url):
    remote = repo.remotes.create(name, url, "+refs/*:refs/*")
    mirror_var = "remote.{}.mirror".format(name)
    repo.config[mirror_var] = True
    return remote


def s3_region_url():
    region_session = session.Session()
    region = region_session.region_name
    if region == 'us-east-1':
        return 's3.amazonaws.com'
    else:
        return 's3-' + region + '.amazonaws.com'


def create(event, context):
    """
    Place your code to handle Create events here
    """
    logger.info(event)
    physical_resource_id = 'myResourceId'
    response_data = {}
    source_url = event['ResourceProperties']['SourceRepoUrl']
    source_branch = event['ResourceProperties']['SourceRepoBranch']
    source_bucket = event['ResourceProperties']['SourceS3Bucket']
    source_key = event['ResourceProperties']['SourceS3Key']
    s3_zip_filename = source_key.split('/')[-1]
    dest_url = event['ResourceProperties']['DestRepoUrl']
    repo_name = event['ResourceProperties']['DestRepoName']
    username = event['ResourceProperties']['DestRepoName']
    if len(username) >= 64:
        raise Exception('Username is longer than 64 chars')
    user_id, codecommit_username, password = get_codecommit_credentials(username, repo_name)
    try:
        creds = RemoteCallbacks(credentials=UserPass(codecommit_username, password))
        if source_url != "":
            repo = pull_repo(source_url, source_branch)
            # Uncomment the next line if you want to update your ci files to a minimal default
            # setup_ci_config(repo)
        else:
            # Fetch source from S3
            repo = create_repo('/tmp/s3source')
            r = requests.get('https://' + s3_region_url() + '/' + source_bucket + '/' + source_key, stream=True)
            if r.status_code == 200:
                with open('/tmp/' + s3_zip_filename, 'wb') as f:
                    for chunk in r:
                        f.write(chunk)
            else:
                raise Exception("cannot fetch zip, s3 returned %s: %s" % (r.status_code, r.reason))
            zip = zipfile.ZipFile('/tmp/' + s3_zip_filename)
            zip.extractall(path='/tmp/s3source')
            author = Signature('Template Validation Pipeline Clone', 'demo@solutions.amazonaws')
            tree = repo.TreeBuilder().write()
            repo.create_commit('HEAD', author, author, 'initial commit', tree, [])
            index = repo.index
            index.add_all()
            index.write()
            tree = index.write_tree()
            repo.create_commit('refs/heads/%s' % source_branch, author, author, 'initial commit', tree,
                               [repo.head.get_object().hex])
        while not push_repo(repo, dest_url, creds, source_branch):
            logger.info("waiting for git credential propagation...")
            sleep(5)
    except Exception:
        logger.error("Unhandled exception: ", exc_info=1)
        raise
    delete_codecommit_credentials(user_id, username)
    return physical_resource_id, response_data


def update(event, context):
    """
    Place your code to handle Update events here
    """
    physical_resource_id = event['PhysicalResourceId']
    response_data = {}
    return physical_resource_id, response_data


def delete(event, context):
    """
    Place your code to handle Delete events here
    """
    username = event['ResourceProperties']['DestRepoName']
    try:
        response = iam_client.list_service_specific_credentials(UserName=username,
                                                                 ServiceName="codecommit.amazonaws.com")
        credential_id = response['ServiceSpecificCredentials'][0]['ServiceSpecificCredentialId']
    except Exception:
        pass
    try:
        iam_client.delete_service_specific_credential(UserName=username,
                                                      ServiceSpecificCredentialId=credential_id)
    except Exception:
        pass
    try:
        iam_client.detach_user_policy(UserName=username,
                                      PolicyArn="arn:aws:iam::aws:policy/AWSCodeCommitFullAccess")
    except Exception:
        pass
    try:
        iam_client.delete_user(UserName=username)
    except Exception:
        pass
    return


def lambda_handler(event, context):
    """
    Main handler function, passes off it's work to crhelper's cfn_handler
    """
    # update the logger with event info
    global logger
    logger = crhelper.log_config(event)
    return crhelper.cfn_handler(event, context, create, update, delete, logger,
                                init_failed)
