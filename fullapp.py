from flask import Flask, session, redirect, url_for, request,render_template,flash,jsonify,send_file
from authlib.integrations.flask_client import OAuth
import redis
from redis import Redis
import os
import time
from functools import wraps
from mutagen.mp3 import MP3
from authlib.integrations.flask_client import OAuth
from flask_session import Session
import base64
from flask import request
import logging
from logging.handlers import RotatingFileHandler
from trainendtoend import train_model,convert_voice,generate_video_job
import os
import uuid
from rq import Worker, Queue, Connection
from redis import Redis
from upload import upload_to_do,download_from_do,download_from_do_with_job_id,download_for_video
from werkzeug.utils import secure_filename
from multiprocessing import Process
from credit import get_user_credits,update_user_credits,use_credit,add_credits
from datetime import datetime
import requests
from pydub import AudioSegment
import io
from admin import admin_blueprint
from status import set_job_attributes,update_job_status,get_job_attributes,add_job_to_user_index,get_user_job_ids
from pydub import AudioSegment
import io
from rq.job import Job
import tempfile
import click
from flask.cli import with_appcontext
import magic

#import librosa
#import soundfile as sf
#import pyrubberband as pyrb
#import razorpay
#client = razorpay.Client(auth=("YOUR_API_KEY", "YOUR_API_SECRET"))

# Now you can use datetime in your code



app = Flask(__name__)
app.register_blueprint(admin_blueprint)
app.secret_key = 'your_secret_key'
UPLOAD_FOLDER = 'uploads'
MAX_WORKERS = 20  # Adjust based on your requirements
WORKER_COUNT_KEY = 'worker_count'



oauth = OAuth(app)
google = oauth.register(
    name='singer',
    client_id='158446367723-fie5o9bjnn20ik2c68h06fjd2ran8fdo.apps.googleusercontent.com',
    client_secret='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',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile',
    }
)

app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


razorpay_key = os.getenv('RAZORPAY_KEY', '')
razorpay_secret = os.getenv('RAZORPAY_SECRET', '')

redis_host = os.getenv('REDIS_HOST', 'default_host')
redis_port = int(os.getenv('REDIS_PORT', 25061))  # Default Redis port
redis_username = os.getenv('REDIS_USERNAME', 'default')
redis_password = os.getenv('REDIS_PASSWORD', '')
#redis_conn = Redis(host=redis_host, port=redis_port, username=redis_username, password=redis_password, ssl=True, ssl_cert_reqs=None)




redis_client = Redis(host=redis_host, port=redis_port, username=redis_username, password=redis_password, ssl=True, ssl_cert_reqs=None)

app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_REDIS'] = redis_client

# Initialize Flask-Session
Session(app)


handler = RotatingFileHandler('app.log', maxBytes=10000, backupCount=3)
handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)

logger = logging.getLogger('my_app_logger')
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# If you still want to attach this to your Flask app's logger for any reason:
app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO)


#app.logger.addHandler(handler)
#app.logger.setLevel(logging.INFO)

q = Queue(connection=redis_client)
# Initialize Redis
FEATURE_FLAG_WAITLIST = True 


@app.cli.command("start-workers")
@with_appcontext
def start_workers():
    
    #redis_url = os.getenv['REDIS_URL']
    #redis_conn = Redis.from_url(redis_url)
    redis_host = os.getenv('REDIS_HOST', 'default_host')
    redis_port = int(os.getenv('REDIS_PORT', 25061))  # Default Redis port
    redis_username = os.getenv('REDIS_USERNAME', 'default')
    redis_password = os.getenv('REDIS_PASSWORD', '')

    # Creating a Redis client and attaching it to the app config
    redis_client = Redis(host=redis_host, port=redis_port, username=redis_username, password=redis_password, ssl=True, ssl_cert_reqs=None)
    
    with Connection(redis_client):
        
        for _ in range(2):
        # Assuming 'rq' command is available in the environment
        # and the workers are configured to listen to the 'default' queue.
        # Adjust the command as necessary for your environment.
        #subprocess.Popen(['rq', 'worker', 'default'])
        #start_worker()
            app.logger.info("Started an RQ worker.")
            worker = Worker(Queue())
            worker.work()


def create_app():
    app = Flask(__name__)
    redis_host = os.getenv('REDIS_HOST', 'default_host')
    redis_port = int(os.getenv('REDIS_PORT', 25061))  # Default Redis port
    redis_username = os.getenv('REDIS_USERNAME', 'default')
    redis_password = os.getenv('REDIS_PASSWORD', '')

    # Creating a Redis client and attaching it to the app config
    redis_client = Redis(host=redis_host, port=redis_port, username=redis_username, password=redis_password, ssl=True, ssl_cert_reqs=None)
    start_rq_workers()
    return app

def login_required(f):
    @wraps(f)  # Preserve the function name and docstring
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def is_feature_waitlist_enabled():
    # Placeholder for actual feature flag check
    return FEATURE_FLAG_WAITLIST

def is_user_authorized(user_email):
    return redis_client.sismember("authorized_users", user_email)

def is_user_in_waitlist(user_email):
    return redis_client.sismember("waitlist_users", user_email)





def start_rq_workers(worker_count=2):
    """
    Start a specified number of RQ workers.
    """
    for _ in range(worker_count):
        # Assuming 'rq' command is available in the environment
        # and the workers are configured to listen to the 'default' queue.
        # Adjust the command as necessary for your environment.
        #subprocess.Popen(['rq', 'worker', 'default'])
        start_worker()
        app.logger.info("Started an RQ worker.")


def convert_audio_to_mp3(file, upload_folder='/tmp'):
    """
    Checks the MIME type of the uploaded file and converts it to MP3 if necessary.
    Returns the path to the MP3 file (or the original file if no conversion was needed).

    Args:
        file (FileStorage): The uploaded file object from Flask request.
        upload_folder (str): The directory where the file will be saved.

    Returns:
        str: Path to the MP3 file or the original file.
    """
    # Ensure the upload folder exists
    os.makedirs(upload_folder, exist_ok=True)

    # Secure the filename and save the original file temporarily
    
    if file.filename == '':
        # Generate a unique filename to avoid collisions
        original_filename = uuid.uuid4().hex + ".mp3"
    else:
        original_filename = secure_filename(file.filename)
    
    temp_path = os.path.join(upload_folder, original_filename)
    
    
    #original_filename = secure_filename(file.filename)
    #temp_path = os.path.join(upload_folder, original_filename)
    file.save(temp_path)

    # Use python-magic to identify the MIME type of the file
    mime_type = magic.from_file(temp_path, mime=True)
    app.logger.info(f"file mime type={mime_type}")
    # Define the output path
    output_filename = original_filename.rsplit('.', 1)[0] + '.mp3'
    output_path = os.path.join(upload_folder, output_filename)

    # Check if the file is already in MP3 format or if it's a supported audio format for conversion
    if mime_type == 'audio/mpeg':
        # File is already an MP3, so no conversion needed
        return temp_path
    elif mime_type in ['audio/wav', 'audio/webm', 'audio/ogg']:
        # Convert to MP3 using FFmpeg
        app.logger.info(f"convert to mp3")
        subprocess.run(['ffmpeg', '-i', temp_path, '-vn', '-ar', 44100, '-ac', 2, '-b:a', '192k', output_path], check=True)
        
        # Cleanup the temporary original file if conversion was successful
        os.remove(temp_path)
        return output_path
    else:
        # Unsupported format, return the original file or handle accordingly
        return temp_path


