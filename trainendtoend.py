import runpod
import requests
import time
import json
import asyncio
import aiohttp
import boto3
import os
from botocore.exceptions import ClientError
import logging
from upload import download_from_do,upload_to_do,download_for_video,generate_presigned_url
import redis
from redis import Redis
from logging.handlers import RotatingFileHandler
from flask import Flask, session, redirect, url_for, request,render_template,flash,jsonify
from rq import get_current_job
from credit import get_user_credits,update_user_credits,use_credit
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from status import set_job_attributes,update_job_status,get_job_attributes,add_job_to_user_index,get_user_job_ids,update_job_progress,get_job_progress
from youtube import download_video_as_mp3
from myemail import send_email



import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
runpod.api_key =os.getenv("RUNPOD_KEY")
logging.basicConfig(level=logging.INFO)
#logger = logging.getLogger(__name__)
logger = logging.getLogger('my_app_logger')

# Get all my pods
#pods = runpod.get_pods()
#gpus=runpod.get_gpus();
#print(gpus)
# Get a specific pod
#pod = runpod.get_pod(pod.id)


app = Flask(__name__)

ACCESS_ID=os.getenv("ACCESS_ID")
SECRET_KEY=os.getenv("SECRET_KEY")

redis_host = os.getenv('REDIS_HOST', 'default_host')
redis_port = int(os.getenv('REDIS_PORT', 25061))  # Default Redis port
redis_username = os.getenv('REDIS_USERNAME', 'default')
redis_password = os.getenv('REDIS_PASSWORD', '')
infer_url= os.getenv('INFER_URL', '')
#redis_conn = Redis(host=redis_host, port=redis_port, username=redis_username, password=redis_password, ssl=True, ssl_cert_reqs=None)
redis_client = Redis(host=redis_host, port=redis_port, username=redis_username, password=redis_password, ssl=True, ssl_cert_reqs=None)

WORKER_COUNT_KEY = 'worker_count'
logger = logging.getLogger('my_app_logger')

env_vars = {
    "ACCESS_ID": ACCESS_ID,
    "SECRET_KEY": SECRET_KEY,
}






handler = RotatingFileHandler('app.log', maxBytes=10000, backupCount=3)
handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)

app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO)


