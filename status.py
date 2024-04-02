import redis
from redis import Redis
import os
import time
import json


def add_job_to_user_index(redis_client, user_email, job_id):
    """
    Adds a job ID to the set of jobs associated with a user_email.
    
    :param redis_client: Redis connection object.
    :param user_email: The email of the user who submitted the job.
    :param job_id: The unique ID of the job.
    """
    key = f"user_jobs:{user_email}"
    redis_client.sadd(key, job_id)



def set_job_attributes(redis_client, job_id, attributes):
    """
    Stores or updates job attributes in Redis, keyed by job_id.
    
    :param redis_client: Redis connection object.
    :param job_id: The unique ID of the job.
    :param attributes: Dictionary containing the attributes to store.
    """
    key = f"job:{job_id}"
    for attribute, value in attributes.items():
        redis_client.hset(key, attribute, value)

def get_job_attributes(redis_client, job_id):
    """
    Retrieves job attributes from Redis using the job_id.
    
    :param redis_client: Redis connection object.
    :param job_id: The unique ID of the job.
    :return: Dictionary of the job attributes, or None if not found.
    """
    key = f"job:{job_id}"
    attributes = redis_client.hgetall(key)
    if not attributes:
        return None  # Return None if the job doesn't exist
    
    return {k.decode('utf-8'): v.decode('utf-8') for k, v in attributes.items()}


def get_user_job_ids(redis_client, user_email):
    """
    Retrieves all job IDs associated with a user_email.
    
    :param redis_client: Redis connection object.
    :param user_email: The email of the user.
    :return: Set of job IDs.
    """
    key = f"user_jobs:{user_email}"
    return {job_id.decode('utf-8') for job_id in redis_client.smembers(key)}

def get_job_status(redis_client, job_id):
    """
    Retrieves the status of a job from Redis.
    
    :param redis_client: Redis connection object.
    :param job_id: The unique ID of the job.
    :return: The status of the job as a string, or None if not found.
    """
    key = f"job:{job_id}"
    status = redis_client.hget(key, "status")
    return status.decode('utf-8') if status else None


def update_job_status(redis_client, job_id, new_status):
    """
    Updates the status of an existing job in Redis.
    
    :param redis_client: Redis connection object.
    :param job_id: The unique ID of the job.
    :param new_status: The new status to set for the job.
    """
    key = f"job:{job_id}"
    redis_client.hset(key, "status", new_status)


def update_job_progress(redis_client, job_id, progress):
    """
    Update the job progress in Redis.

    :param redis_client: The Redis connection instance.
    :param job_id: The ID of the job whose progress is being updated.
    :param progress: The progress percentage to set.
    """
    redis_client.set(f'{job_id}:progress', progress)


def get_job_progress(redis_client, job_id):
    # Example: Retrieve progress from Redis. Implement based on your application's logic.
    progress = redis_client.get(f'{job_id}:progress')
    return int(progress) if progress else 0
