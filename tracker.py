from redis import Redis
from rq import Queue
from infer_client import main
from rq.job import Job
import time
from rq import Worker, Queue, Connection

def check_job_status(job_key,redis_conn):
    """Function to print the status of a job given its job ID."""
    job = Job.fetch(job_key, redis_conn)
    print(f"Job Status: {job.get_status()}")

if __name__ == "__main__":
    redis_host = os.getenv('REDIS_HOST', 'default_host')
    redis_port = int(os.getenv('REDIS_PORT', 25061))  # Default Redis port
    redis_username = os.getenv('REDIS_USERNAME', 'default')
    redis_password = os.getenv('REDIS_PASSWORD', ''
    redis_conn = Redis(host=redis_host, port=redis_port, username=redis_username, password=redis_password, ssl=True, ssl_cert_reqs=None)
    q = Queue(connection=redis_conn)

    
    
    

    # Queue the main function
    job = q.enqueue(main)
    with Connection(redis_conn):
    worker = Worker(map(Queue, ['default']))
    worker.work()

    # Check the status immediately (likely to be 'queued' or 'started')
    check_job_status(job.get_id(),redis_conn)

    # You might want to periodically check the status
    # This could be done in a loop with a sleep, or based on some event in your application
    time.sleep(10)  # Example: Check after some time
    check_job_status(job.get_id(),redis_conn)