def requests_retry_session(
    retries=5,
    backoff_factor=1,
    status_forcelist=(500, 502, 503, 504, 520, 521, 522, 523, 524),
    allowed_methods=('GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'HEAD'),
    session=None,
):
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        
        allowed_methods=allowed_methods,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def user_job_key(user_email,type_of_job):
    """Generate a Redis key based on user email."""
    return f"user_jobs_{type_of_job}:{user_email}"


#def update_job_status(job_id, status, user_email,type_of_job):
#    """Update the status of a user's job."""
#    user_key = user_job_key(user_email,type_of_job)
#    redis_client.hset(user_key, job_id, status)

def cleanup_job(job_id, user_email,type_of_job):
    """Remove a job from the user's map after completion."""
    user_key = user_job_key(user_email,type_of_job)
    redis_client.hdel(user_key, job_id)

def update_model_count(user_email,redis_client):
    
    user_data = redis_client.hgetall(f"user:{user_email}")
    if not user_data:
        return 'User not found'
    
    user_status_raw = user_data.get(b"status", b"trial")  # Redis returns bytes
    
    # Check for bytes type and decode if necessary
    user_status = user_status_raw.decode("utf-8") if isinstance(user_status_raw, bytes) else user_status_raw

    # Determine the model training limit based on user status
    model_training_limit = 3 if user_status == "premium" else 1
    
    models_trained = int(redis_client.hget(f"user:{user_email}", "models_trained") or 0)
    job = get_current_job()
    job_id = job.id
    
    
    redis_client.hincrby(f"user:{user_email}", "models_trained", 1)
    app.logger.info("update of model train done in queue")
    
    

def load_and_personalize_template(event_type, outcome, email,link):
    """Load and personalize the email template based on event type and outcome."""
    filename = f'email_templates/{event_type}_{outcome}.txt'
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            template = file.read()
            username = email.split('@')[0]  # Extract username from email
            personalized_content = template.format(username=username,link=link)
            return personalized_content
    except FileNotFoundError:
        return "Template file not found."





    
def terminate_pod(pod_id) :
    try:
        runpod.terminate_pod(pod_id)
        app.logger.info("deleted pod with id: {pod_id}")
    except Exception as e:
        app.logger.info("unable to delete pod with id:{pod_id}")


def create_pod_and_get_id1(name, image_name, gpu_models, ports, container_disk_in_gb, env_vars):
    """
    Attempts to create a pod with specified configurations, retrying with different GPU types. 
    If all attempts fail in 'SECURE' cloud type, retries with 'COMMUNITY' cloud type.

    :param name: Name of the pod.
    :param image_name: Name of the Docker image.
    :param gpu_models: List of GPU model names to try.
    :param ports: Port mappings.
    :param container_disk_in_gb: Disk size for the container.
    :param env_vars: Environment variables for the pod.
    :return: Pod ID if creation succeeds, None otherwise.
    """
    cloud_types = ["SECURE", "COMMUNITY"]
    
    for cloud_type in cloud_types:
        for gpu_model in gpu_models:
            try:
                logging.info(f"Attempting to create pod with {gpu_model} on {cloud_type} cloud.")
                pod = runpod.create_pod(name=name, image_name=image_name, gpu_type_id=gpu_model, cloud_type=cloud_type,
                                        ports=ports, container_disk_in_gb=container_disk_in_gb, env=env_vars)
                
                if pod and 'id' in pod:
                    logging.info(f"Pod created successfully: {pod['id']}")
                    return pod['id']
                else:
                    logging.error(f"Pod creation failed for {gpu_model} on {cloud_type} cloud. No ID returned.")
            except (ValueError, runpod.error.QueryError) as err:
                logging.error(f"Error creating pod with {gpu_model} on {cloud_type} cloud: {err}")
                # This exception block catches failures and logs them. The loop then continues to the next GPU model.
        
        logging.info(f"All GPU models tried in {cloud_type} cloud. Switching to next cloud type if available.")

    logging.error("Failed to create pod with any GPU model or cloud type.")
    return None





#Create a pod
def create_pod_and_get_id(name, image_name, gpu_type_id, ports, container_disk_in_gb, env_vars, cloud_type):
    try:
        
        pod = runpod.create_pod(name=name, image_name=image_name, gpu_type_id=gpu_type_id, cloud_type=cloud_type,
                                ports=ports, container_disk_in_gb=container_disk_in_gb, env=env_vars)
        
        pod_id = pod['id']
        print("Pod creation response:", pod)
        return pod_id
    except runpod.error.QueryError as err:
        print("Pod creation error:", err)
        print("Query:", err.query)
        return None





def check_pod_is_ready(pod_id):
    url = 'https://api.runpod.io/graphql?api_key={}'.format(runpod.api_key)
    
    headers = {'Content-Type': 'application/json'}
    data_template = """{
        "query": "query Pod { pod(input: {podId: \\"%s\\"}) { id name runtime { uptimeInSeconds ports { ip isIpPublic privatePort publicPort type } gpus { id gpuUtilPercent memoryUtilPercent } container { cpuPercent memoryPercent } } } }"
    }"""

    while True:
        # Replace %s in the data_template with the actual pod_id
        data = data_template % pod_id
        response = requests.post(url, headers=headers, data=data)
        response_data = response.json()
        if 'data' in response_data and 'pod' in response_data['data'] and response_data['data']['pod']:
            pod_info = response_data['data']['pod']
            if pod_info.get('runtime') and pod_info.get('runtime').get('uptimeInSeconds', 0) > 0:
                print(f"Pod {pod_id} is up and running.")
                app.logger.info(f"Pod {pod_id} is up and running.")
                break
            else:
                print(f"Waiting for pod {pod_id} to be ready...")
                app.logger.info(f"Waiting for pod {pod_id} to be ready...")
        else:
            print(f"Pod {pod_id} does not exist or information is not available.")
        
        time.sleep(10)  # Wait for 10 seconds before checking again
        # Check if pod details are present and if the pod is running



def check_file_in_space(access_id, secret_key, bucket_name, file_key, check_interval=60, timeout=2400):
    """
    Periodically checks for the existence of a file in a DigitalOcean Space.

    :param access_id: Your DigitalOcean Spaces access ID.
    :param secret_key: Your DigitalOcean Spaces secret key.
    :param bucket_name: The name of the Space.
    :param file_key: The key of the file in the Space.
    :param check_interval: How often to check for the file (in seconds).
    :param timeout: How long to keep checking before giving up (in seconds).
    """
    app.logger.info('entered funtion check file in space')
    session = boto3.session.Session()
    client = session.client('s3',
                            region_name='nyc3',
                            endpoint_url='https://nyc3.digitaloceanspaces.com',
                            aws_access_key_id=access_id,
                            aws_secret_access_key=secret_key)

    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            app.logger.info('checking presence of file in space')
            client.head_object(Bucket=bucket_name, Key=file_key)
            print(f"File {file_key} found in Space {bucket_name}.")
            return True
        except ClientError as e:
            error_code = int(e.response['Error']['Code'])
            if error_code == 404:
                
                print(f"File {file_key} not found in Space {bucket_name}. Checking again in {check_interval // 60} minutes.")
            else:
                print(f"Error checking file: {e}")
                return False
        time.sleep(check_interval)

    print("Timeout reached, file not found.")
    return False




async def upload_files_async(access_id, secret_key, url, model_name, bucket_name, file_path):
    """
    Asynchronously uploads a single file to a specified URL.
    """
    job = get_current_job()
    # Open the file in binary read mode
    with open(file_path, 'rb') as file:
        files = {'file': (file_path, file)}
        data = {'model_name': model_name}
        
        # Asynchronous POST request
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, data=data, timeout=180) as response:
                    response.raise_for_status()  # This will raise an exception for HTTP error codes
                    return True, "File uploaded successfully."
            except asyncio.TimeoutError:
                #update_job_status(job.id, "failed", user_email, 'train')
                return False, "Request timed out. Checking if file was processed..."
            except Exception as e:
                #update_job_status(job.id, "failed", user_email, 'train')
                return False, str(e)





