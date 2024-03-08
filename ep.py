from flask import Flask, request, jsonify,render_template
from redis import Redis
from rq import Queue
from infer_client import main
import os
import uuid
from rq import Worker, Queue, Connection
from redis import Redis

from multiprocessing import Process

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
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


@app.route('/')
def index():
    return render_template('ui.html')

# Adjust this part in your Flask app
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'})
    file = request.files['file']
    speaker_name = request.form.get('speaker_name', '')
    if file.filename == '':
        return jsonify({'error': 'No selected file'})
    if file:
        filename = uuid.uuid4().hex + '_' + file.filename
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        # Adjusted to pass filepath and speaker_name to the main function
        job = q.enqueue(main, filepath, speaker_name)
        p = Process(target=start_worker)
        p.start()     
        return jsonify({'message': 'File uploaded successfully', 'job_id': job.get_id()})

def start_worker():
    queues_to_listen = ['default']
    print("start the worker")

    with Connection(redis_conn):
        worker = Worker(map(Queue, queues_to_listen))
        print("before starting work")
        worker.work()




@app.route('/status/<job_id>', methods=['GET'])
def check_status(job_id):
    from rq.job import Job
    job = Job.fetch(job_id, connection=redis_conn)
    return jsonify({'status': job.get_status(), 'job_id': job_id})

if __name__ == "__main__":
   
    app.run(debug=False)
    
