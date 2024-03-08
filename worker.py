from rq import Worker, Queue, Connection
from redis import Redis

# Setup Redis connection
redis_host = "db-redis-nyc3-93249-do-user-4571001-0.c.db.ondigitalocean.com"
redis_port = 25061  # This should be an integer, e.g., 6379
redis_username = "default"  # Redis >=6 supports username
redis_password = "AVNS_xgDxBgvDmNRvM6wN0ti"

redis_conn = Redis(host=redis_host, port=redis_port, username=redis_username, password=redis_password, ssl=True, ssl_cert_reqs=None)

# Specify the list of queues the worker will listen to
queues_to_listen = ['default']

if __name__ == '__main__':
    with Connection(redis_conn):
        worker = Worker(map(Queue, queues_to_listen))
        worker.work()
