from flask import Flask, request, jsonify,render_template
from redis import Redis
from rq import Queue
from infer_client import main
from trainendtoend import main
import os
import uuid
from rq import Worker, Queue, Connection
from redis import Redis

from multiprocessing import Process

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
MAX_WORKERS = 6  # Adjust based on your requirements
WORKER_COUNT_KEY = 'worker_count'

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
# Setup Redis connection
# Fetch Redis connection parameters from environment variables
redis_host = os.getenv('REDIS_HOST', 'default_host')
redis_port = int(os.getenv('REDIS_PORT', 25061))  # Default Redis port
redis_username = os.getenv('REDIS_USERNAME', 'default')
redis_password = os.getenv('REDIS_PASSWORD', '')
redis_conn = Redis(host=redis_host, port=redis_port, username=redis_username, password=redis_password, ssl=True, ssl_cert_reqs=None)
q = Queue(connection=redis_conn)

@app.route('/login/callback')
def authorize():
    token = google.authorize_access_token()
    user_info = google.parse_id_token(token)
    
    # Assuming user_info contains an email field
    user_email = user_info.get('email')
    
    # Use user's email as a key to store their information in Redis
    redis_conn.hset(f"user:{user_email}", mapping=user_info)
    
    # Set session or a cookie to indicate that the user is logged in
    session['user_email'] = user_email
    session['logged_in'] = True
    
    return 'Login Successful'



@app.route('/')
def index():
    return render_template('ui.html')

# Adjust this part in your Flask app
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'})
    file = request.files['file']
    model_name = request.form.get('speaker_name', '')
    if file.filename == '':
        return jsonify({'error': 'No selected file'})
    if file:
        filename = uuid.uuid4().hex + '_' + file.filename
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        print(filepath)
        # Adjusted to pass filepath and speaker_name to the main function
        job = q.enqueue(main, filepath, model_name)
        p = Process(target=start_worker)
        p.start()     
        return jsonify({'message': 'File uploaded successfully', 'job_id': job.get_id()})

def start_worker():
    # Fetch the current number of workers
    current_worker_count = int(redis_conn.get(WORKER_COUNT_KEY) or 0)
    
    if current_worker_count < MAX_WORKERS:
        # Increment the worker count atomically
        redis_conn.incr(WORKER_COUNT_KEY)
        
        try:
            queues_to_listen = ['default']
            with Connection(redis_conn):
                worker = Worker(map(Queue, queues_to_listen))
                worker.work()
        finally:
            # Ensure the worker count is decremented when the worker stops working
            redis_conn.decr(WORKER_COUNT_KEY)
    else:
        print("Maximum number of workers reached. Not starting a new worker.")




@app.route('/status/<job_id>', methods=['GET'])
def check_status(job_id):
    from rq.job import Job
    job = Job.fetch(job_id, connection=redis_conn)
    return jsonify({'status': job.get_status(), 'job_id': job_id})

if __name__ == "__main__":
   
    app.run(debug=False)
    
