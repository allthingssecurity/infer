from rq import Worker, Queue, Connection
from redis import Redis

redis_host = os.getenv('REDIS_HOST', 'default_host')
redis_port = int(os.getenv('REDIS_PORT', 25061))  # Default Redis port
redis_username = os.getenv('REDIS_USERNAME', 'default')
redis_password = os.getenv('REDIS_PASSWORD', ''
redis_conn = Redis(host=redis_host, port=redis_port, username=redis_username, password=redis_password, ssl=True, ssl_cert_reqs=None)
#q = Queue(connection=redis_conn)

# Specify the list of queues the worker will listen to
queues_to_listen = ['default']

if __name__ == '__main__':
    with Connection(redis_conn):
        worker = Worker(map(Queue, queues_to_listen))
        worker.work()
