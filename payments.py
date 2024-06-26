from flask import Blueprint, request, jsonify, session,render_template,flash,jsonify,send_file
from flask import Flask, session, redirect, url_for, request,render_template,flash,jsonify,send_file
from functools import wraps
from redis import Redis
import os
import logging
import uuid
from rq import Worker, Queue, Connection
from redis import Redis
from upload import upload_to_do,download_from_do,download_from_do_with_job_id,download_for_video,generate_presigned_url
from werkzeug.utils import secure_filename
from multiprocessing import Process
from credit import get_user_credits,update_user_credits,use_credit,add_credits
from datetime import datetime
import requests
from pydub import AudioSegment
import io
from trainendtoend import train_model,convert_voice,generate_video_job,convert_voice_youtube
from status import set_job_attributes,update_job_status,get_job_attributes,add_job_to_user_index,get_user_job_ids,update_job_progress,get_job_progress,get_job_status,check_existing_jobs
from pydub import AudioSegment
import io
from rq.job import Job
from logging.handlers import RotatingFileHandler
import json
from datetime import datetime, timedelta
import time
from myemail import send_email
from cashfree_pg.models.create_order_request import CreateOrderRequest,OrderMeta
from cashfree_pg.api_client import Cashfree
from cashfree_pg.models.customer_details import CustomerDetails


app = Flask(__name__)
payment_blueprint = Blueprint('payment', __name__)

redis_host = os.getenv('REDIS_HOST', 'default_host')
redis_port = int(os.getenv('REDIS_PORT', 25061))  # Default Redis port
redis_username = os.getenv('REDIS_USERNAME', 'default')
redis_password = os.getenv('REDIS_PASSWORD', '')
redis_client = Redis(host=redis_host, port=redis_port, username=redis_username, password=redis_password, ssl=True, ssl_cert_reqs=None)

q = Queue(connection=redis_client)


Cashfree.XClientId = os.getenv('CASHFREE_CLIENT_ID', '')
Cashfree.XClientSecret = os.getenv('CASHFREE_CLIENT_SECRET', '')
Cashfree.XEnvironment = os.getenv('CASHFREE_ENVIRONMENT', '')

PAYMENT_URL=os.getenv('CASHFREE_LINK_URL','')

logger = logging.getLogger('my_app_logger')

handler = RotatingFileHandler('payments.log', maxBytes=10000, backupCount=3)
handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)

app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO)


def login_required(f):
    @wraps(f)  # Preserve the function name and docstring
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function



@payment_blueprint.route('/payment', methods=['GET'])
@login_required
def home():
    # Render a form to collect payment details
    return render_template('order_form.html')

@payment_blueprint.route('/payment/create_order', methods=['POST'])
@login_required
def create_order():
    try:
        #user_email = request.json.get('user_email')
        
        user_email = session.get('user_email')
        app.logger.info(f"user email={user_email}")
        amount = request.json['amount']
        phoneNumber = request.json['phoneNumber']
        orderType = request.json['orderType']
        
        app.logger.info(f"amount={amount},phoneNumber={phoneNumber},orderType={orderType}")
        link_id = f"order_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        app.logger.info(link_id)
        expiry_time = datetime.utcnow() + timedelta(minutes=10)
        link_expiry_time = expiry_time.isoformat() + 'Z'  # Append 'Z' to indicate UTC
        app.logger.info(link_expiry_time)
        url = PAYMENT_URL
        app.logger.info(f"url={url}")
        headers = {
            'accept': 'application/json',
            'content-type': 'application/json',
            'x-api-version': '2023-08-01',
            'x-client-id': Cashfree.XClientId,
            'x-client-secret': Cashfree.XClientSecret
        }
        data = {
            "customer_details": {"customer_phone": phoneNumber},
            "link_notify": {"send_sms": True},
            "link_id": link_id,
            "link_amount": amount,
            "link_currency": "INR",
            "link_purpose": orderType,
            "link_expiry_time": link_expiry_time 
        }

        response = requests.post(url, json=data, headers=headers)
        
        app.logger.info(url)
        if response.status_code == 200:
            response_data = response.json()
            code=response_data.get('link_qrcode', '')
            app.logger.info(f"code={code}")
            link_qrcode= response_data.get('link_qrcode', '')
            link_url=response_data.get('link_url', '')
            app.logger.info(f"link qr code={link_qrcode}")
            app.logger.info(f"link_url={link_url}")
            data_to_store = {
                "orderId": link_id,                
                "link_url": link_url,
                "link_qrcode" :link_qrcode,
                "link_amount": amount,
                "link_currency": "INR",
                "link_purpose": orderType,

                "success": True
            }
            app.logger.info("before dumping json")
            json_data_string = json.dumps(data_to_store)
            app.logger.info(json_data_string)
            
            key = f"{user_email}_paymentlink_{link_id}"
            
            app.logger.info("before  storing in redis")
            
            redis_client.hset(key, link_id, json_data_string)
    
            app.logger.info("after storing in redis")

    # Use the user_email and order_id as the key for the Redis hash
            
            
            
            
            return jsonify(data_to_store),200
            
            
            
            
            
        else:
            
            return jsonify({"error": "Failed to create order", "success": False}), 400

    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 500

