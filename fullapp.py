from flask import Flask, session, redirect, url_for, request,render_template,flash
from authlib.integrations.flask_client import OAuth
import redis
from redis import Redis
from rq import Queue
import os
import time
from functools import wraps
from authlib.integrations.flask_client import OAuth
from flask_session import Session
import base64
from flask import request
import logging
from logging.handlers import RotatingFileHandler


app = Flask(__name__)
app.secret_key = 'your_secret_key'

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
        return 'Authorization successful'
    else:
        # Handle the case where the email is not available
        return 'Email not found in user info'
    # Process user_info or perform actions such as logging in the user
    return 'Authorization successful'



# Middleware or decorator to check if user is logged in
def login_required(f):
    @wraps(f)  # Preserve the function name and docstring
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


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
    return google.authorize_redirect(redirect_uri, nonce=nonce)


    
@app.route('/')
def index():
    print ("helllllllllllllllllllo")
    if 'logged_in' in session and session['logged_in']:
        return render_template('index.html')
    else:
        print ("redirecting to ",url_for('login'))
        return redirect(url_for('login'))

@app.route('/song_conversion')
def song_conversion():
    if 'logged_in' in session and session['logged_in']:
        return render_template('convert.html')
    else:
        return redirect(url_for('login'))


@app.route('/models')
@login_required
def models():
    # Check user's model count from Redis and render accordingly
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

    user_email = session.get('user_email')
    user_data = redis_client.hgetall(f"user:{user_email}")
    user_status_raw = user_data.get(b"status", b"trial")  # Redis returns bytes

    # Check for bytes type and decode if necessary
    user_status = user_status_raw.decode("utf-8") if isinstance(user_status_raw, bytes) else user_status_raw

    # Determine the model limit based on user status
    model_limit = 4 if user_status == "premium" else 2
    
    models_trained = int(redis_client.hget(f"user:{user_email}", "models_trained") or 0)
    
    if models_trained >= model_limit:
        return f"Model training limit of {model_limit} reached. Upgrade for more."
    
    # If under limit, proceed with model training
    result = dummy_model_training()
    
    # Update Redis to reflect the new model count
    redis_client.hincrby(f"user:{user_email}", "models_trained", 1)
    
    models_trained = redis_client.hget(f"user:{user_email}", "models_trained")
    if models_trained is None:
        models_trained = 0
    else:
        models_trained = int(models_trained)

    print(f"Models trained for {user_email}: {models_trained}")  # Debugging line
    
    return f"Model training successful. {result}"



@app.route('/song_conversion_submit')
@login_required
def song_conversion_submit():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    user_email = session.get('user_email')
    user_data = redis_client.hgetall(f"user:{user_email}")
    user_status_raw = user_data.get(b"status", b"trial")  # Redis returns bytes

    # Check for bytes type and decode if necessary
    user_status = user_status_raw.decode("utf-8") if isinstance(user_status_raw, bytes) else user_status_raw

    # Determine the model limit based on user status
    song_limit = 4 if user_status == "premium" else 2
    
    songs_converted = int(redis_client.hget(f"user:{user_email}", "songs_converted") or 0)
    recharge_balance = int(redis_conn.hget(f"user:{user_email}", "recharge_balance") or 0)
    
    
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
