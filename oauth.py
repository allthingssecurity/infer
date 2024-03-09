from flask import Flask, redirect, url_for
from authlib.integrations.flask_client import OAuth

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Change this to a random secret key

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.getenv("CLIENT_ID",''),  # Replace with your Client ID
    client_secret=os.getenv("CLIENT_SECRET"),  # Replace with your Client Secret
    access_token_url='https://accounts.google.com/o/oauth2/token',
    access_token_params=None,
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    authorize_params=None,
    api_base_url='https://www.googleapis.com/oauth2/v1/',
    client_kwargs={'scope': 'openid profile email'},
)

@app.route('/')
def hello_world():
    return 'Hello, World!'

@app.route('/login')
def login():
    return google.authorize_redirect(redirect_uri=url_for('authorize', _external=True))

@app.route('/login/callback')
def authorize():
    token = google.authorize_access_token()
    user = google.parse_id_token(token)
    # At this point, user information is available, proceed accordingly
    return 'Login Successful'

if __name__ == '__main__':
    app.run(debug=True)