from pydub import AudioSegment
import os
import tempfile

def analyze_audio_file1(file_path, max_size_bytes=10*1024*1024, max_duration_minutes=6):
    """
    Analyzes an uploaded audio file for size, format, and duration.

    :param file_path: Path to the audio file.
    :param max_size_bytes: Maximum allowed file size in bytes.
    :param max_duration_minutes: Maximum allowed audio duration in minutes.
    :return: A dictionary with success status, an error message if applicable, the audio duration in minutes, and a format check.
    """
    print("entered analyse audio")
    app.logger.info("entered audio analysis")
    
    # Check if the file extension is .mp3
    if not file_path.lower().endswith('.mp3'):
        return {'success': False, 'error': 'Only MP3 files are allowed.', 'duration': None}
    app.logger.info("file check succeeded")
    
    try:
        # Check file size
        app.logger.info("entered try block")
        file_size = os.path.getsize(file_path)
        if file_size > max_size_bytes:
            return {'success': False, 'error': 'File size exceeds the allowed limit.', 'duration': None}
        
        # Load the audio file for processing
        app.logger.info("before reading")
        audio = AudioSegment.from_file(file_path)
        
        # Calculate audio length in minutes
        audio_length_minutes = len(audio) / 60000.0
        app.logger.info(f"audio length={audio_length_minutes}")
        if audio_length_minutes > max_duration_minutes:
            return {'success': False, 'error': 'Audio length exceeds the allowed duration.', 'duration': audio_length_minutes}
    
    except Exception as e:
        app.logger.error(f"error in file analysis={str(e)}")
        return {'success': False, 'error': f'Failed to process the audio file: {str(e)}', 'duration': None}
    
    # If all checks pass
    return {'success': True, 'error': None, 'duration': audio_length_minutes}




def analyze_audio_file(file, max_size_bytes=10*1024*1024, max_duration_minutes=6):
    """
    Analyzes an uploaded audio file for size, format, and duration using a temporary file for audio processing.

    :param file: FileStorage object from Flask's request.files.
    :param max_size_bytes: Maximum allowed file size in bytes.
    :param max_duration_minutes: Maximum allowed audio duration in minutes.
    :return: A dictionary with success status, an error message if applicable, the audio duration in minutes, and a format check.
    """
    
    print("entered analyse audio")
    app.logger.info("entered audio analysis")
    # Check if the file extension is .mp3
    
    
    if not file.filename.lower().endswith('.mp3'):
        return {'success': False, 'error': 'Only MP3 files are allowed.', 'duration': None}
    app.logger.info("file check succeeded")
    # Create a temporary copy of the file for all operations
    file_copy = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
    file.save(file_copy.name)
    file_copy.close()
    
    try:
        # Check file size using the temporary file
        app.logger.info("entered try block")
        file_size = os.path.getsize(file_copy.name)
        if file_size > max_size_bytes:
            os.remove(file_copy.name)  # Clean up temporary file
            return {'success': False, 'error': 'File size exceeds the allowed limit.', 'duration': None}

        # Load the audio file for processing
        app.logger.info("before reading")
        audio = AudioSegment.from_file(file_copy.name)
        
        # Calculate audio length in minutes
        audio_length_minutes = len(audio) / 60000.0
        app.logger.info("audio length={audio_length_minutes}")
        if audio_length_minutes > max_duration_minutes:
            os.remove(file_copy.name)  # Clean up temporary file
            return {'success': False, 'error': 'Audio length exceeds the allowed duration.', 'duration': audio_length_minutes}
    
    except Exception as e:
        os.remove(file_copy.name)  # Ensure the temporary file is removed in case of an error
        app.logger.error(f"error in file analysis={str(e)}")
        return {'success': False, 'error': f'Failed to process the audio file: {str(e)}', 'duration': None}
    
    # Clean up temporary file after successful processing
    os.remove(file_copy.name)
    
    # If all checks pass
    return {'success': True, 'error': None, 'duration': audio_length_minutes}


    

@app.route('/add_to_waitlist', methods=['POST'])
@login_required
def add_to_waitlist():
    if not is_feature_waitlist_enabled():
        return jsonify({'error': 'Waitlist feature is not enabled'}), 403

    user_email = session.get('user_email')
    if not user_email:
        return jsonify({'error': 'User not signed in'}), 401
    
    if is_user_in_waitlist(user_email):
        return jsonify({'message': 'Already in waitlist'}), 200

    redis_client.sadd("waitlist_users", user_email)
    return jsonify({'message': 'Added to waitlist. We will get back to you. Till that time you can check samples'}), 200


@app.route('/authorize_users', methods=['POST'])
def authorize_users():
    # This endpoint could be protected to be accessible only by admins
    users_to_authorize = request.json.get('users')
    if not users_to_authorize:
        return jsonify({'error': 'No users provided'}), 400
    
    for user_email in users_to_authorize:
        if is_user_in_waitlist(user_email):
            redis_client.srem("waitlist_users", user_email)
            redis_client.sadd("authorized_users", user_email)
    
    return jsonify({'message': f'Authorized {len(users_to_authorize)} users'}), 200





def has_active_jobs(user_email,type_of_job):
    """
    Check if the user has any jobs that are either queued or started.
    """
    user_key = user_job_key(user_email,type_of_job)
    jobs = redis_client.hgetall(user_key)
    for status in jobs.values():
        if status.decode('utf-8') in ['queued', 'started']:
            return True
    return False





