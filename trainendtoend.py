import runpod
import requests
import time
import json
#import asyncio
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
    
    if models_trained < model_training_limit:
        # If the user hasn't exceeded their limit, train another model
        
        redis_client.hincrby(f"user:{user_email}", "models_trained", 1)
        app.logger.info("update of model train done in queue")
        return 'update done'
    else:
        # If the user has exceeded their limit
        return 'error: Upgrade to premium for more model trainings or wait for the limit to reset'


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
                break
            else:
                print(f"Waiting for pod {pod_id} to be ready...")
        else:
            print(f"Pod {pod_id} does not exist or information is not available.")
        
        time.sleep(10)  # Wait for 10 seconds before checking again
        # Check if pod details are present and if the pod is running



def check_file_in_space(access_id, secret_key, bucket_name, file_key, check_interval=60, timeout=18000):
    """
    Periodically checks for the existence of a file in a DigitalOcean Space.

    :param access_id: Your DigitalOcean Spaces access ID.
    :param secret_key: Your DigitalOcean Spaces secret key.
    :param bucket_name: The name of the Space.
    :param file_key: The key of the file in the Space.
    :param check_interval: How often to check for the file (in seconds).
    :param timeout: How long to keep checking before giving up (in seconds).
    """
    session = boto3.session.Session()
    client = session.client('s3',
                            region_name='nyc3',
                            endpoint_url='https://nyc3.digitaloceanspaces.com',
                            aws_access_key_id=access_id,
                            aws_secret_access_key=secret_key)

    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
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
            print("Starting file check")
            # Assuming check_file_in_space is defined elsewhere to check the file presence in the cloud storage
            file_key = f'{model_name}.pth'
            check_file_in_space(access_id, secret_key, bucket_name, file_key)
            return False, str(e)

# Ensure all file objects are properly closed after upload
def close_files(files):
    for _, file_obj in files:
        file_obj.close()

def add_model_to_user(user_email, model_name):
    redis_client.rpush(user_email, model_name)
    training_done_key = f"{user_email}:trained"
    redis_client.set(training_done_key, "true")


def convert_voice(file_path,spk_id):
    """
    Synchronously uploads multiple files.

    :param access_id: Access ID for authentication.
    :param secret_key: Secret key for authentication.
    :param file_paths: A list of file paths of the audio files to upload.
    """
    #url = f'https://{pod_id}--5000.proxy.runpod.net/convert_voice'
    
    base_url = os.environ.get('INFER_URL')
    url = f"{base_url}/convert_voice/"
    
    
    
    with open(file_path, 'rb') as file:
        files = {'file': file}
        
        # Include any additional data as a dictionary
        data = {'spk_id': spk_id, 'voice_transform': '0'}  # Assuming spk_id is passed here and voice_transform hardcoded to 0

        # Send a POST request to the server
        try:
            app.logger.info(f'Infer url : {url}')
            response = requests.post(url, files=files, data=data, timeout=600)
            response.raise_for_status()  # This will raise an exception for HTTP error codes
            app.logger.info('Infer done successfully')
            return True, "infer went succesfully"
        except requests.exceptions.RequestException as e:
            print("Failed to convert audio")
            # Assuming check_file_in_space is defined elsewhere to check the file presence in the cloud storage
            app.logger.info('Infer Failed ')
            return False, str(e)

    
    
    

    if response.status_code == 200:
        
        #app.logger.info('Infer of song done successfully')
        app.logger.info(f'got response from infer: {response.json()}')
        print(response.json())  # Assuming the server responds with JSON
        audio_id = response.json().get('audio_id')
        job = get_current_job()
        job_id = job.id if job else 'default_id'  # Fallback ID in case this runs outside a job context
        app.logger.info(f'got job id: {job_id}')
        
        save_path = f"{job_id}.mp3"
        download_and_save_mp3(base_url,audio_id,save_path)
        app.logger.info(f'downloaded the converted file to save path {save_path}')
        response=upload_to_do(save_path)
        app.logger.info('uploade converted file to DO space')
        #download_and_save_mp3(audio_id,save_path)
        return response
    else:
        print(f"Failed to upload files. Status: {response.status_code}")
        #print(response.text)
        return None


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





def main(file_name,model_name,user_email):
    
    
    
    bucket_name = "sing"  # Your DigitalOcean Space name
    
    # Run synchronous pod creation and status check in the event loop
    #loop = asyncio.get_running_loop()
    pod_id = create_pod_and_get_id("train", "smjain/train:v6", "NVIDIA RTX A4500", "5000/http", 20, env_vars)
    app.logger.info('After creating pod for training')
    if pod_id:
        
        check_pod_is_ready(pod_id)
        app.logger.info('checked pod is ready')
        url = f'https://{pod_id}--5000.proxy.runpod.net/process_audio'
        #upload_files(url)
        
        # Proceed with asynchronous file upload
        #print("file uploaded to ",file_path)
        #logger.info("This is an info message from the background task. file_path is valid: {}".format(file_path is not None))
        file_path=download_from_do(file_name)
        app.logger.info('downloaded audio from space')
        upload_files(ACCESS_ID,SECRET_KEY,url, user_email,bucket_name, file_path)
        app.logger.info('uploaded to DO Space')
        add_model_to_user(user_email,model_name)
        update_model_count(user_email,redis_client)
        app.logger.info('updated redis')
        ##push model to infer app dir
        app.logger.info('before pushing to infer')
        push_model_to_infer(user_email)
        app.logger.info('Training completed. Model pushed to bucket and pulled by Infer')
        
        # Check for the file in the S3 bucket (DigitalOcean Spaces)
        
    else:
        print("Failed to create the pod or retrieve the pod ID.")


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



    


if __name__ == "__main__":
    main()
    
    