@payment_blueprint.route('/payment/check_payment_status/<link_id>', methods=['GET'])
@login_required
def check_payment_status(link_id):
    url = f"{PAYMENT_URL}/{link_id}"
    app.logger.info("in check payment status")
    headers = {
        'accept': 'application/json',
        'x-api-version': '2023-08-01',
        'x-client-id': Cashfree.XClientId,
        'x-client-secret': Cashfree.XClientSecret
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        response_data = response.json()
        if response_data['link_status'] == 'PAID':
            return jsonify({'status': 'PAID'})
        else:
            return jsonify({'status': 'NOT_PAID'})
    return jsonify({'status': 'ERROR'})


@payment_blueprint.route('/payment/submit_payment_details', methods=['POST'])
@login_required
def submit_payment_details():
    # Retrieve JSON data from the request
    user_email = session.get('user_email')
    data = request.get_json()
    
    
    orderId = data['orderId']
    status = data['status']
    app.logger.info(f"orderId={orderId}")
    
    # Print the data received to the console (server-side)
    app.logger.info("Received payment details:", data)
    
    key_for_link = f"{user_email}_paymentlink_{orderId}"
    
    # Optionally, you can perform any processing here, such as updating a database
    # For now, we just return a success message
    if redis_client.exists(key_for_link):
        app.logger.info("found key")
        
        stored_data = redis_client.hget(key_for_link, orderId)
        if stored_data:
            stored_data = stored_data.decode('utf-8')  # Decode bytes to string if necessary
            stored_data = json.loads(stored_data)  # Convert JSON string back to dictionary
        else:
    # Handle the case where the key or field does not exist
            return jsonify({"error": "No data found for the provided link_id", "success": False}), 404
        
        
        
        app.logger.info(stored_data)
        # If payment is confirmed as 'PAID'
        if status == 'PAID':
            # You may want to store additional data such as payment status
            app.logger.info(f"successfully paid for user {user_email} with link {orderId}")
            orderType=stored_data['link_purpose']
            key_for_status = f"{user_email}_paymentstatus_{orderId}"
            amount=0
            
            try:
                # Try to convert amount to an integer, if it's not an integer already
                amount = int(stored_data['link_amount'])  # Default to 0 if not found
                app.logger.info(f"amount to be credited={amount}")
            except ValueError:
                # Handle the case where the amount is not convertible to integer
                return jsonify({"success": False, "message": "Amount coundnt be retrieved"}), 400
            credits=0
            if orderType == 'song':
                credits = amount // 20
            elif orderType == 'model':
                credits = amount // 50
            elif orderType == 'video':
                credits = amount // 25
            else:
                credits = 0  # Default case if the item_type is not recognized
            
            
            #calculate credits 
            
            add_credits(app,user_email,orderType,credits)
            

            app.logger.info(f"added credits={credits} for user {user_email}")

            
            
            
            status_data = {
                'status': status,
                'amount': stored_data['link_amount']  # Assume amount is part of stored data
            }
            redis_client.set(key_for_status, json.dumps(status_data))
        
        return jsonify({
            'success': True,
            'message': 'Payment details updated successfully.',
            'data': stored_data
        }), 200
    else:
        return jsonify({
            'success': False,
            'message': 'No payment link found for this order ID.'
        }), 404


@payment_blueprint.route('/payment/display_qr/<link_id>')
@login_required
def display_qr(link_id):
    print(f"entered display_qr with {link_id}")
    qr_code = request.args.get('qr_code', 'default_qr_code_if_none_provided')
    print(f"qr_code={qr_code}")
   
    return render_template('display_qr.html', link_qrcode=qr_code,order_id=link_id)


@payment_blueprint.route('/payment/cancel_payment/<link_id>', methods=['POST'])
@login_required
def cancel_payment(link_id):
    # Cashfree API endpoint to cancel a payment link
    url = f"{PAYMENT_URL}/{link_id}/cancel"

    # Headers including API credentials
    headers = {
        'accept': 'application/json',
        'x-api-version': '2023-08-01',
        'x-client-id': Cashfree.XClientId,
        'x-client-secret': Cashfree.XClientSecret
    }

    # Make the POST request to Cashfree
    response = requests.post(url, headers=headers)

    # Check if the cancellation was successful
    if response.status_code == 200:
        return jsonify({
            'success': True,
            'message': 'Payment link successfully cancelled.',
            'data': response.json()
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Failed to cancel payment link.',
            'statusCode': response.status_code,
            'error': response.json()
        })


