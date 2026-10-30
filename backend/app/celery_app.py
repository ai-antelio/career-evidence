"""Broker-backed production worker; only server-side environment config."""
import os
from celery import Celery
from kombu import Queue

celery=Celery('career',broker=os.getenv('CELERY_BROKER_URL','amqp://career:local-development-only@rabbitmq:5672//'))
celery.conf.update(
    task_serializer='json',accept_content=['json'],result_serializer='json',
    task_ignore_result=True,task_store_errors_even_if_ignored=False,
    task_acks_late=True,task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,task_default_delivery_mode='persistent',
    broker_connection_retry_on_startup=True,broker_transport_options={'confirm_publish':True},
    task_publish_retry=True,task_publish_retry_policy={'max_retries':2,'interval_start':0,'interval_step':1,'interval_max':2},
    task_queues=tuple(Queue(name,durable=True) for name in ['documents','ai','maintenance']),
    task_default_queue='ai',task_send_sent_event=False,worker_send_task_events=False,
    task_soft_time_limit=240,task_time_limit=270,
)

@celery.task(name='career.dispatch',acks_late=True,reject_on_worker_lost=True,ignore_result=True)
def dispatch(topic,target_id):
    # Task arguments are only IDs. Full input and credentials never enter broker payloads.
    from .db import Session
    if topic=='document':
        from .worker import run_once
        return run_once(job_id=target_id)
    if topic=='career':
        from .career_worker import run_once
        return run_once(Session,job_id=target_id)
    if topic=='deletion':
        from .tracking import process_deletion_job
        return process_deletion_job(target_id)
    raise ValueError('Unknown task topic')
