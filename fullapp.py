from flask import Flask, session, redirect, url_for, request,render_template,flash,jsonify,send_file
from authlib.integrations.flask_client import OAuth
import redis
from redis import Redis
import os
import time
from functools import wraps
from authlib.integrations.flask_client import OAuth
from flask_session import Session
import base64
from flask import request
import logging
from logging.handlers import RotatingFileHandler
from trainendtoend import main,convert_voice
import os
import uuid
from rq import Worker, Queue, Connection
from redis import Redis
from upload import upload_to_do,download_from_do

from multiprocessing import Process


app = Flask(__name__)
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

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

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


q = Queue(connection=redis_client)
# Initialize Redis


def login_required(f):
    @wraps(f)  # Preserve the function name and docstring
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


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
    print(user_info['email'])
    if 'email' in user_info:
        session['user_email'] = user_info['email']
        session['logged_in'] = True
        # Perform any additional processing or actions as needed
        return render_template('index.html')
    else:
        # Handle the case where the email is not available
        return redirect(url_for('login'))
    # Process user_info or perform actions such as logging in the user
    return render_template('index.html')



# Middleware or decorator to check if user is logged in


@app.route('/get-jobs')
@login_required
def get_jobs():
    
    user_email = session['user_email']
    training_jobs_key = user_job_key(user_email, 'train')
    inference_jobs_key = user_job_key(user_email, 'infer')
    training_jobs = redis_client.hgetall(training_jobs_key)
    inference_jobs = redis_client.hgetall(inference_jobs_key)
    formatted_training_jobs = {key.decode('utf-8'): value.decode('utf-8') for key, value in training_jobs.items()}
    formatted_inference_jobs = {key.decode('utf-8'): value.decode('utf-8') for key, value in inference_jobs.items()}
    return render_template('job-tracking.html', training_jobs=formatted_training_jobs, inference_jobs=formatted_inference_jobs)


def create_user_account_if_not_exists(user_email, initial_tier="trial"):
    """
    Create a new user account with the given tier, only if it doesn't already exist.
    """
    user_key = f"user:{user_email}"
    # Check if the user already has a tier set
    if not redis_client.hexists(user_key, "tier"):
        # Account does not exist, so create it with initial values
        app.logger.info(f'account doesnt exist in redis for user {user_email}')
        redis_client.hset(user_key, mapping={"tier": initial_tier, "models_trained": 0})
        app.logger.info(f'account created in redis for user {user_email}')
        print(f"Account created for {user_email} with {initial_tier} tier.")
    else:
        # Account already exists, skip creation
        print(f"Account for {user_email} already exists. Skipping creation.")

def get_user_tier(user_email):
    """
    Retrieve the current tier of the user.
    """
    app.logger.info(f'check user existence {user_email}')
    return redis_client.hget(f"user:{user_email}", "tier").decode("utf-8")

def update_user_tier(user_email, new_tier):
    """
    Update the user's tier to a new value (e.g., upgrading to premium).
    """
    redis_client.hset(f"user:{user_email}", "tier", new_tier)

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
    if 'logged_in' in session and session['logged_in']:
        user_info = {
            'name': session.get('user_name', 'Unknown'),  # Assuming you've stored the user's name here
            'picture': session.get('user_picture', '')   # Assuming you've stored the profile picture URL here
        }
        user_email = session.get('user_email')
        app.logger.info(f'creating account in redis for user {user_email}')
        create_user_account_if_not_exists(user_email)
        app.logger.info(f'account created in redis for user {user_email}')
        return render_template('index.html', user_info=user_info)
    else:
        return redirect(url_for('login'))

@app.route('/song_conversion')
@login_required
def song_conversion():
    
    user_email = session.get('user_email')
    if user_email:
        models = redis_client.lrange(user_email, 0, -1)  # Get list of models
        models = [model.decode('utf-8') for model in models]
    else:
        models = []
    return render_template('convert.html', models=models)
        
    

