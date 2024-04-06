import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from upload import generate_presigned_url

def load_and_personalize_template(event_type, outcome, email, song_url=None, verification_code=None,job_id=None,errorMessage=None):
    """Load and personalize the email template based on event type, outcome, and optional song URL or verification code."""
    filename = f'email_templates/{event_type}_{outcome}.txt'
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            template = file.read()
            username = email.split('@')[0]  # Extract username from email

            # Initialize placeholders in case they're not used
            link_placeholder = ""
            verification_link = ""
            error=""
            job_identity= ""
          
            # Check if song_url is provided, and format the template accordingly
            if song_url:
                link_placeholder = song_url

            # Check if verification_code is provided, and format the template accordingly
            if verification_code:
                
                verification_link = f"https://yourdomain.com/verify_email?token={verification_code}"
            
            if errorMessage:
                error=errorMessage
                
            if job_id:
                job_identity=job_id

            # Use placeholders in formatting the template
            personalized_content = template.format(username=username, link=link_placeholder, verification_link=verification_link,error=error,job_identity=job_identity)
            
            return personalized_content
    except FileNotFoundError:
        return "Template file not found."





def send_email(to_email,event_type, outcome,job_id=None, object_name=None, verification_code=None,errorMessage=None):
    # Generate a presigned URL for the object, if an object name is provided
    bucket_name = 'sing'
    song_url = None
    if object_name:
        song_url = generate_presigned_url(bucket_name, object_name, expiration=3600)  # 1 hour validity

    # Load and personalize the email content based on provided parameters
    personalized_content = load_and_personalize_template(event_type, outcome, to_email, song_url=song_url, verification_code=verification_code,job_id=job_id,errorMessage=errorMessage)

    # Define email subjects for each event type and outcome
    subject_lines = {
        "model_training": {"success": "🌟 Model Training Succeeded!", "failure": "🔴 Model Training Failed"},
        "song_conversion": {"success": "🎶 Song Conversion Succeeded!", "failure": "🔴 Song Conversion Failed"},
        "video_conversion": {"success": "🎥 Video Conversion Succeeded!", "failure": "🔴 Video Conversion Failed"},
        "waitlist_request_made":{"success": "🎥 You are added to waitlist", "failure": "🔴 Sorry we could'nt add you to waitlist for now"},        
        "added_to_approved":{"success": "🎥 You are approved user for trial access.", "failure": "🔴 Sorry we could'nt approve you"}
        "waitlist_added_admin":{"success": "🎥User waiting in waitlist.", "failure": "🔴 Sorry may be user is waiting in waitlist but some issue"}
    }

    # Select subject line based on event type and outcome
    subject = subject_lines.get(event_type, {}).get(outcome, "Notification from MaiBhiSinger")

    # SMTP settings
    smtp_server = os.getenv('SMTP_SERVER', 'smtp.mandrillapp.com')
    smtp_user = os.getenv('SMTP_USER', 'info@maibhisinger.com')
    smtp_pass = os.getenv('SMTP_PASSWORD', '')
    smtp_port = int(os.getenv('SMTP_PORT', 587))

    # Create and send the email
    msg = MIMEMultipart()
    msg['From'] = smtp_user
    msg['To'] = to_email
    msg['Subject'] = subject
    msg['Bcc'] = 'jain.sm@gmail.com'
    msg.attach(MIMEText(personalized_content, 'plain'))

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
            print("Email sent successfully!")
    except Exception as e:
        print(f"Failed to send email: {e}")