def upload_files(access_id, secret_key, url, model_name, bucket_name, file_path):
    """
    Uploads a single file to a specified URL.

    :param url: The URL of the Flask endpoint.
    :param model_name: The name of the model to process the file.
    :param file_path: The file path of the audio file to upload.
    """
    # Open the file in binary read mode
    with open(file_path, 'rb') as file:
        files = {'file': file}
        
        # Include any additional data as a dictionary
        data = {'model_name': model_name}

        # Send a POST request to the server
        try:
            response = requests.post(url, files=files, data=data, timeout=600)
            response.raise_for_status()  # This will raise an exception for HTTP error codes
            return True, "File uploaded successfully."
        except requests.exceptions.RequestException as e:
            # This block will only execute for timeouts, indicating server-side processing time exceeded
            app.logger.info('timeout occured')
            print("Timeout occurred, checking file presence in cloud storage...")
            file_key = f'{model_name}.pth'
            file_exists = check_file_in_space(access_id, secret_key, bucket_name, file_key)
            if file_exists:
                app.logger.info('file found in space')
                return True, "Request timed out, but file was processed successfully."
            else:
                app.logger.info('file not found in space')
                return False, "Request timed out and file was not found in cloud storage."
            #check_file_in_space(access_id, secret_key, bucket_name, file_key) 
            #return False, "Request timed out. Checking if file was processed..."
        
# Ensure all file objects are properly closed after upload
def close_files(files):
    for _, file_obj in files:
        file_obj.close()

def add_model_to_user(user_email, model_name):
    redis_client.rpush(user_email, model_name)
    training_done_key = f"{user_email}:trained"
    redis_client.set(training_done_key, "true")

    
def convert_voice(filename, spk_id, user_email):
    """
    Synchronously uploads a file and handles voice conversion.

    :param file_path: The file path of the audio file to upload.
    :param spk_id: Speaker ID for voice transformation.
    :param user_email: User's email for job tracking.
    """
    #base_url = os.environ.get('INFER_URL')
    #url = f"{base_url}/convert_voice"
    logger.info("entered convert ")
    #app.logger.info(f'filepath where file saved initiallu=: {file_path1}')
    job = get_current_job()

    # Define user_key outside the try block to ensure it's available in the except block
    
    job_id = job.id if job else 'default_id'  # Fallback ID in case this runs outside a job context
     
    
    #directory, filename = os.path.split(file_path1)
    

