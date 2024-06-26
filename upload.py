
from boto3 import session
from botocore.client import Config
import os
ACCESS_ID = os.getenv('ACCESS_ID', 'default_value')
SECRET_KEY = os.getenv('SECRET_KEY', 'default_value')


retry_config = Config(
    retries={
        'max_attempts': 5,  # Maximum number of retries
        'mode': 'standard',  # Retry mode (standard or adaptive)
    }
)

def upload_to_do(file_path):
    
    boto_session=session.Session()
    client = boto_session.client('s3',
                            region_name='nyc3',
                            endpoint_url='https://nyc3.digitaloceanspaces.com',
                            aws_access_key_id=ACCESS_ID,
                            aws_secret_access_key=SECRET_KEY,config=retry_config)
    filename_only = os.path.basename(file_path)
    # Upload a file to your Space
    response=client.upload_file(file_path, 'sing', filename_only)

    
    return response
    
def download_from_do(file_key):
    boto_session = session.Session()
    client = boto_session.client('s3',
                                 region_name='nyc3',
                                 endpoint_url='https://nyc3.digitaloceanspaces.com',
                                 aws_access_key_id=ACCESS_ID,
                                 aws_secret_access_key=SECRET_KEY,config=retry_config)
    
      # Ensure the downloads directory exists
    downloads_dir = 'downloads'
    if not os.path.exists(downloads_dir):
        os.makedirs(downloads_dir)
    
    # Set the full local path for the download
    full_local_path = os.path.join(downloads_dir, file_key)
    
    # Download the file from your Space
    client.download_file('sing', file_key, full_local_path)
    
    # Verify the download
    if os.path.exists(full_local_path):
        print(f"File downloaded successfully to {full_local_path}")
        return full_local_path
    else:
        print("Download failed.")
        return None



def generate_presigned_url(bucket_name, object_name, expiration=3600):
    """
    Generate a presigned URL to share an S3 object

    :param bucket_name: string
    :param object_name: string
    :param expiration: Time in seconds for the presigned URL to remain valid
    :return: Presigned URL as string. If error, returns None.
    """
    boto_session = session.Session()
    client = boto_session.client('s3',
                                 region_name='nyc3',
                                 endpoint_url='https://nyc3.digitaloceanspaces.com',
                                 aws_access_key_id=ACCESS_ID,
                                 aws_secret_access_key=SECRET_KEY,config=retry_config)
    
    try:
        response = client.generate_presigned_url('get_object',
                                                 Params={'Bucket': bucket_name,
                                                         'Key': object_name},
                                                 ExpiresIn=expiration)
    except Exception as e:
        print(e)
        return None
    return response



def download_from_do_with_prefix(prefix):
    boto_session = session.Session()
    client = boto_session.client('s3',
                                 region_name='nyc3',
                                 endpoint_url='https://nyc3.digitaloceanspaces.com',
                                 aws_access_key_id=ACCESS_ID,
                                 aws_secret_access_key=SECRET_KEY)
    
    # Ensure the downloads directory exists
    downloads_dir = 'downloads'
    if not os.path.exists(downloads_dir):
        os.makedirs(downloads_dir)
    
    # List objects in the Space with the specified prefix
    response = client.list_objects(Bucket='sing', Prefix=prefix)
    
    if 'Contents' in response:
        # Assuming you want to download the first file that matches the prefix
        file_key = response['Contents'][0]['Key']
        
        # Set the full local path for the download
        full_local_path = os.path.join(downloads_dir, os.path.basename(file_key))
        
        # Download the file from your Space
        client.download_file('sing', file_key, full_local_path)
        
        # Verify the download
        if os.path.exists(full_local_path):
            print(f"File downloaded successfully to {full_local_path}")
            return full_local_path
        else:
            print("Download failed.")
            return None
    else:
        print("No files found with the specified prefix.")
        return None


import os
from boto3 import session

def download_from_do_with_job_id(job_id):
    boto_session = session.Session()
    client = boto_session.client('s3',
                                 region_name='nyc3',
                                 endpoint_url='https://nyc3.digitaloceanspaces.com',
                                 aws_access_key_id=ACCESS_ID,
                                 aws_secret_access_key=SECRET_KEY)
    
    # Ensure the downloads directory exists
    downloads_dir = 'downloads'
    if not os.path.exists(downloads_dir):
        os.makedirs(downloads_dir)
    
    # List all objects in the Space (or use a more general prefix if applicable)
    response = client.list_objects(Bucket='sing')
    
    matched_files = []
    if 'Contents' in response:
        for content in response['Contents']:
            file_key = content['Key']
            # Split the filename to extract the job ID part
            parts = file_key.split('##')
            if len(parts) > 1 and job_id in parts[1]:
                matched_files.append(file_key)
                
    if matched_files:
        # For simplicity, assuming you want to download the first matched file
        file_key = matched_files[0]
        full_local_path = os.path.join(downloads_dir, os.path.basename(file_key))
        
        # Download the file from your Space
        client.download_file('sing', file_key, full_local_path)
        
        # Verify the download
        if os.path.exists(full_local_path):
            print(f"File downloaded successfully to {full_local_path}")
            return full_local_path
        else:
            print("Download failed.")
            return None
    else:
        print("No files found matching the job ID.")
        return None

def download_for_video(job_id):
    # Here, you would determine the file_key from the job_id
    # For this example, let's assume they are the same
    file_key = f'{job_id}.mp3'
    
    # Call the download function
    local_file_path = download_from_do(file_key)
    
    if local_file_path:
        return local_file_path
    else:
        return "Download failed", 404