@app.route('/models')
@login_required
def models():
    # Check user's model count from Redis and render accordingly
    user_email = session.get('user_email')  # Assuming current_user has an email attribute
    models = redis_client.lrange(user_email, 0, -1) # Assuming set usage; adapt if using lists
    models = [model.decode('utf-8') for model in models]
    return render_template('models.html', models=models)
    pass

@app.route('/deploy_model')
@login_required
def deploy_model(model_name):
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

@app.route('/train')
@login_required
def train():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    else:
        
        
        return render_template('train.html')


@app.route('/infer')
@login_required
def infer():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    else:
        user_email = session.get('user_email')
        
        return render_template('infer.html', user_email=user_email)




@app.route('/start_infer', methods=['POST'])
@login_required
def start_infer():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'})
    file = request.files['file']
    speaker_name = request.form.get('spk_id', '')
    app.logger.info(f"enqueed the job for speaker {speaker_name} ")
    if file.filename == '':
        return jsonify({'error': 'No selected file'})
    app.logger.info("starting to infer")
    user_email = session.get('user_email')
    final_speaker_name=f'{user_email}_{speaker_name}'
    trained_model_key = f"{user_email}:trained"
    if not redis_client.exists(trained_model_key):
        # Model not trained for this speaker
        return jsonify({'error': 'Model is not yet trained for the specified speaker'})

    if file:
        filename = uuid.uuid4().hex + '_' + file.filename
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        print(filepath)
        # Adjusted to pass filepath and speaker_name to the main function
        app.logger.info("enqueed the job ")
        job = q.enqueue(convert_voice, filepath, final_speaker_name)
        if user_email:
            # Update Redis with the new job ID and its initial status
            app.logger.info(f"updating redis for job id {job.id} ")
            user_key = user_job_key(user_email,'infer')
            redis_client.hset(user_key, job.id, "queued")  # Initial status is "queued"
            app.logger.info(f"updated redis for job id {job.id} ")
        p = Process(target=start_worker)
        p.start()     
        return jsonify({'message': 'File uploaded successfully for conversion', 'job_id': job.get_id()})


@app.route('/download/<job_id>')
@login_required
def download(job_id):
    # Here, you would determine the file_key from the job_id
    # For this example, let's assume they are the same
    file_key = job_id
    
    # Call the download function
    local_file_path = download_from_do(file_key)
    
    if local_file_path:
        return send_file(local_file_path, as_attachment=True)
    else:
        return "Download failed", 404


def user_job_key(user_email,type_of_job):
    """Generate a Redis key based on user email."""
    return f"user_jobs_{type_of_job}:{user_email}"


@app.route('/process_audio', methods=['POST'])
def process_audio():
    user_email = session.get('user_email')
    
    if has_active_jobs(user_email,'train'):
        app.logger.info(f"job already running for this user {user_email} ")
        return jsonify({'message': 'Cannot submit new job. A job is already queued or started'})
    
    user_tier = get_user_tier(user_email)
    current_count = int(redis_client.hget(f"user:{user_email}", "models_trained"))
    tier_limits = {"trial": 2, "premium": 4}
    if current_count < tier_limits[user_tier]:
    
    
    
    

        if 'file' not in request.files:
            return jsonify({'error': 'No file part'})
        file = request.files['file']
        model_name = request.form.get('model_name', '')
        if file.filename == '':
            return jsonify({'error': 'No selected file'})
        if file:
            filename = uuid.uuid4().hex + '_' + file.filename
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            
            print(filepath)
            response = upload_to_do(filepath)
            user_email = session.get('user_email')
            # Adjusted to pass filepath and speaker_name to the main function
            job = q.enqueue_call(
                func=main, 
                args=(filename, model_name,user_email),  # Positional arguments for my_function
                
                timeout=1500  # Job-specific parameters like timeout
        )

            if user_email:
            # Update Redis with the new job ID and its initial status
                user_key = user_job_key(user_email,'train')
                redis_client.hset(user_key, job.id, "queued")  # Initial status is "queued"
            #job = q.enqueue(main, filename, model_name)
            p = Process(target=start_worker)
            p.start()     
            return jsonify({'message': 'Model Training Job Started with ', 'job_id': job.get_id()})
    else:
        app.logger.info(f"max train jobs exceeded for the user {user_email} ")
        return jsonify({'message': 'You have reached max limits '})