# Generate the new file path with job_id as the filename, preserving the original extension
    
    new_filename = f"{job_id}{os.path.splitext(filename)[1]}"  # Preserves original file extension
    app.logger.error(f'new file name=: {new_filename}')
    #app.logger.error(f'directory=: {directory}')
    #file_path = os.path.join(directory, new_filename)
    #os.rename(file_path1, file_path)
    #app.logger.error(f'new file path=: {file_path}')
    

    try:
        file_path1 = download_from_do(filename)
        directory, filename1 = os.path.split(file_path1)
        file_path = os.path.join(directory, new_filename)
        app.logger.error(f'old filepath =: {file_path1}')
        app.logger.error(f'new filepath =: {file_path}')
        
        os.rename(file_path1, file_path)
        app.logger.error(f'new file path=: {file_path}')
        
        bucket_name = "sing"
        pod_id = create_pod_and_get_id("infer", "smjain/infer:v6", "NVIDIA RTX A4500", "5000/http", 20, env_vars,"SECURE")
        app.logger.info('After creating pod for training')

        if not pod_id:
            raise Exception("Failed to create the pod or retrieve the pod ID.")

        check_pod_is_ready(pod_id)
        
        app.logger.info('checked that pod is ready now')
        
        
        
        
        url = f'https://{pod_id}-5000.proxy.runpod.net/convert_voice'
        app.logger.info('before call to upload files for training done')

        time.sleep(20)
        
    # Open the file and prepare for the POST request
        with open(file_path, 'rb') as file:
            files = {'file': file}
            data = {'spk_id': spk_id, 'voice_transform': '0'}
            app.logger.info(f'Infer url: {url}')

            # Send the POST request within the with block to ensure file is open
            response = requests_retry_session().post(url, files=files, data=data, timeout=600)
            #response = requests.post(url, files=files, data=data, timeout=600)
            response.raise_for_status()  # Ensure HTTP errors are caught

        # Handle successful upload outside the with block
        
        
        update_job_status(redis_client,job_id,'finished')
        use_credit(user_email,'song')
        redis_client.decr(WORKER_COUNT_KEY)
        if pod_id:
            terminate_pod(pod_id)
        return True, "File uploaded successfully."

    except requests.exceptions.RequestException as e:
        # Handle specific request exceptions
        
        #app.logger.info('timeout occured')
        app.logger.info("Timeout occurred, checking file presence in cloud storage...")
        file_key = f'{job_id}.mp3'
        app.logger.info(f'file ={file_key}')
        
        
        app.logger.info(f'Upload failed: {e}')
        update_job_status(redis_client,job_id,'failed')
        redis_client.decr(WORKER_COUNT_KEY)
        
        if pod_id:
            terminate_pod(pod_id)
        return False, str(e)

    except Exception as e:
        # Handle other exceptions
        app.logger.info("error occured .now check file presence in space")
        file_key = f'{job_id}.mp3'
        app.logger.info(f'file ={file_key}')
        
        app.logger.error(f'Conversion failed: {e}')
        
        update_job_status(redis_client,job_id,'failed')
        redis_client.decr(WORKER_COUNT_KEY)
        if pod_id:
            terminate_pod(pod_id)
        return False, str(e)
 
    



def convert_voice_youtube(youtube_link, spk_id, user_email):
    """
    Synchronously uploads a file and handles voice conversion.

    :param file_path: The file path of the audio file to upload.
    :param spk_id: Speaker ID for voice transformation.
    :param user_email: User's email for job tracking.
    """
    UPLOAD_FOLDER = 'uploads'
    #base_url = os.environ.get('INFER_URL')
    #url = f"{base_url}/convert_voice"
    logger.info("entered convert ")
    #app.logger.info(f'filepath where file saved initiallu=: {file_path1}')
    job = get_current_job()

    # Define user_key outside the try block to ensure it's available in the except block
    
    job_id = job.id if job else 'default_id'  # Fallback ID in case this runs outside a job context
     
    
    #directory, filename = os.path.split(file_path1)
    

