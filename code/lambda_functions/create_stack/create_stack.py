from awsclients import AwsClients
from cfnpipeline import CFNPipeline
from logger import Logger


loglevel = 'debug'
logger = Logger(loglevel=loglevel)
logger.info('New Lambda container initialised, logging configured.')
clients = AwsClients(logger)
pipeline_run = CFNPipeline(logger, clients)


def lambda_handler(event, context):
    try:
        logger.config(context.aws_request_id)
        logger.debug("Handler starting...")
        logger.debug(event)
        pipeline_run.consume_event(event, context, loglevel=loglevel)
        logger.info({'event': 'new_invoke'})
        if pipeline_run.cleanup_previous:
            deleted_stacks = None
            if not pipeline_run.continuation_event:
                logger.info({'event': 'pre-delete_start'})
                deleted_stacks = pipeline_run.cleanup_previous_stacks()
            elif 'pre-delete' in pipeline_run.continuation_data['message'].keys():
                logger.info({'event': 'pre-delete_continuation'})
                deleted_stacks = pipeline_run.check_statuses(
                    pipeline_run.continuation_data['message']['deleting']
                )
            if deleted_stacks:
                if pipeline_run.handle_deletes(deleted_stacks):
                    # delete handler sent a failure or continuation, so exit
                    return
        try:
            stacks_in_event = 'stacks' in pipeline_run.continuation_data['message'].keys()
        except Exception:
            stacks_in_event = False
        if not stacks_in_event:
            logger.info({'event': 'create_stacks'})
            stacks = pipeline_run.create_stacks()
        else:
            logger.info({'event': 'create_stacks_continuation'})
            stacks = pipeline_run.continuation_data['message']['stacks']
            updated_stacks = pipeline_run.check_statuses(stacks['inprogress'])
            stacks['inprogress'] = updated_stacks['inprogress']
            stacks['success'] += updated_stacks['success']
            stacks['error'] += updated_stacks['error']

        if len(stacks['inprogress']) > 0:
            msg = "Stack creation still in progress..."
            data = {
                "status": msg,
                'configs': pipeline_run.ci_configs,
                'stacks': stacks
            }
            logger.info({'event': 'stack_create_continuation'})
            pipeline_run.continue_job_later(data)
            logger.debug(msg)
            return
        elif len(stacks['error']) > 0:
            deleted_stacks = None
            stacks_to_delete = []
            if pipeline_run.cleanup_non_failed and pipeline_run.cleanup_failed:
                stacks_to_delete = stacks['success'] + stacks['inprogress'] + stacks['error']
            elif pipeline_run.cleanup_failed:
                stacks_to_delete = stacks['error']
            elif pipeline_run.cleanup_non_failed:
                stacks_to_delete = stacks['success'] + stacks['inprogress']
            try:
                delete_continuation = 'post-delete' in pipeline_run.continuation_data['message'].keys()
            except Exception:
                delete_continuation = False
            if not delete_continuation:
                if stacks_to_delete != []:
                    logger.info({'event': 'post-delete_start'})
                    deleted_stacks = pipeline_run.delete_stacks(stacks_to_delete)
            else:
                logger.info({'event': 'post-delete_continuation'})
                deleted_stacks = pipeline_run.check_statuses(
                    pipeline_run.continuation_data['message']['deleting']
                )
            if deleted_stacks:
                if pipeline_run.handle_deletes(deleted_stacks, stacks, 'post'):
                    # delete handler sent a failure or continuation, so exit
                    logger.info({'event': 'post-delete_complete'})
                    return
            msg = "%s StackCreate failures %s" % (len(stacks['error']), stacks['error'])
            pipeline_run.put_job_failure(msg)
            logger.debug("%s StackCreate failures %s" % (len(stacks['error']), stacks['error']))
            return
        logger.info({'event': 'stack_create_complete', "stacks": stacks['success']})
        pipeline_run.upload_output_artifact(stacks['success'])
        msg = "%s StackCreate success %s" % (len(stacks['success']), stacks['success'])
        pipeline_run.put_job_success(msg)
        return

    except Exception as e:
        logger.error("Unhandled exception!", exc_info=1)
        pipeline_run.put_job_failure(str(e))
