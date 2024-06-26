from flask import Blueprint, request, jsonify, session,render_template,flash,jsonify,send_file
from functools import wraps
from redis import Redis
import os

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


from datetime import datetime, timedelta
import time
from myemail import send_email

admin_blueprint = Blueprint('admin', __name__)

redis_host = os.getenv('REDIS_HOST', 'default_host')
redis_port = int(os.getenv('REDIS_PORT', 25061))  # Default Redis port
redis_username = os.getenv('REDIS_USERNAME', 'default')
redis_password = os.getenv('REDIS_PASSWORD', '')
redis_client = Redis(host=redis_host, port=redis_port, username=redis_username, password=redis_password, ssl=True, ssl_cert_reqs=None)

q = Queue(connection=redis_client)




# Custom decorator to check admin role
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_email = session.get('user_email')
        if not user_email:
            return jsonify({'error': 'User not signed in'}), 401
        user_role = redis_client.hget(f"user:{user_email}", "role")
        if user_role != b'admin':
            return jsonify({"message": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function
    
@admin_blueprint.route('/admin', methods=['GET'])
@admin_required
def admin_panel():
    return render_template('admin.html')

@admin_blueprint.route('/admin/delete_job', methods=['POST'])
@admin_required
def delete_job():
    user_key = request.json.get('user_key')
    job_id = request.json.get('job_id')
    delete_count = redis_client.hdel(user_key, job_id)
    if delete_count > 0:
        return jsonify({"message": f"Job {job_id} deleted successfully."}), 200
    else:
        return jsonify({"message": f"Job {job_id} was not found."}), 404

@admin_blueprint.route('/admin/check_waitlist', methods=['GET'])
@admin_required
def check_waitlist():
    waitlist_users = redis_client.smembers("waitlist_users")
    waitlist_users = [user.decode('utf-8') for user in waitlist_users]
    return jsonify({"waitlisted_users": waitlist_users}), 200


@admin_blueprint.route('/admin/add_credits', methods=['POST'])
@admin_required
def add_credits():
    user_email = request.json.get('user_email')
    activity = request.json.get('activity')
    new_credits = int(request.json.get('credits', 0))  # Ensure it's an int and provide a default

    # Key and field for Redis
    user_key = f"user:{user_email}"
    credits_field = f"{activity}_credits"

    # Fetch existing credits, if any
    existing_credits = redis_client.hget(user_key, credits_field)
    existing_credits = int(existing_credits) if existing_credits else 0

    # Calculate the total credits by adding new credits to existing ones
    total_credits = existing_credits + new_credits

    # Update the credits for the user and activity in Redis
    redis_client.hset(user_key, credits_field, total_credits)

    return jsonify({"message": f"Credits added to {user_email}'s account. Total {activity} credits: {total_credits}"}), 200


#@admin_blueprint.route('/admin/delete_all_jobs', methods=['POST'])
#@admin_required
#def delete_all_jobs():
 #   user_key = request.json.get('user_key')
  #  fields = redis_client.hkeys(user_key)
   # if fields:
    #    redis_client.hdel(user_key, *fields)
     #   return jsonify({"message": f"All jobs for the user deleted successfully."}), 200
    #else:
     #   return jsonify({"message": f"No jobs found for the user."}), 404

@admin_blueprint.route('/admin/move_to_approved', methods=['POST'])
@admin_required
def move_to_approved():
    user_email = request.json.get('user_email')
    redis_client.srem("waitlist_users", user_email)
    redis_client.sadd("authorized_users", user_email)
    send_email(user_email, 'added_to_approved', 'success')
    return jsonify({"message": f"User {user_email} moved from waitlist to approved."}), 200


@admin_blueprint.route('/admin/list_approved_users', methods=['GET'])
@admin_required
def list_approved_users():
    # Retrieve all members of the 'authorized_users' set from Redis
    approved_users = redis_client.smembers("authorized_users")

    # Convert the result from bytes to string if necessary
    approved_users = [user.decode('utf-8') for user in approved_users]

    return jsonify({"approved_users": approved_users}), 200


@admin_blueprint.route('/admin/move_to_waitlist_from_approved', methods=['POST'])
@admin_required
def move_to_waitlist_from_approved():
    user_email = request.json.get('user_email')
    redis_client.srem("authorized_users", user_email)
    redis_client.sadd("waitlist_users", user_email)
    
    return jsonify({"message": f"User {user_email} moved from approved to waitlist."}), 200


@admin_blueprint.route('/admin/remove_from_waitlist', methods=['POST'])
@admin_required
def remove_from_waitlist():
    user_email = request.json.get('user_email')
    redis_client.srem("waitlist_users", user_email)
    
    
    return jsonify({"message": f"User {user_email} moved from waitlist to removed."}), 200




@admin_blueprint.route('/admin/list_long_queued_jobs', methods=['GET'])
@admin_required
def list_long_queued_jobs():
    user_email = request.args.get('user_email')

    if not user_email:
        return jsonify({'error': 'User email is required'}), 400

    # Calculate the timestamp for 30 minutes ago
    thirty_minutes_ago_timestamp = (datetime.now() - timedelta(minutes=30)).timestamp()

    # Assuming job_types are known and static, if dynamic you'll need to adjust this
    job_types = ['infer', 'train', 'video']
    long_queued_jobs = []

    for job_type in job_types:
        redis_key = f'jobs:submission_times:{user_email}:{job_type}'
        # Retrieve job IDs queued before the timestamp for 30 minutes ago
        job_ids = redis_client.zrangebyscore(redis_key, '-inf', thirty_minutes_ago_timestamp)

        for job_id_bytes in job_ids:
            job_id = job_id_bytes.decode('utf-8')
            job_status = redis_client.hget(f"job:{job_id}", "status").decode('utf-8')

            if job_status == "queued":
                job_attributes = get_job_attributes(redis_client, job_id)  # Assumes this function exists
                long_queued_jobs.append(job_attributes)

    return jsonify({'long_queued_jobs': long_queued_jobs}), 200


@admin_blueprint.route('/admin/user_jobs', methods=['GET'])
@admin_required
def get_user_jobs():
    user_email = request.args.get('user_email')
    if not user_email:
        return jsonify({'error': 'User email is required'}), 400

    key = f"user_jobs:{user_email}"
    job_ids = redis_client.smembers(key)
    if not job_ids:
        return jsonify({'message': f"No jobs found for {user_email}"}), 404

    jobs_data = {}
    for job_id_bytes in job_ids:
        job_id = job_id_bytes.decode('utf-8')
        job_attributes = get_job_attributes(redis_client, job_id)
        if job_attributes:
            jobs_data[job_id] = job_attributes

    return jsonify({'jobs': jobs_data}), 200


@admin_blueprint.route('/admin/delete_user_jobs1', methods=['POST'])
@admin_required
def delete_user_jobs1():
    user_email = request.json.get('user_email')
    if not user_email:
        return jsonify({'error': 'User email is required'}), 400

    key = f"user_jobs:{user_email}"
    job_ids = redis_client.smembers(key)
    if not job_ids:
        return jsonify({'message': f"No jobs found for {user_email}"}), 404

    for job_id_bytes in job_ids:
        job_id = job_id_bytes.decode('utf-8')
        # Delete the job attributes
        redis_client.delete(f"job:{job_id}")
    
    # After deleting the jobs, clear the user's set of job IDs
    redis_client.delete(key)

    return jsonify({'message': f"All jobs for {user_email} deleted successfully."}), 200
    
    
@admin_blueprint.route('/admin/delete_user_jobs', methods=['POST'])
@admin_required
def delete_user_jobs():
    user_email = request.json.get('user_email')
    if not user_email:
        return jsonify({'error': 'User email is required'}), 400

    # Assume job types are predefined or retrieved from somewhere
    # If you have a set or list in Redis containing all job types for a user, fetch it here
    # For demonstration, using a static list of job types
    job_types = ['infer', 'train', 'video']  # Example job types

    key = f"user_jobs:{user_email}"
    job_ids = redis_client.smembers(key)
    if not job_ids:
        return jsonify({'message': f"No jobs found for {user_email}"}), 404

    for job_id_bytes in job_ids:
        job_id = job_id_bytes.decode('utf-8')
        # Delete the job attributes
        redis_client.delete(f"job:{job_id}")

        # Additional step: Remove job ID from each job type's sorted set
        for job_type in job_types:
            submission_times_key = f'jobs:submission_times:{user_email}:{job_type}'
            redis_client.zrem(submission_times_key, job_id)
    
    # After deleting the jobs and removing them from the sorted sets, clear the user's set of job IDs
    redis_client.delete(key)

    return jsonify({'message': f"All jobs for {user_email} deleted successfully."}), 200

@admin_blueprint.route('/admin/delete_specific_job', methods=['POST'])
@admin_required
def delete_specific_job():
    # Extract the job ID from the POST request's JSON payload
    data = request.get_json()
    job_id = data.get('job_id')
    
    if not job_id:
        return jsonify({'error': 'Job ID is required'}), 400

    # Attempt to delete the job by its ID
    deleted_count = redis_client.delete(f"job:{job_id}")
    
    if deleted_count == 0:
        return jsonify({'error': f"Job {job_id} not found."}), 404

    return jsonify({'message': f"Job {job_id} deleted successfully."}), 200




def get_job_attributes(redis_client, job_id):
    """
    Retrieves job attributes from Redis using the job_id.
    
    :param redis_client: Redis connection object.
    :param job_id: The unique ID of the job.
    :return: Dictionary of the job attributes, or None if not found.
    """
    key = f"job:{job_id}"
    attributes = redis_client.hgetall(key)
    if not attributes:
        return None  # Return None if the job doesn't exist
    
    return {k.decode('utf-8'): v.decode('utf-8') for k, v in attributes.items()}
    

@admin_blueprint.route('/admin/add_name_to_user', methods=['POST'])
@admin_required
def add_name_to_user():
    # Extract 'user_email' and 'name' from the POST request's body
    data = request.get_json()
    user_email = data.get('user_email')
    name = data.get('name')

    if not user_email or not name:
        return jsonify({'error': 'Missing user_email or name'}), 400

    # Use Redis's rpush to add the name to the list associated with the user's email
    redis_client.rpush(user_email, name)

    return jsonify({'message': f"Name {name} added to {user_email}."}), 200


@admin_blueprint.route('/admin/remove_name_from_user', methods=['POST'])
@admin_required
def remove_name_from_user():
    # Extract 'user_email' and 'name' from the POST request's body
    data = request.get_json()
    user_email = data.get('user_email')
    name = data.get('name')

    if not user_email or not name:
        return jsonify({'error': 'Missing user_email or name'}), 400

    # Use Redis's LREM to remove the name from the list associated with the user's email
    removed_count = redis_client.lrem(user_email, 0, name)

    if removed_count > 0:
        return jsonify({'message': f"Name {name} removed from {user_email}."}), 200
    else:
        return jsonify({'error': f"Name {name} not found in {user_email}."}), 404




@admin_blueprint.route('/admin/user_jobs_attributes', methods=['GET'])
@admin_required
def user_jobs_attributes():
    user_email = request.args.get('user_email')
    selected_job_type = request.args.get('job_type')
    
    if not user_email or not selected_job_type:
        return jsonify({'error': 'Missing user_email or job_type parameters'}), 400
    
    redis_key = f'jobs:submission_times:{user_email}:{selected_job_type}'
    # Retrieve top 5 job IDs for the specified user and job type
    job_ids = redis_client.zrevrange(redis_key, 0, 4)

    if not job_ids:
        return jsonify({'error': f'No jobs found for {user_email} with job type {selected_job_type}.'}), 404
    
    jobs_data = {}
    for job_id_bytes in job_ids:
        job_id = job_id_bytes.decode('utf-8')
        job_attributes = get_job_attributes(redis_client, job_id)
        if job_attributes:
            jobs_data[job_id] = job_attributes
    
    return jsonify({'jobs': jobs_data}), 200



@admin_blueprint.route('/admin/retrigger_job', methods=['POST'])
@admin_required
def admin_retrigger_job():
    # Admin authentication (adjust according to your auth system)

    # Extracting user email and filename from the request
 
    data = request.get_json()  # Get data as JSON
    user_email = data.get('user_email')
    filename = data.get('filename')
    model_name = data.get('model_name', 'default_model')

 
    if not user_email or not filename:
        return jsonify({'error': 'Missing user email or filename'}), 400

    # Construct the ` for the existing file in Digital Ocean Spaces
    # Assuming files are named after the secure_filename and stored in a known UPLOAD_FOLDER
    secure_filename = filename  # If filename is already the secure filename
    #filepath = os.path.join(UPLOAD_FOLDER, secure_filename)

    # Here, instead of saving and uploading the file again, use the existing file's path
    # since the file is already in Digital Ocean Spaces

    # Enqueue the job for processing with the provided details
    job = q.enqueue_call(func=train_model, args=(secure_filename, model_name, user_email), timeout=2500)
    job_id = job.get_id()

    # Log the job submission for the user
    submission_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    attributes = {
        "type": 'train',  # Assuming the job type
        "filename": secure_filename,
        "submission_time": submission_time,
    }
    set_job_attributes(redis_client, job_id, attributes)
    update_job_status(redis_client, job_id, 'queued')
    add_job_to_user_index(redis_client, user_email, job_id)

    # Optionally, if your system tracks job submissions by timestamp
    submission_datetime = datetime.strptime(submission_time, '%Y-%m-%d %H:%M:%S')
    submission_timestamp = submission_datetime.timestamp()
    redis_key = f'jobs:submission_times:{user_email}:train'
    redis_client.zadd(redis_key, {job_id: submission_timestamp})

    return jsonify({'message': 'Job re-triggered for user.', 'job_id': job_id}), 200
    


@admin_blueprint.route('/admin/retry_infer', methods=['POST'])
@admin_required  # Assuming this decorator checks for admin privileges as well
def admin_retry_infer():
    
    # Extracting parameters from JSON request
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    user_email = data.get('user_email')
    speaker_name = data.get('spk_id', '')
    youtube_link = data.get('youtube_link', '')

    if not all([user_email, speaker_name, youtube_link]):
        return jsonify({'error': 'Missing required parameters (user_email, spk_id, youtube_link)'}), 400

    

    credit_count = get_user_credits(user_email, 'song')
    if credit_count > 0:
        final_speaker_name = f'{user_email}_{speaker_name}'
        trained_model_key = f"{user_email}:trained"
        
        if not redis_client.exists(trained_model_key):
            return jsonify({'error': 'Model is not yet trained for the specified speaker'})

        if not youtube_link.strip():
            return jsonify({'error': 'YouTube link is required'}), 400

        job = q.enqueue_call(
            func=convert_voice_youtube,
            args=(youtube_link, final_speaker_name, user_email),
            timeout=2500
        )
       

        submission_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        submission_timestamp = datetime.strptime(submission_time, '%Y-%m-%d %H:%M:%S').timestamp()
        
        attributes = {
            "type": "infer",
            "filename": youtube_link,
            "user_email": user_email,
            "spk_id": speaker_name ,
            "submission_time": submission_time,
        }

        # Set job attributes in Redis
        set_job_attributes(redis_client, job.get_id(), attributes)

        # Update job status and initial progress
        update_job_status(redis_client, job.get_id(), 'queued')
        update_job_progress(redis_client, job.get_id(), 10)  # Progress updated to 10%

        # Log and store the submission timestamp in a sorted set
        redis_key = f'jobs:submission_times:{user_email}:infer'
        redis_client.zadd(redis_key, {job.get_id(): submission_timestamp})
        
        

        return jsonify({'message': 'Job submitted successfully by admin', 'job_id': job.get_id()})
    else:
        
        return jsonify({'message': 'User has reached the limit for song conversions. Buy more credits.'})