# Generate the new file path with job_id as the filename, preserving the original extension
    
    #new_filename = f"{job_id}{os.path.splitext(filename)[1]}"  # Preserves original file extension
    new_filename = f"{job_id}.mp3"

    app.logger.error(f'new file name=: {new_filename}')
    #app.logger.error(f'directory=: {directory}')
    file_path = os.path.join(UPLOAD_FOLDER, new_filename)
    #os.rename(file_path1, file_path)
    #app.logger.error(f'new file path=: {file_path}')
    
    gpu_models = [
    "NVIDIA RTX A4500",
    "NVIDIA RTX A5000",
    "NVIDIA RTX A6000",
    "NVIDIA RTX A4000",
    "NVIDIA RTX A3090",
    # Add more GPU models here as needed.
]
    

    try:
        
        
        
        
        #file_path1 = download_from_do(filename)
        #directory, filename1 = os.path.split(file_path1)
        app.logger.info(f'Before downloading audio from youtube to filepath={file_path}')
        
        
        
        
        download_video_as_mp3(youtube_link,file_path)
        app.logger.info(f'After downloading audio from youtube to filepath={file_path}')
        
        
        
        
        
        
        bucket_name = "sing"
        #def create_pod_and_get_id1(name, image_name, gpu_models, ports, container_disk_in_gb, env_vars):
        
        pod_id = create_pod_and_get_id1(name="infer", image_name="smjain/infer:v6", gpu_models=gpu_models, ports="5000/http", container_disk_in_gb=20, env_vars=env_vars)
        #pod_id = create_pod_and_get_id("infer", "smjain/infer:v6", "NVIDIA RTX A4500", "5000/http", 20, env_vars)
        update_job_progress(redis_client, job_id, 30)  # Progress updated to 10%
        app.logger.info('After creating pod for training')

        if not pod_id:
            raise Exception("Failed to create the pod or retrieve the pod ID.")

        check_pod_is_ready(pod_id)
        
        app.logger.info('checked that pod is ready now')
        update_job_progress(redis_client, job_id, 60)  # Progress updated to 10%
        
        
        
        url = f'https://{pod_id}-5000.proxy.runpod.net/convert_voice'
        app.logger.info('before call to upload files for training done')

        time.sleep(10)
        
    # Open the file and prepare for the POST request
        with open(file_path, 'rb') as file:
            files = {'file': file}
            data = {'spk_id': spk_id, 'voice_transform': '0'}
            app.logger.info(f'Infer url: {url}')

            # Send the POST request within the with block to ensure file is open
            response = requests_retry_session().post(url, files=files, data=data, timeout=600)
            #response = requests.post(url, files=files, data=data, timeout=600)
            response.raise_for_status()  # Ensure HTTP errors are caught

        # Handle successful upload outside the with block
        
        
        update_job_status(redis_client,job_id,'finished')
        update_job_progress(redis_client, job_id, 100)  # Progress updated to 10%
        redis_client.delete(f'{job_id}:progress')

        use_credit(user_email,'song')
        redis_client.decr(WORKER_COUNT_KEY)
        if pod_id:
            terminate_pod(pod_id)
            app.logger.info(f"email to be sent  for successful completion to {user_email}")
            
            send_email(user_email, 'song_conversion', 'success',object_name=new_filename,job_id=job_id)
            app.logger.info("email sent for successful completion")
            
        return True, "File uploaded successfully."

    except requests.exceptions.RequestException as e:
        # Handle specific request exceptions
        
        #app.logger.info('timeout occured')
        app.logger.info("Timeout occurred, checking file presence in cloud storage...")
        file_key = f'{job_id}.mp3'
        app.logger.info(f'file ={file_key}')
        
        
        app.logger.info(f'Upload failed: {e}')
        update_job_status(redis_client,job_id,'failed')
        update_job_progress(redis_client, job_id, 0)  # Progress updated to 10%
        redis_client.decr(WORKER_COUNT_KEY)
        redis_client.delete(f'{job_id}:progress')
        errorMessage=str(e)
        if pod_id:
            terminate_pod(pod_id)
            send_email(user_email, 'song_conversion', 'failure',object_name='',job_id=job_id,errorMessage=errorMessage)
        return False, str(e)

    except Exception as e:
        # Handle other exceptions
        app.logger.info("error occured .now check file presence in space")
        file_key = f'{job_id}.mp3'
        app.logger.info(f'file ={file_key}')
        
        app.logger.error(f'Conversion failed: {e}')
        errorMessage=str(e)
        update_job_status(redis_client,job_id,'failed')
        redis_client.decr(WORKER_COUNT_KEY)
        if pod_id:
            terminate_pod(pod_id)
            send_email(user_email,'song_conversion', 'failure',object_name='',job_id=job_id,errorMessage=errorMessage)
        return False, str(e)



   

def download_and_save_mp3(url,audio_id, save_path):
    """
    Downloads an MP3 file using the given 'audio_id' and saves it locally.

    :param base_url: The base URL for the GET request.
    :param audio_id: The unique identifier for the audio file to download.
    :param save_path: The local path where the MP3 file will be saved.
    """
    final_url = f'{url}/get_processed_audio/{audio_id}'
    app.logger.info(f'url for downloading converted file: {final_url}')
    response = requests.get(final_url, stream=True)
    if response.status_code == 200:
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=128):
                f.write(chunk)
        print(f"MP3 file downloaded and saved to {save_path}")
    else:
        print(f"Failed to download MP3 file. Status code: {response.status_code}")












import os
import subprocess
import magic
import uuid
from werkzeug.utils import secure_filename
import logging



