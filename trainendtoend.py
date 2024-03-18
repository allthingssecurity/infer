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
from upload import download_from_do,upload_to_do
import redis
from redis import Redis
from logging.handlers import RotatingFileHandler
from flask import Flask, session, redirect, url_for, request,render_template,flash,jsonify
from rq import get_current_job
from credit import get_user_credits,update_user_credits,use_credit

runpod.api_key =os.getenv("RUNPOD_KEY")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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


env_vars = {
    "ACCESS_ID": ACCESS_ID,
    "SECRET_KEY": SECRET_KEY,
}


handler = RotatingFileHandler('train.log', maxBytes=10000, backupCount=3)
handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)

app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO)

def user_job_key(user_email,type_of_job):
    """Generate a Redis key based on user email."""
    return f"user_jobs_{type_of_job}:{user_email}"


def update_job_status(job_id, status, user_email,type_of_job):
    """Update the status of a user's job."""
    user_key = user_job_key(user_email,type_of_job)
    redis_client.hset(user_key, job_id, status)

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
    
def terminate_pod(pod_id) :
    try:
        runpod.terminate_pod(pod_id)
        app.logger.info("deleted pod with id: {pod_id}")
    except Exception as e:
        app.logger.info("unable to delete pod with id:{pod_id}")

# Create a pod
def create_pod_and_get_id(name, image_name, gpu_type_id, ports, container_disk_in_gb, env_vars):
    try:
        pod = runpod.create_pod(name=name, image_name=image_name, gpu_type_id=gpu_type_id,
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


def convert_voice(file_path1, spk_id, user_email):
    """
    Synchronously uploads a file and handles voice conversion.

    :param file_path: The file path of the audio file to upload.
    :param spk_id: Speaker ID for voice transformation.
    :param user_email: User's email for job tracking.
    """
    #base_url = os.environ.get('INFER_URL')
    #url = f"{base_url}/convert_voice"
    app.logger.info(f'filepath where file saved initiallu=: {file_path1}')
    job = get_current_job()

    # Define user_key outside the try block to ensure it's available in the except block
    
    job_id = job.id if job else 'default_id'  # Fallback ID in case this runs outside a job context
     
    
    directory, filename = os.path.split(file_path1)
    

# Generate the new file path with job_id as the filename, preserving the original extension
    
    new_filename = f"{job_id}{os.path.splitext(filename)[1]}"  # Preserves original file extension
    app.logger.error(f'new file name=: {new_filename}')
    app.logger.error(f'directory=: {directory}')
    #file_path = os.path.join(directory, new_filename)
    #os.rename(file_path1, file_path)
    #app.logger.error(f'new file path=: {file_path}')
    

    try:
        
        bucket_name = "sing"
        pod_id = create_pod_and_get_id("infer", "smjain/infer:v6", "NVIDIA RTX A4500", "5000/http", 20, env_vars)
        app.logger.info('After creating pod for training')

        if not pod_id:
            raise Exception("Failed to create the pod or retrieve the pod ID.")

        check_pod_is_ready(pod_id)
        
        app.logger.info('checked that pod is ready now')
        
        
        
        
        url = f'https://{pod_id}-5000.proxy.runpod.net/convert_voice'
        app.logger.info('before call to upload files for training done')

        
        file_path = os.path.join(directory, new_filename)
        app.logger.error(f'old filepath =: {file_path1}')
        app.logger.error(f'new filepath =: {file_path}')
        
        os.rename(file_path1, file_path)
        app.logger.error(f'new file path=: {file_path}')
        time.sleep(10)
    # Open the file and prepare for the POST request
        with open(file_path, 'rb') as file:
            files = {'file': file}
            data = {'spk_id': spk_id, 'voice_transform': '0'}
            app.logger.info(f'Infer url: {url}')

            # Send the POST request within the with block to ensure file is open
            response = requests.post(url, files=files, data=data, timeout=600)
            response.raise_for_status()  # Ensure HTTP errors are caught

        # Handle successful upload outside the with block
        update_job_status(job.id, "finished", user_email, 'infer')
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
        file_exists = check_file_in_space(ACCESS_ID, SECRET_KEY, bucket_name, file_key)
        if file_exists:
            app.logger.info('file found in space')
            update_job_status(job.id, "finished", user_email, 'infer')
            use_credit(user_email,'song')
            redis_client.decr(WORKER_COUNT_KEY)
            if pod_id:
                terminate_pod(pod_id)
                return True, "Request timed out, but file was processed successfully."
        else:
            app.logger.info('file not found in space')
            return False, "Request timed out and file was not found in cloud storage."
        
        app.logger.info(f'Upload failed: {e}')
        update_job_status(job.id, "failed", user_email, 'infer')
        redis_client.decr(WORKER_COUNT_KEY)
        
        if pod_id:
            terminate_pod(pod_id)
        return False, str(e)

    except Exception as e:
        # Handle other exceptions
        app.logger.info("error occured .now check file presence in space")
        file_key = f'{job_id}.mp3'
        app.logger.info(f'file ={file_key}')
        file_exists = check_file_in_space(ACCESS_ID, SECRET_KEY, bucket_name, file_key)
        if file_exists:
            app.logger.info('file found in space')
            update_job_status(job.id, "finished", user_email, 'infer')
            use_credit(user_email,'song')
            redis_client.decr(WORKER_COUNT_KEY)
            if pod_id:
                terminate_pod(pod_id)
                return True, "Request timed out, but file was processed successfully."
        else:
            app.logger.info('file not found in space')
            return False, "Request timed out and file was not found in cloud storage."

        app.logger.error(f'Conversion failed: {e}')
        update_job_status(job.id, "failed", user_email, 'infer')
        redis_client.decr(WORKER_COUNT_KEY)
        #if pod_id:
        #    terminate_pod(pod_id)
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








def train_model(file_name, model_name, user_email):
    job = get_current_job()
    update_job_status(job.id, "started", user_email, 'train')

    try:
        bucket_name = "sing"
        pod_id = create_pod_and_get_id("train", "smjain/train:v7", "NVIDIA RTX A4500", "5000/http", 20, env_vars)
        app.logger.info('After creating pod for training')

        if not pod_id:
            raise Exception("Failed to create the pod or retrieve the pod ID.")

        check_pod_is_ready(pod_id)
        app.logger.info('checked that pod is ready now')
        file_path = download_from_do(file_name)
        app.logger.info('downloaded file from do')
        final_model_name = f"{user_email}_{model_name}"
        
        url = f'https://{pod_id}--5000.proxy.runpod.net/process_audio'
        app.logger.info('before call to upload files for training done')
        success, message = upload_files(ACCESS_ID, SECRET_KEY, url, final_model_name, bucket_name, file_path)
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
            #update_model_count(user_email, redis_client)
            update_job_status(job.id, "finished", user_email, 'train')
            app.logger.info('updated model state to finished')
            #use_credit(user_email,'model')
            app.logger.info('credit consumed')
            push_model_to_infer(final_model_name)
            app.logger.info('pushed model to infer engine')
        # Proceed with additional job steps as needed
        else:
            app.logger.info('got false return from upload_files so setting job status fail')
            update_job_status(job.id, "failed", user_email, 'train')
            redis_client.decr(WORKER_COUNT_KEY)
            if pod_id:
                terminate_pod(pod_id)
        
        
    except Exception as e:
        app.logger.error(f'Error during model training: {e}')
        update_job_status(job.id, "failed", user_email, 'train')
        print(f"Operation failed: {e}")
        redis_client.decr(WORKER_COUNT_KEY)
        if pod_id:
            terminate_pod(pod_id)



def infer_song(file_name, user_email):
    job = get_current_job()
    update_job_status(job.id, "started", user_email, 'infer')

    try:
        bucket_name = "sing"
        pod_id = create_pod_and_get_id("infer", "smjain/infer:v6", "NVIDIA RTX A4500", "5000/http", 20, env_vars)
        app.logger.info('After creating pod for training')

        if not pod_id:
            raise Exception("Failed to create the pod or retrieve the pod ID.")

        check_pod_is_ready(pod_id)
        app.logger.info('checked that pod is ready now')
        file_path = download_from_do(file_name)
        app.logger.info('downloaded file from do')
        final_model_name = f"{user_email}_{model_name}"
        
        url = f'https://{pod_id}--5000.proxy.runpod.net/process_audio'
        app.logger.info('before call to upload files for training done')
        success, message = upload_files(ACCESS_ID, SECRET_KEY, url, final_model_name, bucket_name, file_path)
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
            #update_model_count(user_email, redis_client)
            update_job_status(job.id, "finished", user_email, 'train')
            app.logger.info('updated model state to finished')
            #use_credit(user_email,'model')
            app.logger.info('credit consumed')
            push_model_to_infer(final_model_name)
            app.logger.info('pushed model to infer engine')
        # Proceed with additional job steps as needed
        else:
            app.logger.info('got false return from upload_files so setting job status fail')
            update_job_status(job.id, "failed", user_email, 'train')
            redis_client.decr(WORKER_COUNT_KEY)
            if pod_id:
                terminate_pod(pod_id)
        
        
    except Exception as e:
        app.logger.error(f'Error during model training: {e}')
        update_job_status(job.id, "failed", user_email, 'train')
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



    
    