def validate_audio_file(file):
    """
    Validates the uploaded audio file based on its size and length.
    
    :param file: The uploaded file object.
    :param spk_id: The speaker ID or model ID associated with the file.
    :return: A tuple containing a JSON response and status code if validation fails, or (None, None) if validation succeeds.
    """
    # Check file size
    if file.content_length > 10 * 1024 * 1024:  # 10 MB limit
        return jsonify({"error": "File size exceeds 10 MB"}), 400

    app.logger.info("after file access")
    app.logger.info("check if model is there in weights dir or not")
    filename_without_extension = os.path.splitext(file.filename)[0]
    
   

    # Map content types to audio formats
    content_type_format_map = {
        'audio/mpeg': 'mp3',
        'audio/wav': 'wav',
        'audio/x-wav': 'wav',
        'audio/mp4': 'mp4',
        'audio/x-m4a': 'mp4',
    }

    # Default to 'mp3' if content type is unknown
    audio_format = content_type_format_map.get(file.content_type, 'mp3')

    # Convert the uploaded file to an audio segment
    try:
        audio = AudioSegment.from_file(io.BytesIO(file.read()), format=audio_format)
    except Exception as e:
        return jsonify({"error": f"Failed to process the audio file: {str(e)}"}), 400
    finally:
        file.seek(0)  # Reset file pointer after reading

    # Calculate audio length in minutes
    audio_length_minutes = len(audio) / 60000.0  # pydub returns length in milliseconds

    if audio_length_minutes > 6:  # 5 minutes limit
        return jsonify({"error": "Audio length exceeds 5 minutes"}), 400

    # If the file passes all checks
    return None, None



def generate_nonce(length=32):
    return base64.urlsafe_b64encode(os.urandom(length)).rstrip(b'=').decode('ascii')

# Setup OAuth and Google configuration as before
@app.route('/login/callback')
def authorize():
    # The code to handle the callback and authorization logic goes here
    app.logger.info("entered authorize code")
    app.logger.info(f'Request URL:: {request.url}')
    app.logger.info(f'Request URL:: {request.args}')
    print("Query Parameters::", request.url)
    print("Query Parameters:", request.args)
    token = google.authorize_access_token()
    app.logger.info(f"token={token}")
    nonce = session.pop('oauth_nonce', None)
    user_info = google.parse_id_token(token, nonce=nonce)
    
    
    user_profile_response = google.get('https://www.googleapis.com/oauth2/v3/userinfo')
    user_profile = user_profile_response.json()
    app.logger.info(f"User profile response: {user_profile}")  # Use logging
    print(user_profile)  # Or just print it for debugging purposes
    print(user_info['email'])
    
    app.logger.info(user_info['email'])
    
    
    
    if 'email' in user_info:
        session['user_email'] = user_info['email']
        session['logged_in'] = True
        session['user_image'] = user_profile.get('picture', None)
        app.logger.info("before invoking user account creation")
        create_user_account_if_not_exists(user_info['email'])
        app.logger.info("after invoking user account creation")
        user_email=user_info['email']
        model_credits=get_user_credits(user_email,'model')
        song_credits=get_user_credits(user_email,'song')
        video_credits=get_user_credits(user_email,'video')
      # Adjust this function to your implementation
    #return render_template('index.html', user_info=session, model_credits=model_credits, song_credits=song_credits,video_credits=video_credits)
        
        if is_feature_waitlist_enabled():
            if not is_user_authorized(user_email):
                if is_user_in_waitlist(user_email):
                    # User is in waitlist, can only see samples
                    return render_template('waitlist_only_samples.html', user_info=session)
                else:
                    # User not in waitlist, prompt to join
                    return render_template('join_waitlist.html', user_info=session)
        
        
        
        
        # Perform any additional processing or actions as needed
        return render_template('index.html',user_info=session,model_credits=model_credits, song_credits=song_credits,video_credits=video_credits)
    else:
        # Handle the case where the email is not available
        return redirect(url_for('login'))
    # Process user_info or perform actions such as logging in the user
    return render_template('join_waitlist.html')


def check_user_access_and_credits(user_email, job_type='infer', credit_type='song'):
    """
    Check if the user has access to a feature and if they can submit a new job.

    Parameters:
    - user_email: The email of the user.
    - job_type: The type of job to check for active jobs.
    - credit_type: The type of credits to check for the user.

    Returns:
    - A tuple containing a JSON response and an HTTP status code.
    """

    # Check if the feature waitlist is enabled and if the user is authorized or in the waitlist
    if is_feature_waitlist_enabled():
        if not is_user_authorized(user_email):
            if is_user_in_waitlist(user_email):
                return {'error': 'You are on the waitlist but not yet authorized. Please wait for authorization.'}, 403
            else:
                return {'error': 'You must join the waitlist to access this feature.'}, 403

    # Check if the user already has an active job of the specified type
    if has_active_jobs(user_email, job_type):
        app.logger.info(f"Job already running for this user {user_email}")
        return {'message': 'Cannot submit new job. A job is already queued or started'}, 200

    # Check the user's credits for the specified type
    credit_count = get_user_credits(user_email, credit_type)
    app.logger.info(f"Credits for  this user {user_email} are {credit_count}")
    
    if credit_count > 0:
        # If the user has credits, return a positive response to proceed
        return {'message': 'User is authorized and can submit a new job.'}, 200
    else:
        # If the user has no credits, return an error message
        return {'error': 'Insufficient credits to submit a new job.'}, 403



# @app.route('/get-inference-jobs')
# @login_required
# def get_inference_jobs():
    # user_email = session['user_email']
    # inference_jobs_key = user_job_key(user_email, 'infer')
    # inference_jobs = redis_client.hgetall(inference_jobs_key)
    # formatted_inference_jobs = {key.decode('utf-8'): value.decode('utf-8') for key, value in inference_jobs.items()}
    
    # For a web page, you would use render_template and pass the jobs to it
    # return render_template('select-inference-job.html', inference_jobs=formatted_inference_jobs)
    
    # For an AJAX call, you might return JSON
    # return jsonify(inference_jobs=formatted_inference_jobs)



@app.route('/get-inference-jobs')
@login_required
def get_inference_jobs():
    user_email = session.get('user_email')

    # Retrieve all job IDs associated with the user
    job_ids = get_user_job_ids(redis_client, user_email)
    # Initialize a dictionary to specifically store inference jobs
    inference_jobs_data = []

    for job_id in job_ids:
        job_attributes = get_job_attributes(redis_client, job_id)
        
        # Filter for inference jobs
        if job_attributes and job_attributes.get('type') == 'infer':
            app.logger.info("entered infer jobs")
            job_attributes['job_id'] = job_id  # Ensure the job_id is included
            inference_jobs_data.append(job_attributes)

    
    app.logger.info(f'inference jobs= {inference_jobs_data}')
    # Decide on the response format based on the request (e.g., AJAX or direct web access)
    # For simplicity, here's how you might return JSON for an AJAX call:
    return jsonify(inference_jobs=inference_jobs_data)