from pydub import AudioSegment
import os
import logging  # Consider using the logging module

def analyze_audio_file1(file_path, max_size_bytes=10*1024*1024, max_duration_minutes=6, min_duration_minutes=2):
    """
    Analyzes an uploaded audio file for size, format, and duration.

    :param file_path: Path to the audio file.
    :param max_size_bytes: Maximum allowed file size in bytes.
    :param max_duration_minutes: Maximum allowed audio duration in minutes.
    :param min_duration_minutes: Minimum allowed audio duration in minutes.
    :return: A dictionary with success status, an error message if applicable, the audio duration in minutes, and a format check.
    """
    print("entered analyze audio")
    logging.info("entered audio analysis")  # Use logging.info instead of app.logger for a more general approach
    
    # Check if the file extension is .mp3
    if not file_path.lower().endswith('.mp3'):
        return {'success': False, 'error': 'Only MP3 files are allowed.', 'duration': None}
    logging.info("file check succeeded")
    
    try:
        # Check file size
        logging.info("entered try block")
        file_size = os.path.getsize(file_path)
        if file_size > max_size_bytes:
            return {'success': False, 'error': 'File size exceeds the allowed limit.', 'duration': None}
        
        # Load the audio file for processing
        logging.info("before reading")
        audio = AudioSegment.from_file(file_path)
        
        # Calculate audio length in minutes
        audio_length_minutes = len(audio) / 60000.0
        logging.info(f"audio length={audio_length_minutes}")
        
        # Check if the audio length exceeds the maximum duration
        if audio_length_minutes > max_duration_minutes:
            return {'success': False, 'error': 'Audio length exceeds the allowed maximum duration.', 'duration': audio_length_minutes}
        
        # Check if the audio length is below the minimum duration
        if audio_length_minutes < min_duration_minutes:
            return {'success': False, 'error': 'Audio length is below the allowed minimum duration.', 'duration': audio_length_minutes}
    
    except Exception as e:
        logging.error(f"error in file analysis={str(e)}")  # Use logging.error for error messages
        return {'success': False, 'error': f'Failed to process the audio file: {str(e)}', 'duration': None}
    
    # If all checks pass
    return {'success': True, 'error': None, 'duration': audio_length_minutes}



def convert_audio_to_mp3(filepath, upload_folder='/tmp'):
    """
    Checks the MIME type of the uploaded file and converts it to MP3 if necessary.
    Assumes the file is already downloaded from DigitalOcean Spaces to a local path.

    Args:
        filepath (str): The path to the file downloaded from DigitalOcean Spaces.
        upload_folder (str): The directory where the converted file will be saved.

    Returns:
        str: Path to the MP3 file or the original file.
    """
    # Ensure the upload folder exists
    os.makedirs(upload_folder, exist_ok=True)

    # Extract the filename from the filepath
    original_filename = os.path.basename(filepath)
    logging.info(f"Processing file: {original_filename}")

    # Use python-magic to identify the MIME type of the file
    mime_type = magic.from_file(filepath, mime=True)
    logging.info(f"File MIME type: {mime_type}")

    # Define the output path
    output_filename = original_filename.rsplit('.', 1)[0] + '.mp3'
    output_path = os.path.join(upload_folder, output_filename)

    # Check if the file is already in MP3 format or if it's a supported audio format for conversion
    if mime_type == 'audio/mpeg':
        logging.info("File is already an MP3, so no conversion needed.")
        return filepath
    elif mime_type in ['audio/wav', 'audio/webm', 'audio/ogg', 'video/webm', 'video/mp4']:
        logging.info("Converting to MP3...")
        # Convert to MP3 using FFmpeg
        command = ['ffmpeg', '-i', filepath, '-vn', '-ar', '44100', '-ac', '2', '-b:a', '192k', output_path]
        logging.info(f"Executing command: {' '.join(command)}")
        subprocess.run(command, check=True)
        
        # Cleanup the temporary original file if conversion was successful and if it's different from the output
        if filepath != output_path:
            os.remove(filepath)
        return output_path
    else:
        # Unsupported format, return the original file or handle accordingly
        logging.info("Unsupported file format for conversion.")
        return filepath














