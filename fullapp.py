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
from werkzeug.utils import secure_filename
from multiprocessing import Process
from credit import get_user_credits,update_user_credits,use_credit,add_credits
from datetime import datetime
import requests
#import razorpay
#client = razorpay.Client(auth=("YOUR_API_KEY", "YOUR_API_SECRET"))

# Now you can use datetime in your code



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


q = Queue(connection=redis_client)
# Initialize Redis
FEATURE_FLAG_WAITLIST = True 

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
        create_user_account_if_not_exists(user_info['email'])
        # Perform any additional processing or actions as needed
        return render_template('join_waitlist.html')
    else:
        # Handle the case where the email is not available
        return redirect(url_for('login'))
    # Process user_info or perform actions such as logging in the user
    return render_template('join_waitlist.html')





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
    
    if not user_exists:
        # User does not exist, so initialize their account
        model_credits = 2
        song_credits = 5
        update_user_credits(user_email, "model", model_credits)
        update_user_credits(user_email, "song", song_credits)
        
        # Set the user exists key in Redis
        redis_client.set(user_exists_key, 1)
        
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
    model_credits=get_user_credits(user_email,'model')
    song_credits=get_user_credits(user_email,'song')
      # Adjust this function to your implementation
    return render_template('index.html', user_info=session, model_credits=model_credits, song_credits=song_credits)


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
        return render_template('convert.html', models=models,model_credits=model_credits,song_credits=song_credits)
    else:
        models = []
        model_credits=get_user_credits(user_email,'model')
        song_credits=get_user_credits(user_email,'song')
        return render_template('convert.html', models=models,model_credits=model_credits,song_credits=song_credits)
        
    

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
        
        return render_template('train.html',model_credits=model_credits,song_credits=song_credits)


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


        if 'file' not in request.files:
            return jsonify({'error': 'No file part'})
        file = request.files['file']
        speaker_name = request.form.get('spk_id', '')
        app.logger.info(f"enqueed the job for speaker {speaker_name} ")
        if file.filename == '':
            return jsonify({'error': 'No selected file'})
        app.logger.info("starting to infer")
        
        final_speaker_name=f'{user_email}_{speaker_name}'
        trained_model_key = f"{user_email}:trained"
        if not redis_client.exists(trained_model_key):
            # Model not trained for this speaker
            return jsonify({'error': 'Model is not yet trained for the specified speaker'})

        if file:
            filename = file.filename  # Original filename
            file_extension = os.path.splitext(filename)[1]  # Extracts file extension including the dot (.)
            new_filename = f"{uuid.uuid4()}{file_extension}"  # Generates a new filename with original extension
            filepath = os.path.join(UPLOAD_FOLDER, secure_filename(new_filename))
            file.save(filepath)
            app.logger.error(f'file saved with filepath =: {filepath}')
            # Adjusted to pass filepath and speaker_name to the main function
            app.logger.info("enqueed the job ")
            job = q.enqueue(convert_voice, filepath, final_speaker_name,user_email)
            job.meta['file_name'] = filename
            job.meta['submission_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            job.save_meta()  # Don't forget to save the metadata
            if user_email:
                # Update Redis with the new job ID and its initial status
                app.logger.info(f"updating redis for job id {job.id} ")
                user_key = user_job_key(user_email,'infer')
                redis_client.hset(user_key, job.id, "queued")  # Initial status is "queued"
                app.logger.info(f"updated redis for job id {job.id} ")
            p = Process(target=start_worker)
            p.start()     
            return jsonify({'message': 'File uploaded successfully for conversion', 'job_id': job.get_id()})
    else:
        app.logger.info(f"max song conversion exceeded for the user {user_email}. Buy credits")
        return jsonify({'message': 'You have reached max limits for song conversion. Buy credits '})


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


@app.route('/process_audio', methods=['POST'])
def process_audio():
    user_email = session.get('user_email')
    if is_feature_waitlist_enabled():
        if not is_user_authorized(user_email):
            if is_user_in_waitlist(user_email):
                return jsonify({'error': 'You are on the waitlist but not yet authorized. Please wait for authorization.'}), 403
            else:
                return jsonify({'error': 'You must join the waitlist to access this feature.'}), 403

    if has_active_jobs(user_email,'train'):
        app.logger.info(f"job already running for this user {user_email} ")
        return jsonify({'message': 'Cannot submit new job. A job is already queued or started'})
    
    credit_count=get_user_credits(user_email,'song')
    if (credit_count >0):
    
    
    
    

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
                
                timeout=2500  # Job-specific parameters like timeout
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


@app.route('/recharge')
@login_required
def recharge():
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
        
        return render_template('raz.html',model_credits=model_credits,song_credits=song_credits)



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
    
    file_name = job.meta.get('file_name', 'Unknown')  # Default to 'Unknown' if not set
    submission_time = job.meta.get('submission_time', 'Unknown')
    
    return jsonify({'status': job.get_status(), 'file_name': file_name, 'submission_time': submission_time})
    


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

@app.route('/update_payment', methods=['POST'])
@login_required
def update_payment():
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