@app.route('/get-jobs1')
@login_required
def get_jobs1():
    
    user_email = session['user_email']
    training_jobs_key = user_job_key(user_email, 'train')
    inference_jobs_key = user_job_key(user_email, 'infer')
    video_jobs_key = user_job_key(user_email, 'video')
    training_jobs = redis_client.hgetall(training_jobs_key)
    inference_jobs = redis_client.hgetall(inference_jobs_key)
    video_jobs= redis_client.hgetall(video_jobs_key)
    formatted_training_jobs = {key.decode('utf-8'): value.decode('utf-8') for key, value in training_jobs.items()}
    formatted_inference_jobs = {key.decode('utf-8'): value.decode('utf-8') for key, value in inference_jobs.items()}
    formatted_video_jobs = {key.decode('utf-8'): value.decode('utf-8') for key, value in video_jobs.items()}
    model_credits=get_user_credits(user_email,'model')
    song_credits=get_user_credits(user_email,'song')
    
    return render_template('job-tracking.html', training_jobs=formatted_training_jobs, inference_jobs=formatted_inference_jobs,video_jobs=formatted_video_jobs,model_credits=model_credits,song_credits=song_credits)


@app.route('/recharge_credits', methods=['POST'])
def recharge_credits():
    data = request.get_json()
    user_email = data.get('user_email')
    activity = data.get('activity')
    credits_to_add = int(data.get('credits', 0))
    
    if not user_email or not activity or credits_to_add <= 0:
        return jsonify({'error': 'Invalid request'}), 400

    current_credits = get_user_credits(user_email, activity)
    new_credits = current_credits + credits_to_add
    update_user_credits(user_email, activity, new_credits)

    return jsonify({'message': f'Successfully added {credits_to_add} {activity} credits to {user_email}.',
                    'total_credits': new_credits}), 200




def create_user_account_if_not_exists(user_email, initial_tier="trial"):
    """
    Create a new user account with the given tier, only if it doesn't already exist.
    """
    user_exists_key = f"user:{user_email}:exists"  # Key to check if user account already exists
    user_exists = redis_client.get(user_exists_key)
    app.logger.info("entered create user account")
    if not user_exists:
        # User does not exist, so initialize their account
        model_credits = 2
        song_credits = 5
        video_credits= 2
        update_user_credits(user_email, "model", model_credits)
        update_user_credits(user_email, "song", song_credits)
        update_user_credits(user_email, "video", video_credits)
        # Set the user exists key in Redis
        redis_client.set(user_exists_key, 1)
        app.logger.info("account and credits initialized")    
        print(f"Account and credits initialized for {user_email}.")
    else:
        # User already exists, no need to re-initialize
        print(f"User {user_email} already exists, skipping initialization.")
        
        
def get_user_tier(user_email,task_type):
    """
    Retrieve the current tier of the user.
    """
    app.logger.info(f'check user existence {user_email}')
    return redis_client.hget(f"user:{user_email}:{task_type}", "tier").decode("utf-8")

def update_user_tier(user_email, task_type,new_tier):
    """
    Update the user's tier to a new value (e.g., upgrading to premium).
    """
    redis_client.hset(f"user:{user_email}:{task_type}", "tier", new_tier)

@app.route('/login')
def login():
    # Generate a nonce and save it in the session
    print("Accessed the login endpoint")
    app.logger.info('Accessed the login endpoint')
    nonce = generate_nonce()
    session['oauth_nonce'] = nonce
    
    # Include the nonce in your authorization request
    redirect_uri = url_for('authorize', _external=True)
    app.logger.info(f'Redirect URI for OAuth: {redirect_uri}')
    print(f"Redirect URI for OAuth: {redirect_uri}")
    return google.authorize_redirect("https://www.maibhisinger.com/login/callback", nonce=nonce)



@app.route('/')
def index():
    user_email = session.get('user_email')
    if not user_email:
        # User not logged in; redirect to login or directly ask to join waitlist
        return redirect(url_for('login'))  # Assuming you have a login route

    if is_feature_waitlist_enabled():
        if not is_user_authorized(user_email):
            if is_user_in_waitlist(user_email):
                # User is in waitlist, can only see samples
                return render_template('waitlist_only_samples.html', user_info=session)
            else:
                # User not in waitlist, prompt to join
                return render_template('join_waitlist.html', user_info=session)
    # User is authorized, show full page
    user_image = session.get('user_image', None)
    model_credits=get_user_credits(user_email,'model')
    song_credits=get_user_credits(user_email,'song')
    video_credits=get_user_credits(user_email,'video')
      # Adjust this function to your implementation
    return render_template('index.html', user_info=session, model_credits=model_credits, song_credits=song_credits,video_credits=video_credits)


#old code will be removed  
@app.route('/')
def index1():
    if 'logged_in' in session and session['logged_in']:
        user_info = {
            'name': session.get('user_name', 'Unknown'),  # Assuming you've stored the user's name here
            'picture': session.get('user_picture', '')   # Assuming you've stored the profile picture URL here
        }
        user_email = session.get('user_email')
        app.logger.info(f'creating account in redis for user {user_email}')
        create_user_account_if_not_exists(user_email)
        app.logger.info(f'account created in redis for user {user_email}')
        model_credits=get_user_credits(user_email,'model')
        song_credits=get_user_credits(user_email,'song')
        return render_template('index.html', user_info=user_info,model_credits=model_credits,song_credits=song_credits)
    else:
        return redirect(url_for('login'))

@app.route('/song_conversion')
@login_required
def song_conversion():
    
    user_email = session.get('user_email')
    if user_email:
        models = redis_client.lrange(user_email, 0, -1)  # Get list of models
        models = [model.decode('utf-8') for model in models]
        model_credits=get_user_credits(user_email,'model')
        song_credits=get_user_credits(user_email,'song')
        video_credits=get_user_credits(user_email,'video')
        return render_template('convert.html', models=models,model_credits=model_credits,song_credits=song_credits,video_credits=video_credits)
    else:
        models = []
        model_credits=get_user_credits(user_email,'model')
        song_credits=get_user_credits(user_email,'song')
        video_credits=get_user_credits(user_email,'video')
        return render_template('convert.html', models=models,model_credits=model_credits,song_credits=song_credits,video_credits=video_credits)
        
    

@app.route('/models')
@login_required
def models():
    # Check user's model count from Redis and render accordingly
    user_email = session.get('user_email')  # Assuming current_user has an email attribute
    models = redis_client.lrange(user_email, 0, -1) # Assuming set usage; adapt if using lists
    models = [model.decode('utf-8') for model in models]
    return render_template('models.html', models=models)
    pass





@app.route('/upgrade')
@login_required
def upgrade():
    return render_template('payment_form.html')

def dummy_song_converted():
    # Simulate some processing
    time.sleep(5)  # Sleep for 5 seconds to simulate computation
    return "Song convered successfully"


def dummy_model_training():
    # Simulate some processing
    time.sleep(5)  # Sleep for 5 seconds to simulate computation
    return "Model trained successfully"


