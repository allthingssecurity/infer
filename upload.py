
from boto3 import session
from botocore.client import Config
import os
ACCESS_ID = os.getenv('ACCESS_ID', 'default_value')
SECRET_KEY = os.getenv('SECRET_KEY', 'default_value')


def upload_to_do(file_path):
    
    boto_session=session.Session()
    client = boto_session.client('s3',
                            region_name='nyc3',
                            endpoint_url='https://nyc3.digitaloceanspaces.com',
                            aws_access_key_id=ACCESS_ID,
                            aws_secret_access_key=SECRET_KEY)
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
                                 aws_secret_access_key=SECRET_KEY)
    
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


# Initiate session