def train_model(file_name, model_name, user_email):
    job = get_current_job()
    job_id=job.id
    update_job_status(redis_client,job_id,'started')
    
    gpu_models = [
    "NVIDIA RTX A4500",
    "NVIDIA RTX A5000",
    "NVIDIA RTX A6000",
    "NVIDIA RTX A4000",
    "NVIDIA RTX A3090",
    # Add more GPU models here as needed.
]

    
    pod_id=''
    try:
        
        file_path = download_from_do(file_name)
        
        
        
        converted_path = convert_audio_to_mp3(file_path)
        
        app.logger.info(f"converted path={converted_path}")
        
        
        analysis_results = analyze_audio_file1(converted_path)
        app.logger.info("After analysing audio")
        if not analysis_results['success']:
            raise Exception("Audio analysis failed. either audio is too short in length or too large.")
    
        
        bucket_name = "sing"
        #pod_id = create_pod_and_get_id("train", "smjain/train:v7", "NVIDIA RTX A4500", "5000/http", 20, env_vars)
        pod_id = create_pod_and_get_id1(name="train", image_name="smjain/train:v7", gpu_models=gpu_models, ports="5000/http", container_disk_in_gb=20, env_vars=env_vars)
        
        #pod_id = create_pod_and_get_id("train", "smjain/train:v7", "NVIDIA RTX A4500", "5000/http", 20, env_vars,"SECURE")
        app.logger.info('After creating pod for training')

        if not pod_id:
            raise Exception("Failed to create the pod or retrieve the pod ID.")

        check_pod_is_ready(pod_id)
        app.logger.info('checked that pod is ready now')
        
        
        
        
        
        
        
        
        
        final_model_name = f"{user_email}_{model_name}"
        
        url = f'https://{pod_id}--5000.proxy.runpod.net/process_audio'
        app.logger.info('before call to upload files for training done')
        success, message = upload_files(ACCESS_ID, SECRET_KEY, url, final_model_name, bucket_name, converted_path)
        #success, message = asyncio.run(upload_files_async(ACCESS_ID, SECRET_KEY, url, final_model_name, bucket_name, file_path))
        if success:
            
            app.logger.info(f'Job {job.id} success during file upload: {message}')
            app.logger.info('file check done')
            #file_key = f'{model_name}.pth'
            #file_exists = check_file_in_space(ACCESS_ID, SECRET_KEY, bucket_name, file_key)
            terminate_pod(pod_id)
            add_model_to_user(user_email, model_name)
            app.logger.info('added model to user')
            use_credit(user_email,'model')
            app.logger.info('credit consumed')
            
            
            update_job_status(redis_client,job_id,'finished')
            app.logger.info('updated model state to finished')
            #use_credit(user_email,'model')
            app.logger.info('credit consumed')
            #push_model_to_infer(final_model_name)
            app.logger.info('pushed model to infer engine')
            redis_client.decr(WORKER_COUNT_KEY)
            send_email(user_email, 'model_training', 'success',job_id=job_id)
        # Proceed with additional job steps as needed
        else:
            app.logger.info('got false return from upload_files so setting job status fail')
            
            update_job_status(redis_client,job_id,'failed')
            redis_client.decr(WORKER_COUNT_KEY)
            send_email(user_email,'model_training', 'failure',job_id=job_id)
            if pod_id:
                terminate_pod(pod_id)
                
        
        
    except Exception as e:
        app.logger.error(f'Error during model training: {e}')
        errorMessage = str(e)
        update_job_status(redis_client,job_id,'failed')
        print(f"Operation failed: {e}")
        redis_client.decr(WORKER_COUNT_KEY)
        send_email(user_email, 'model_training', 'failure',job_id=job_id,errorMessage=errorMessage)
        if pod_id:
            terminate_pod(pod_id)
            


def generate_video_call(image_file_path, audio_file_path,audio_job_id, key,url):
    files = {
        'source_image': open(image_file_path, 'rb'),
        'audio_path': open(audio_file_path, 'rb'),
        # Uncomment the line below if you're including a reference video
        # 'ref_video_path': open(ref_video_file_path, 'rb'),
    }
    bucket_name = "sing"
    app.logger.info('sleep for 20 secs for pod to be warmed up')
    time.sleep(20)
    app.logger.info(f'now go for making a call at {url}')
    
    try:
        response = requests_retry_session().post(url, files=files, timeout=600)
        #response = requests.post(url, files=files, timeout=600)
        response.raise_for_status()  # This will raise an exception for HTTP error codes
        return True, "File uploaded successfully."
    except requests.exceptions.RequestException as e:
        # This block will only execute for timeouts, indicating server-side processing time exceeded
        app.logger.info(f'error occured{str(e)}')
        #print("Timeout occurred, checking file presence in cloud storage...")
        #file_key = f'{audio_job_id}.mp4'
        app.logger.info(f'start checking for file  {key}')
        file_exists = check_file_in_space(ACCESS_ID, SECRET_KEY, bucket_name, key)
        if file_exists:
            app.logger.info('file found in space')
            return True, "Request timed out, but file was processed successfully."
        else:
            app.logger.info('file not found in space')
            return False, "Request timed out and file was not found in cloud storage."