@app.route('/gen_video')
@login_required
def gen_video():
    user_email = session.get('user_email')  # Assuming current_user has an email attribute
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    else:
        if is_feature_waitlist_enabled():
            if not is_user_authorized(user_email):
                if is_user_in_waitlist(user_email):
                    return jsonify({'error': 'You are on the waitlist but not yet authorized. Please wait for authorization.'}), 403
                else:
                    return jsonify({'error': 'You must join the waitlist to access this feature.'}), 403
        model_credits=get_user_credits(user_email,'model')
        song_credits=get_user_credits(user_email,'song')
        video_credits=get_user_credits(user_email,'video')
        
        return render_template('video.html',model_credits=model_credits,song_credits=song_credits,video_credits=video_credits)




@app.route('/train')
@login_required
def train():
    user_email = session.get('user_email')  # Assuming current_user has an email attribute
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    else:
        if is_feature_waitlist_enabled():
            if not is_user_authorized(user_email):
                if is_user_in_waitlist(user_email):
                    return jsonify({'error': 'You are on the waitlist but not yet authorized. Please wait for authorization.'}), 403
                else:
                    return jsonify({'error': 'You must join the waitlist to access this feature.'}), 403
        model_credits=get_user_credits(user_email,'model')
        song_credits=get_user_credits(user_email,'song')
        video_credits=get_user_credits(user_email,'video')
        
        return render_template('train.html',model_credits=model_credits,song_credits=song_credits,video_credits=video_credits)







@app.route('/infer')
@login_required
def infer():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    else:
        user_email = session.get('user_email')
        if is_feature_waitlist_enabled():
            if not is_user_authorized(user_email):
                if is_user_in_waitlist(user_email):
                    return jsonify({'error': 'You are on the waitlist but not yet authorized. Please wait for authorization.'}), 403
                else:
                    return jsonify({'error': 'You must join the waitlist to access this feature.'}), 403
        
        return render_template('infer.html', user_email=user_email)





@app.route('/start_infer', methods=['POST'])
@login_required
def start_infer():
    print("entered infer")
    user_email = session.get('user_email')
    
    if is_feature_waitlist_enabled():
        if not is_user_authorized(user_email):
            if is_user_in_waitlist(user_email):
                return jsonify({'error': 'You are on the waitlist but not yet authorized. Please wait for authorization.'}), 403
            else:
                return jsonify({'error': 'You must join the waitlist to access this feature.'}), 403

    
    if has_active_jobs(user_email,'infer'):
        app.logger.info(f"job already running for this user {user_email} ")
        return jsonify({'message': 'Cannot submit new job. A job is already queued or started'})
    credit_count=get_user_credits(user_email,'song')
    #user_tier = get_user_tier(user_email,'infer')
    #current_count = int(redis_client.hget(f"user:{user_email}:infer", "songs_converted"))
    #tier_limits = {"trial": 2, "premium": 4}
    if (credit_count > 0):
        
        

        # Proceed with your file processing logic here if validation succeeds
        
        

        if 'file' not in request.files:
            return jsonify({'error': 'No file part'})
        file = request.files['file']
        print("analyse audio")
        analysis_results = analyze_audio_file(file)
        
        if not analysis_results['success']:
            return jsonify({"error": analysis_results['error']}), 400
        speaker_name = request.form.get('spk_id', '')
        app.logger.info(f"enqued the job for speaker {speaker_name} ")
        if file.filename == '':
            return jsonify({'error': 'No selected file'})
        app.logger.info("starting to infer")
        
        final_speaker_name=f'{user_email}_{speaker_name}'
        trained_model_key = f"{user_email}:trained"
        if not redis_client.exists(trained_model_key):
            # Model not trained for this speaker
            return jsonify({'error': 'Model is not yet trained for the specified speaker'})

        if file:
            #validation_response, status_code = validate_audio_file(file)
            #if validation_response:
            #    return validation_response, status_code
            file.seek(0)
            filename = file.filename  # Original filename
            file_extension = os.path.splitext(filename)[1]  # Extracts file extension including the dot (.)
            new_filename = f"{uuid.uuid4()}{file_extension}"  # Generates a new filename with original extension
            filepath = os.path.join(UPLOAD_FOLDER, secure_filename(new_filename))
            file.save(filepath)
            response = upload_to_do(filepath)
            app.logger.info(f"file sent to DO={new_filename}")
            
            if os.path.exists(filepath):
                app.logger.info("File exists, proceeding with the process.")
    # Place the code here that should run after confirming the file exists
            else:
                app.logger.info("File does not exist, cannot proceed.")
                return jsonify({'message': 'Issue with file upload'})
            
            app.logger.info(f'file saved with filepath =: {filepath}')
            # Adjusted to pass filepath and speaker_name to the main function
            
            absolute_path = os.path.abspath(filepath)
            #os.chmod(absolute_path, 0o666)
            
            job = q.enqueue_call(            
                func=convert_voice, 
                args=(new_filename, final_speaker_name,user_email),  # Positional arguments for my_function
                
                timeout=2500  # Job-specific parameters like timeout
        )
            
            app.logger.info("enqueed the job ")
            #job = q.enqueue(convert_voice, absolute_path, final_speaker_name,user_email)
            #job.meta['file_name'] = filename
            #job.meta['submission_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            #job.save_meta()  # Don't forget to save the metadata
            
            app.logger.info(f"Job ID: {job.get_id()}")
            app.logger.info(f"Job Status: {job.get_status()}")

            
            
            type_of_job = "infer"
            job_id = job.id
            add_job_to_user_index(redis_client,user_email,job_id)
            attributes = {
                "type":type_of_job,
                "filename": filename,
                "submission_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                
            }

            # Set job attributes
            set_job_attributes(redis_client,job_id, attributes)
            #set_job_attributes(type_of_job, user_email,job_id, attributes)
            
            
            
            if user_email:
                # Update Redis with the new job ID and its initial status
                app.logger.info(f"updating redis for job id {job.id} ")
                #user_key = user_job_key(user_email,'infer')
                #redis_client.hset(user_key, job.id, "queued")  # Initial status is "queued"
                
                #update_job_status(type_of_job,user_email,'queued')
                update_job_status(redis_client,job_id,'queued')
                app.logger.info(f"updated redis for job id {job.id} ")
                
                #try:
                #    p = Process(target=start_worker)
                #    p.start()     
                return jsonify({'message': 'File uploaded successfully for conversion', 'job_id': job.get_id()})
                #except Exception as e:
                #    return jsonify({'message': 'Failed to start process'})
    else:
        app.logger.info(f"max song conversion exceeded for the user {user_email}. Buy credits")
        return jsonify({'message': 'You have reached max limits for song conversion. Buy credits '})


@app.route('/download_video/<job_id>')
@login_required
def download_video(job_id):
    # Here, you would determine the file_key from the job_id
    # For this example, let's assume they are the same
    file_key = f'{job_id}.mp4'
    
    # Call the download function
    #local_file_path = download_from_do_with_job_id(job_id)
    local_file_path = download_from_do(file_key)
    if local_file_path:
        return send_file(local_file_path, as_attachment=True)
    else:
        return "Download failed", 404




