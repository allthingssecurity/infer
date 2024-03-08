import runpod
import requests
import time
import json

import boto3
import os
from botocore.exceptions import ClientError
import time
from rq import get_current_job


# Get all my pods
#pods = runpod.get_pods()
#gpus=runpod.get_gpus();
#print(gpus)
# Get a specific pod
#pod = runpod.get_pod(pod.id)

runpod_key=os.getenv('runpod_key', '')
runpod.api_key = runpod_key


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






def convert_voice(pod_id,file_paths,spk_id):
    """
    Synchronously uploads multiple files.

    :param access_id: Access ID for authentication.
    :param secret_key: Secret key for authentication.
    :param file_paths: A list of file paths of the audio files to upload.
    """
    url = f'https://{pod_id}--5000.proxy.runpod.net/convert_voice'
    
    files = [('file', (open(file_path, 'rb'))) for file_path in file_paths]
    data = {'spk_id': spk_id, 'voice_transform': '0'}  # Assuming spk_id is passed here and voice_transform hardcoded to 0

    response = requests.post(url, files=files, data=data, timeout=180)  # 3 minutes timeout

    if response.status_code == 200:
        print("converted successfully.")
        print(response.json())  # Assuming the server responds with JSON
        audio_id = response.json().get('audio_id')
        return audio_id
    else:
        print(f"Failed to upload files. Status: {response.status_code}")
        #print(response.text)
        return None

    # Close the file objects
    
# Ensure all file objects are properly closed after upload

def download_and_save_mp3(pod_id, audio_id, save_path):
    """
    Downloads an MP3 file using the given 'audio_id' and saves it locally.

    :param base_url: The base URL for the GET request.
    :param audio_id: The unique identifier for the audio file to download.
    :param save_path: The local path where the MP3 file will be saved.
    """
    url = f'https://{pod_id}--5000.proxy.runpod.net/get_processed_audio/{audio_id}'
    
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=128):
                f.write(chunk)
        print(f"MP3 file downloaded and saved to {save_path}")
    else:
        print(f"Failed to download MP3 file. Status code: {response.status_code}")



# Assuming env_vars is a dictionary containing your environment variables like ACCESS_ID and SECRET_KEY

# Create the pod and get its ID
def main(file_path,spk_id):
    job = get_current_job()
    job_id = job.id if job else 'default_id'  # Fallback ID in case this runs outside a job context
    print(job_id)
    #pass this job id and use it instead of unique id. once job is finished then client can access file over rest api
    
    ACCESS_ID=os.getenv('ACCESS_ID', '')
    SECRET_KEY=os.getenv('SECRET_KEY', '')
    env_vars = {"ACCESS_ID": ACCESS_ID, "SECRET_KEY": SECRET_KEY}
    
    #file_paths = ["c:/shashank/trips/128-Tu Is Tarah Se Mere Zindagi Main - Aap To Aise Na The 128 Kbps (mp3cut.net).mp3"]
    bucket_name = "sing"  # Your DigitalOcean Space name
    #spk_id="trips"
    save_path = f"{job_id}.mp3"
    # Run synchronous pod creation and status check in the event loop
    start_time = time.time()
    pod_id = create_pod_and_get_id("infer", "smjain/infer:v4", "NVIDIA RTX A4500", "5000/http", 20, env_vars)
    if pod_id:
        check_pod_is_ready(pod_id)
        
        
        audio_id =convert_voice(pod_id,file_path,spk_id)
        if audio_id:
            download_and_save_mp3(pod_id, audio_id, save_path)
        conv_time=time.time()-start_time
        print(f"Voice conversion took {conv_time} seconds.")
        
    else:
        print("Failed to create the pod or retrieve the pod ID.")

if __name__ == "__main__":
    # Connect to Redis
    main()
    
    



