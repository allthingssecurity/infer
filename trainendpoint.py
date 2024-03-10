from flask import Flask, redirect, url_for, render_template,session,request,jsonify
import subprocess
import os
import tempfile
from werkzeug.utils import secure_filename
import shutil

app = Flask(__name__)

# Allowed extensions for the audio files
ALLOWED_EXTENSIONS = {'wav', 'mp3', 'm4a'}

def allowed_file(filename):
    """Check if the uploaded file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    # Serve the file upload form
    return render_template('train.html')

@app.route('/process_audio', methods=['POST'])
def process_audio():
    """Endpoint to upload files and trigger processing."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    files = request.files.getlist('file')
    model_name = request.form.get('model_name', '')
    if not model_name:
        return jsonify({'error': 'Model name is required'}), 400

    if not files or all(file.filename == '' for file in files):
        return jsonify({'error': 'No selected files'}), 400

    # Create a temporary directory for this upload session
    tmpdirname = tempfile.mkdtemp(dir=os.getcwd())
    try:
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(tmpdirname, filename)
                file.save(filepath)

        # After saving all files to the temporary directory, call the scripts
        log_dir = f'logs/{model_name}'
        os.makedirs(log_dir, exist_ok=True)  # Ensure log directory exists

        # Assuming your scripts are modified to accept a directory of audio files
        subprocess.run(['python', 'trainset_preprocess_pipeline_print.py', tmpdirname, '40000', '12', log_dir, 'False'], check=True)
        subprocess.run(['python', 'extract_f0_print.py', log_dir, '12', 'harvest'], check=True)
        subprocess.run(['python', 'extract_feature_print.py', 'cuda:0', '1', '0', '0', log_dir], check=True)
        subprocess.run(['python', 'pretrain.py', '--exp_dir1', model_name, '--sr2', '40k', '--if_f0_3', '1', '--spk_id5', '0'], check=True)
        subprocess.run(['python3', 'train_nsf_sim_cache_sid_load_pretrain.py', '-e', model_name, '-sr', '40k', '-f0', '1', '-bs', '19', '-g', '0', '-te', '200', '-se', '50', '-pg', 'pretrained/f0G40k.pth', '-pd', 'pretrained/f0D40k.pth', '-l', '0', '-c', '0'], check=True)

        return jsonify({'success': True, 'message': 'Files processed successfully.'})
    except Exception as e:
        model_path = os.path.join('weights', f'{model_name}.pth')
        if os.path.isfile(model_path):
            return jsonify({'success': True, 'message': 'Files processed with errors.', 'details': str(e)})
        else:
            return jsonify({'error': 'An error occurred during processing', 'details': str(e)}), 500
        return jsonify({'error': 'An error occurred during processing', 'details': str(e)}), 500
    finally:
        # Optionally remove the temporary directory after processing if no longer needed
          shutil.rmtree(tmpdirname)

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=False)
