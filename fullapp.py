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

app = Flask(__name__)




app.secret_key = os.urandom(16)

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id='158446367723-fie5o9bjnn20ik2c68h06fjd2ran8fdo.apps.googleusercontent.com',
    client_secret='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',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile',
    }
)



# Initialize Flask-Session
Session(app)



# Initialize Redis



def generate_nonce(length=32):
    return base64.urlsafe_b64encode(os.urandom(length)).rstrip(b'=').decode('ascii')

# Setup OAuth and Google configuration as before
@app.route('/login/callback')
def authorize():
    # The code to handle the callback and authorization logic goes here
    print("Request URL:", request.url)
    print("Query Parameters:", request.args)
    token = google.authorize_access_token()
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





@app.route('/login')
def login():
    # Generate a nonce and save it in the session
    print("Accessed the login endpoint")
    nonce = generate_nonce()
    session['oauth_nonce'] = nonce
    
    # Include the nonce in your authorization request
    redirect_uri = url_for('authorize', _external=True)
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



# Add routes for login, logout, login callback as discussed earlier
print("Starting Flask application ****************************")
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=False)