@app.route('/download/<job_id>')
@login_required
def download(job_id):
    # Here, you would determine the file_key from the job_id
    # For this example, let's assume they are the same
    file_key = f'{job_id}.mp3'
    
    # Call the download function
    local_file_path = download_from_do(file_key)
    
    if local_file_path:
        return send_file(local_file_path, as_attachment=True)
    else:
        return "Download failed", 404









def user_job_key(user_email,type_of_job):
    """Generate a Redis key based on user email."""
    return f"user_jobs_{type_of_job}:{user_email}"


@app.route('/process_audio1', methods=['POST'])
def process_audio1():
    user_email = session.get('user_email')
    
    if is_feature_waitlist_enabled():
        if not is_user_authorized(user_email):
            if is_user_in_waitlist(user_email):
                return jsonify({'error': 'You are on the waitlist but not yet authorized. Please wait for authorization.'}), 403
            else:
                return jsonify({'error': 'You must join the waitlist to access this feature.'}), 403

    #if has_active_jobs(user_email,'train'):
    #    app.logger.info(f"job already running for this user {user_email} ")
    #    return jsonify({'message': 'Cannot submit new job. A job is already queued or started'})
    
    
    
    
    credit_count=get_user_credits(user_email,'song')
    app.logger.info(f"credits for {user_email}={credit_count}")
    if (credit_count >0):
    
        
    
    
        app.logger.info("enough credits")
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'})
        file = request.files['file']
        model_name = request.form.get('model_name', '')
        #converted_path = convert_audio_to_mp3(file)
        
        app.logger.info(f"model for {user_email}={model_name}")
        
        if file and file.filename == '':
        # If no filename is detected, assign a default or generated filename
            filename = 'default_filename.mp3'
        else:
        # Use the actual filename from the upload
            filename = file.filename
        
        #if file.filename == '':
        #    app.logger.info(f"no file name")
        #    return jsonify({'error': 'No selected file'})
        app.logger.info(f"before analysing audio")
        analysis_results = analyze_audio_file(file)
        app.logger.info(f"after analysing audio")
        if not analysis_results['success']:
            return jsonify({"error": analysis_results['error']}), 400    
        
        if file:
        
            #validation_response, status_code = validate_audio_file(file)
            #if validation_response:
            #    return validation_response, status_code
            file.seek(0)
            filename = uuid.uuid4().hex + '_' + file.filename
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            
            print(filepath)
            app.logger.info(f"filepath={filepath}")
            response = upload_to_do(filepath)
            user_email = session.get('user_email')
            print(user_email)
            # Adjusted to pass filepath and speaker_name to the main function
            job = q.enqueue_call(
                func=train_model, 
                args=(filename, model_name,user_email),  # Positional arguments for my_function
                
                timeout=2500  # Job-specific parameters like timeout
            )
            
                        
            type_of_job='train'
            job_id = job.id
            add_job_to_user_index(redis_client,user_email,job_id)
            attributes = {
                "type": type_of_job,
                "filename": filename,
                "type":type_of_job,
                
                "submission_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                
            }

                    # Set job attributes
                    
            set_job_attributes(redis_client,job_id, attributes)
                
            if user_email:
                # Update Redis with the new job ID and its initial status
                #user_key = user_job_key(user_email,'train')
                #redis_client.hset(user_key, job.id, "queued")  # Initial status is "queued"
                update_job_status(redis_client,job_id,'queued')
                #job = q.enqueue(main, filename, model_name)
                p = Process(target=start_worker)
                p.start()     
                return jsonify({'message': 'Model Training Job Started with ', 'job_id': job.get_id()})
    else:
        app.logger.info(f"max train jobs exceeded for the user {user_email} ")
        return jsonify({'message': 'You have reached max limits '})