# Make a POST request to upload the files


def rename_file(current_file_path, new_file_name_without_extension):
    # Extract the directory path from the current file path
    directory = os.path.dirname(current_file_path)
    new_file_name_with_extension = f"{new_file_name_without_extension}.mp3"
    # Create the new file path with the new file name in the same directory
    new_file_path = os.path.join(directory, new_file_name_with_extension)
    
    # Rename the file
    os.rename(current_file_path, new_file_path)
    
    app.logger.info(f"File renamed to {new_file_path}")
    return new_file_path



def generate_video_job(source_image_path, job_id1,ref_video_path, audio_job_id,key,user_email):
    job = get_current_job()
    job_id=job.id
    
    update_job_status(redis_client,job_id,'started')

    try:
        bucket_name = "sing"
        pod_id = create_pod_and_get_id("video", "smjain/talker:v5", "NVIDIA RTX A4500", "5000/http", 20, env_vars)
        
        app.logger.info('After creating pod for training')

        if not pod_id:
            raise Exception("Failed to create the pod or retrieve the pod ID.")

        check_pod_is_ready(pod_id)
        app.logger.info('checked that pod is ready now')
        
        
        
        url = f'https://{pod_id}-5000.proxy.runpod.net/generate_video'
        app.logger.info('before call to upload files for training done')
        
        
        
        #def generate_video_call(source_image_path, audio_file_path,audio_job_id, url):
        job_id=job.id
        audio_file_path=download_for_video(job_id1)
        audio_file_path_new=rename_file(audio_file_path,job_id)
        app.logger.info(f"audio file path renamed={audio_file_path_new}")
        filename_without_extension = key
        new_key = f"{job_id}.mp4"
        
        success, message = generate_video_call(source_image_path,audio_file_path_new,audio_job_id,new_key,url)
        #success, message = asyncio.run(upload_files_async(ACCESS_ID, SECRET_KEY, url, final_model_name, bucket_name, file_path))
        if success:
            
            app.logger.info(f'Job {job.id} success during file upload: {message}')
            app.logger.info('file check done')
            #file_key = f'{model_name}.pth'
            #file_exists = check_file_in_space(ACCESS_ID, SECRET_KEY, bucket_name, file_key)
            terminate_pod(pod_id)
            #update_model_count(user_email, redis_client)
            
            update_job_status(redis_client,job_id,'finished')
            app.logger.info('updated model state to finished')
            use_credit(user_email,'video')
            redis_client.decr(WORKER_COUNT_KEY)
            #use_credit(user_email,'model')
            #app.logger.info('credit consumed')
            #push_model_to_infer(final_model_name)
            #app.logger.info('pushed model to infer engine')
        # Proceed with additional job steps as needed
        else:
            app.logger.info('got false return from upload_files so setting job status fail')
            
            update_job_status(redis_client,job_id,'failed')
            redis_client.decr(WORKER_COUNT_KEY)
            if pod_id:
                terminate_pod(pod_id)
        
        
    except Exception as e:
        app.logger.error(f'Error during video creation: {e}')
        
        update_job_status(redis_client,job_id,'failed')
        print(f"Operation failed: {e}")
        redis_client.decr(WORKER_COUNT_KEY)
        if pod_id:
            terminate_pod(pod_id)











def push_model_to_infer(model_name):
    # Step 1: Obtain the base URL from the environment variable
    base_url = os.environ.get('INFER_URL')
    if not base_url:
        print("INFER_URL environment variable is not set.")
        return
    
    # Step 2: Append model_name and .pth extension to the base URL
    model_url = f"{base_url}/download/{model_name}.pth"
    
    # Step 3: Make a GET request to the constructed URL
    try:
        response = requests.get(model_url)
        response.raise_for_status()  # Raises an exception for 4XX or 5XX status codes
        
        # Step 4: Print or process the response as needed
        print("Response Status Code:", response.status_code)
        print("Response Text:", response.text)
        app.logger.info(f'Response from  infer push:: {response.text}')
        
    except requests.RequestException as e:
        print(f"Request failed: {e}")
        app.logger.info('failed to send to infer')



    
    