def start_worker():
    # Fetch the current number of workers
    current_worker_count = int(redis_client.get(WORKER_COUNT_KEY) or 0)
    
    if current_worker_count < MAX_WORKERS:
        # Increment the worker count atomically
        redis_client.incr(WORKER_COUNT_KEY)
        
        try:
            queues_to_listen = ['default']
            with Connection(redis_client):
                worker = Worker(map(Queue, queues_to_listen))
                worker.work()
        finally:
            # Ensure the worker count is decremented when the worker stops working
            redis_client.decr(WORKER_COUNT_KEY)
    else:
        print("Maximum number of workers reached. Not starting a new worker.")






@app.route('/song_conversion_submit')
@login_required
def song_conversion_submit():
    
    user_email = session.get('user_email')
    user_data = redis_client.hgetall(f"user:{user_email}")
    user_status_raw = user_data.get(b"status", b"trial")  # Redis returns bytes

    # Check for bytes type and decode if necessary
    user_status = user_status_raw.decode("utf-8") if isinstance(user_status_raw, bytes) else user_status_raw

    # Determine the model limit based on user status
    song_limit = 4 if user_status == "premium" else 2
    
    songs_converted = int(redis_client.hget(f"user:{user_email}", "songs_converted") or 0)
    recharge_balance = int(redis_client.hget(f"user:{user_email}", "recharge_balance") or 0)
    
    
    if user_status == 'premium':
        if recharge_balance > 0:
            # For premium users with enough recharge balance
            result = dummy_song_converted()
            redis_client.hincrby(f"user:{user_email}", "recharge_balance", -1)
        elif song_conversions < 2:
            # Allow up to 2 free conversions for premium users without balance
            result = dummy_song_converted()
            redis_client.hincrby(f"user:{user_email}", "songs_converted", 1)
        else:
            return jsonify({'error': 'No more free conversions available'}), 403
    elif song_conversions < song_limit:
        # Allow free users up to 2 conversions
        result = dummy_song_converted()
        redis_client.hincrby(f"user:{user_email}", "songs_converted", 1)
    else:
        return jsonify({'error': 'Upgrade to premium for more conversions'}), 403
    
    
    
    
    
    
    # If under limit, proceed with model training
    
    
    # Update Redis to reflect the new model count
    

    print(f"Song converted for {user_email}: {songs_converted}")  # Debugging line
    
    return f"Song converted successful. {result}"

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

@app.route('/process-recharge', methods=['POST'])
@login_required
def process_recharge():
    user_email = session.get('user_email')

    if not user_email:
        return "User not logged in.", 403

    # Check if the user is a premium user
    user_status = redis_client.hget(f"user:{user_email}", "status").decode('utf-8')
    if user_status != 'premium':
        return jsonify({'error': 'Only premium users can recharge'}), 403

    amount = request.form.get('amount')

    if amount:
        # In a real app, you would process the payment details with a payment gateway
        # Simulate successful payment by updating the user's recharge balance
        current_balance = int(redis_client.hget(f"user:{user_email}", "recharge_balance") or 0)
        new_balance = current_balance + int(amount)
        redis_client.hset(f"user:{user_email}", "recharge_balance", new_balance)

        return jsonify({'message': 'Recharge successful, new balance: ' + str(new_balance) + ' credits.'})
    else:
        return "Invalid request", 400



@app.route('/samples')
@login_required
def samples():
    # Display sample conversions
    pass

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
    return jsonify({'status': job.get_status(), 'job_id': job_id})


@app.route('/logout')
def logout():
    # Clear the session, effectively logging the user out of your application
    session.clear()
    # Redirect to homepage or login page after logout
    return redirect(url_for('login'))


# Add routes for login, logout, login callback as discussed earlier
print("Starting Flask application ****************************")
if __name__ == '__main__':
    handler = RotatingFileHandler('app.log', maxBytes=10000, backupCount=3)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=False)