@app.route('/process_audio', methods=['POST'])
def process_audio():
    user_email = session.get('user_email')
    
    # Insert your feature waitlist and credit checks here.
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    model_name = request.form.get('model_name', '')

    # Convert the audio file to MP3 if necessary and get the path.
    converted_path = convert_audio_to_mp3(file)
    app.logger.info(f"converted path={converted_path}")

    # Generate a secure, unique filename for the processed file.
    secure_filename = uuid.uuid4().hex + '_' + (file.filename if file.filename else "uploaded_audio.mp3")
    filepath = os.path.join(UPLOAD_FOLDER, secure_filename)
    os.rename(converted_path, filepath)
    app.logger.info(f"File saved to {filepath}")
    # Assuming convert_audio_to_mp3 saves the file, open it for further processing.
    #with open(converted_path, 'rb') as file:
     #   app.logger.info("Before analysing audio")
    analysis_results = analyze_audio_file1(filepath)
    #    app.logger.info("After analysing audio")
    if not analysis_results['success']:
        return jsonify({"error": analysis_results['error']}), 400

    # File has been analyzed; now move it to a permanent location.
    response = upload_to_do(filepath)
    
    # Example of further processing: queue a job for model training.
    job = q.enqueue_call(func=train_model, args=(secure_filename, model_name, user_email), timeout=2500)
    job_id = job.get_id()
    add_job_to_user_index(redis_client, user_email, job_id)
    
    attributes = {
        "type": "train",
        "filename": secure_filename,
        "submission_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    set_job_attributes(redis_client, job_id, attributes)
    update_job_status(redis_client, job_id, 'queued')

    # Optionally, start a background worker if not already running.
    # Be cautious with starting processes; ensure it's controlled and necessary.
    # p = Process(target=start_worker)
    # p.start()

    return jsonify({'message': 'Model Training Job Started', 'job_id': job_id})







def start_worker():
    # Fetch the current number of workers
    app.logger.info("entered start worker")
    current_worker_count = int(redis_client.get(WORKER_COUNT_KEY) or 0)
    app.logger.info(f"current worker={current_worker_count}")
    all_queues = Queue.all(connection=redis_client)

# Iterate over each queue to count jobs
    for queue in all_queues:
        num_jobs = len(queue)
        app.logger.info(f"Number of jobs in '{queue.name}' queue: {num_jobs}")
        
    failed_queue = Queue('failed', connection=redis_client)

# Get the number of jobs in the failed queue
    num_failed_jobs = len(failed_queue)
    print(f"Number of failed jobs: {num_failed_jobs}")
    app.logger.info(f"Number of failed jobs: {num_failed_jobs}")
    for job in failed_queue.jobs:
        app.logger.info(f"Failed Job ID: {job.get_id()}, Exception: {job.exc_info}")
    
    
    
    if current_worker_count < MAX_WORKERS:
        # Increment the worker count atomically
        redis_client.incr(WORKER_COUNT_KEY)
        
        try:
            queues_to_listen = ['default']
            with Connection(redis_client):
                worker = Worker(map(Queue, queues_to_listen))
                app.logger.info("created worker")
                worker.work(logging_level='DEBUG')
                app.logger.info("launched worker")
        finally:
            # Ensure the worker count is decremented when the worker stops working
            redis_client.decr(WORKER_COUNT_KEY)
    else:
        print("Maximum number of workers reached. Not starting a new worker.")




@app.route('/generate_video', methods=['POST'])
def generate_video():
    try:
    
        

        if request.method == 'POST':
            app.logger.info("entered generate video endpoint ")
            user_email = session.get('user_email')
            
            response, status_code = check_user_access_and_credits(user_email, 'video', 'video')
            if status_code == 200:
            # Check if the post request has the file parts
                source_image_filename = request.form.get('source_image_filename')
                source_image_path = os.path.join(app.static_folder, source_image_filename)
                app.logger.info(f"image path={source_image_path}")
                
                
                

                #if 'source_image' not in request.files :
                #    return 'Missing files', 400
                #source_image = request.files['source_image']
                job_id = request.form.get('job_id')
                if not job_id:
                    return 'Missing job ID', 400
                app.logger.info(f"image path={source_image_path}")
                #audio_path = download_for_video(job_id)
                ref_video_path = request.files.get('ref_video_path')  # Optional

                #if source_image.filename == '' :
                 #   return 'No selected image file', 400

                #source_image_filename = secure_filename(source_image.filename)
                #print(f"source file={source_image_filename}")
                
                #app.logger.info(f"audio file={audio_path}")
                #source_image_path = os.path.join(UPLOAD_FOLDER, source_image_filename)
                
                #source_image.save(source_image_path)
                filename_without_extension = os.path.splitext(source_image_filename)[0]

                # Construct the new key
                new_key = f"{filename_without_extension}##{job_id}.mp4"
                app.logger.info(f"file key={new_key}")

                ref_video_file = None
                if ref_video_path and ref_video_path.filename != '':
                    ref_video_filename = secure_filename(ref_video_path.filename)
                    ref_video_file = os.path.join(UPLOAD_FOLDER, ref_video_filename)
                    ref_video_path.save(ref_video_file)

                # Process the files
                
                job = q.enqueue_call(
                    func=generate_video_job, 
                    args=(source_image_path, job_id,ref_video_file,job_id,filename_without_extension,user_email),  # Positional arguments for my_function
                    
                    timeout=2500  # Job-specific parameters like timeout
            )
            
                type_of_job = "video"
                job_id = job.id
                add_job_to_user_index(redis_client,user_email,job_id)
                attributes = {
                    "type":type_of_job,
                    "user_email": user_email,
                    "submission_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    
                }

                # Set job attributes
                
                #set_job_attributes(type_of_job, user_email,job_id, attributes)
                set_job_attributes(redis_client,job_id, attributes)
                #update_job_status(type_of_job,user_email,'queued')
                update_job_status(redis_client,job_id,'queued')
                p = Process(target=start_worker)
                p.start()     
                app.logger.info("enqueed the job ")
                
                
                
                return jsonify(message="Files processed and uploaded successfully and Job Enqueued"), 200
            else:
                return jsonify(response), status_code
    except Exception as e:
        app.logger.info(f"An error occurred: {e}")
        return jsonify(error=str(e)), 500




@app.route('/get-jobs')
@login_required
def get_jobs():
    user_email = session.get('user_email')
    
    job_ids = get_user_job_ids(redis_client, user_email)
    jobs_data = {}

    for job_id in job_ids:
        job_attributes = get_job_attributes(redis_client, job_id)
        
        if job_attributes:
            job_attributes['job_id'] = job_id
            job_type = job_attributes.get('type', 'unknown')
            if job_type not in jobs_data:
                jobs_data[job_type] = []
            jobs_data[job_type].append(job_attributes)
    
    model_credits=get_user_credits(user_email,'model')
    song_credits=get_user_credits(user_email,'song')
    video_credits=get_user_credits(user_email,'video')
    
    return render_template('job-tracking.html', jobs_data=jobs_data,model_credits=model_credits,song_credits=song_credits)


@app.route('/get_samples', methods=['GET'])
@login_required
def get_samples():
    user_email = session.get('user_email')
    
    
    model_credits=get_user_credits(user_email,'model')
    song_credits=get_user_credits(user_email,'song')
    video_credits=get_user_credits(user_email,'video')
    
    return render_template('samples.html',model_credits=model_credits,song_credits=song_credits)
    
    
    

@app.route('/process_payment', methods=['POST'])
def process_payment():
    card_number = request.form['cardNumber']
    card_exp = request.form['cardExp']
    card_cvc = request.form['cardCVC']
    
    # Dummy check: In real scenarios, you would use a payment gateway's API here
    if card_number == "4242 4242 4242 4242" and len(card_cvc) == 3:
        # Pretend the payment was successful
        # Here, you could mark the user as having upgraded their account, for example
        if not session.get('logged_in'):
            return redirect(url_for('login'))

        user_email = session.get('user_email')
        if user_email:
            # Update the user's status in Redis to 'premium'
            redis_client.hset(f"user:{user_email}", "status", "premium")
            return "Payment successful.User upgraded to premium."
    #return "User not logged in."

    #return "Payment successful. Account upgraded."
    else:
        flash("Payment failed. Please check your card details and try again.")
        return redirect(url_for('payment_form'))

# @app.route('/process-recharge', methods=['POST'])
# @login_required
# def process_recharge():
    # user_email = session.get('user_email')

    # if not user_email:
        # return "User not logged in.", 403

    #Check if the user is a premium user
    # user_status = redis_client.hget(f"user:{user_email}", "status").decode('utf-8')
    # if user_status != 'premium':
        # return jsonify({'error': 'Only premium users can recharge'}), 403

    # amount = request.form.get('amount')

    # if amount:
        #In a real app, you would process the payment details with a payment gateway
        #Simulate successful payment by updating the user's recharge balance
        # current_balance = int(redis_client.hget(f"user:{user_email}", "recharge_balance") or 0)
        # new_balance = current_balance + int(amount)
        # redis_client.hset(f"user:{user_email}", "recharge_balance", new_balance)

        # return jsonify({'message': 'Recharge successful, new balance: ' + str(new_balance) + ' credits.'})
    # else:
        # return "Invalid request", 400


@app.route('/rechargeModel')
@login_required
def rechargeModel():
    user_email = session.get('user_email')  # Assuming current_user has an email attribute
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    else:
        if is_feature_waitlist_enabled():
            if not is_user_authorized(user_email):
                if is_user_in_waitlist(user_email):
                    return jsonify({'error': 'You are on the waitlist but not yet authorized. Please wait for authorization.'}), 403
                else:
                    return jsonify({'error': 'You must join the waitlist to access this feature.'}), 403
        model_credits=get_user_credits(user_email,'model')
        song_credits=get_user_credits(user_email,'song')
        video_credits=get_user_credits(user_email,'video')
        
        #return render_template('raz.html',model_credits=model_credits,song_credits=song_credits)
        return render_template('wip.html',model_credits=model_credits,song_credits=song_credits,video_credits=video_credits)



@app.route('/rechargeSong')
@login_required
def rechargeSong():
    user_email = session.get('user_email')  # Assuming current_user has an email attribute
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    else:
        if is_feature_waitlist_enabled():
            if not is_user_authorized(user_email):
                if is_user_in_waitlist(user_email):
                    return jsonify({'error': 'You are on the waitlist but not yet authorized. Please wait for authorization.'}), 403
                else:
                    return jsonify({'error': 'You must join the waitlist to access this feature.'}), 403
        model_credits=get_user_credits(user_email,'model')
        song_credits=get_user_credits(user_email,'song')
        video_credits=get_user_credits(user_email,'video')
        #return render_template('raz_song.html',model_credits=model_credits,song_credits=song_credits)
        return render_template('wip.html',model_credits=model_credits,song_credits=song_credits,video_credits=video_credits)



@app.route('/samples')
@login_required
def samples():
    # Display sample conversions
    return render_template('samples1.html')

@app.route('/reset-redis')
def reset_redis():
    try:
        # Clear the current database
        redis_client.flushdb()
        return "Redis data cleared successfully."
    except Exception as e:
        return f"Error clearing Redis data: {e}", 500

@app.route('/status/<job_id>', methods=['GET'])
def check_status(job_id):
    from rq.job import Job
    job = Job.fetch(job_id, connection=redis_client)
    
    file_name = job.meta.get('file_name', 'Unknown')  # Default to 'Unknown' if not set
    submission_time = job.meta.get('submission_time', 'Unknown')
    status=jsonify({'status': job.get_status(), 'file_name': file_name, 'submission_time': submission_time})
    app.logger.info(status)
    return status
    


# Assuming you have the `razorpay_order_id`, `razorpay_payment_id`, and `razorpay_signature` from the request
#def verify_payment_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
 #   params_dict = {
  #      'razorpay_order_id': razorpay_order_id,
   #     'razorpay_payment_id': razorpay_payment_id,
    #    'razorpay_signature': razorpay_signature
    #}

    # The function returns True if the signature is valid, False otherwise
    #return client.utility.verify_payment_signature(params_dict)

@app.route('/create_order', methods=['POST'])
def create_order():
    app.logger.info("create order invoked ")
    #credit_type = request.json.get('creditType')
    data = {
        'amount': request.json.get('amount', 10000),
        'currency': 'INR',
        'receipt': 'order_rcptid_11',
        'payment_capture': 1
       }
        
    
    
    response = requests.post('https://api.razorpay.com/v1/orders', auth=(razorpay_key, razorpay_secret), json=data)
    
    if response.status_code == 200:
        return jsonify(response.json()), 200
    else:
        return jsonify(response.text), response.status_code




@app.route('/update_payment_song', methods=['POST'])
@login_required
def update_payment_song():
    # Extract the payment details from the request
    app.logger.info("update payment invoked  ")
    user_email = session.get('user_email')

    if not user_email:
        return "User not logged in.", 403
    payment_details = request.json
    
    # Your logic to update the payment details in Redis
    # Make sure to handle exceptions and errors
    try:
        # Logic to update Redis with payment_details
        app.logger.info(f"before adding credits for user {user_email}")
        add_credits(app,user_email,"song",5)
        app.logger.info("after  adding credits ")

        # Mock response for success
        response = {'status': 'success'}
        return jsonify(response), 200
    except Exception as e:
        print(e)  # Log the error for debugging
        app.logger.info(f"error: {str(e)}")
        response = {'status': 'failure', 'error': str(e)}
        return jsonify(response), 500



@app.route('/update_payment_model', methods=['POST'])
@login_required
def update_payment_model():
    # Extract the payment details from the request
    app.logger.info("update payment invoked  ")
    user_email = session.get('user_email')

    if not user_email:
        return "User not logged in.", 403
    payment_details = request.json
    
    # Your logic to update the payment details in Redis
    # Make sure to handle exceptions and errors
    try:
        # Logic to update Redis with payment_details
        app.logger.info(f"before adding credits for user {user_email}")
        add_credits(app,user_email,"model",5)
        app.logger.info("after  adding credits ")

        # Mock response for success
        response = {'status': 'success'}
        return jsonify(response), 200
    except Exception as e:
        print(e)  # Log the error for debugging
        app.logger.info(f"error: {str(e)}")
        response = {'status': 'failure', 'error': str(e)}
        return jsonify(response), 500




@app.route('/payment/webhook', methods=['POST'])
def payment_webhook():
    # Extract the webhook payload
    app.logger.info("webhook invoked ")
    payload = request.get_json()
    app.logger.info(f"payload={payload}")
    event = payload['event']
    app.logger.info(f"event={event}")
    if event == 'payment.captured':
        payment_id = payload['payload']['payment']['entity']['id']
        app.logger.info(f"payment id ={payment_id}")
        order_id = payload['payload']['payment']['entity']['order_id']
        app.logger.info(f"order_id ={order_id}")
        #update_user_credits()
        # Verify payment (e.g., using Razorpay signature verification)
        #verified = verify_payment_signature(payment_id, order_id)
        
        #if verified:
        #    # Execute your post-payment logic
        #    update_order_status(order_id, 'Completed')
        #    send_confirmation_email_to_user(order_id)
            # Other business logic...
        return jsonify({"status": "success"}), 200
    else:
        return jsonify({"status": "verification failed"}), 400


# @app.route('/adjust_pitch', methods=['POST'])
# def adjust_pitch():
    # job_id = request.json['job_id']
    # pitch_factor = request.json['pitch_factor']
    # audio_path = os.path.join(DOWNLOADS_DIR, f'{job_id}.mp3')
    
    #Check if file exists, otherwise download
    # if not os.path.exists(audio_path):
        # download_song_for_job(job_id, audio_path) # Implement this function
    
    #Adjust pitch
    # y, sr = librosa.load(audio_path)
    # y_shifted = pyrb.pitch_shift(y, sr, pitch_factor)
    # output_path = f'adjusted_{job_id}.wav'
    # sf.write(output_path, y_shifted, sr)
    # return send_file(output_path, as_attachment=True)


@app.route('/logout')
def logout():
    # Clear the session, effectively logging the user out of your application
    session.clear()
    # Redirect to homepage or login page after logout
    google_logout_url = 'https://accounts.google.com/Logout?continue=https://appengine.google.com/_ah/logout?continue=' + url_for('login', _external=True)

    # Redirect to Google logout URL
    return redirect(google_logout_url)
    #return redirect(url_for('login'))


# Add routes for login, logout, login callback as discussed earlier
print("Starting Flask application ****************************")
if __name__ == '__main__':
    
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=False)
    
