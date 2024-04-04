from flask import Blueprint, request, jsonify, session,render_template,flash,jsonify,send_file
from functools import wraps
from redis import Redis
import os

admin_blueprint = Blueprint('admin', __name__)

redis_host = os.getenv('REDIS_HOST', 'default_host')
redis_port = int(os.getenv('REDIS_PORT', 25061))  # Default Redis port
redis_username = os.getenv('REDIS_USERNAME', 'default')
redis_password = os.getenv('REDIS_PASSWORD', '')
redis_client = Redis(host=redis_host, port=redis_port, username=redis_username, password=redis_password, ssl=True, ssl_cert_reqs=None)

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
    credits = request.json.get('credits')
    redis_client.hset(f"user:{user_email}", f"{activity}_credits", credits)
    return jsonify({"message": f"Credits added to {user_email}'s account."}), 200

@admin_blueprint.route('/admin/delete_all_jobs', methods=['POST'])
@admin_required
def delete_all_jobs():
    user_key = request.json.get('user_key')
    fields = redis_client.hkeys(user_key)
    if fields:
        redis_client.hdel(user_key, *fields)
        return jsonify({"message": f"All jobs for the user deleted successfully."}), 200
    else:
        return jsonify({"message": f"No jobs found for the user."}), 404

@admin_blueprint.route('/admin/move_to_approved', methods=['POST'])
@admin_required
def move_to_approved():
    user_email = request.json.get('user_email')
    redis_client.srem("waitlist_users", user_email)
    redis_client.sadd("approved_users", user_email)
    return jsonify({"message": f"User {user_email} moved from waitlist to approved."}), 200


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


@admin_blueprint.route('/admin/delete_user_jobs', methods=['POST'])
@admin_required
def delete_user_jobs():
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

