import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from upload import generate_presigned_url

def load_and_personalize_template(event_type, outcome, email,song_url):
    """Load and personalize the email template based on event type and outcome."""
    filename = f'email_templates/{event_type}_{outcome}.txt'
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            template = file.read()
            username = email.split('@')[0]  # Extract username from email
            personalized_content = template.format(username=username,link=song_url)
            return personalized_content
    except FileNotFoundError:
        return "Template file not found."



def send_email(to_email, event_type, outcome,object_name):
    # Load and personalize the email content
    #app.logger.info(f"inside send email. to send email to {to_email}") 
    bucket_name='sing'
    song_url = generate_presigned_url(bucket_name, object_name, expiration=3600)  # 1 hour validity
    personalized_content = load_and_personalize_template(event_type, outcome, to_email,song_url)
    #app.logger.info(f"content : {personalized_content}")
    
    # Define email subjects for each event type and outcome
    subject_lines = {
        "model_training": {
            "success": "🌟 Model Training Succeeded!",
            "failure": "🔴 Model Training Failed",
        },
        "song_conversion": {
            "success": "🎶 Song Conversion Succeeded!",
            "failure": "🔴 Song Conversion Failed",
        },
        "video_conversion": {
            "success": "🎥 Video Conversion Succeeded!",
            "failure": "🔴 Video Conversion Failed",
        }
    }
    
    # Select subject line based on event type and outcome
    #app.logger.info("get subject")
    subject = subject_lines.get(event_type, {}).get(outcome, "Notification from MaiBhiSinger")
    #app.logger.info(f"got subject: {subject}")
    # SMTP settings (as before)
    smtp_server = os.getenv('SMTP_SERVER', 'smtp.mandrillapp.com')
    smtp_user = os.getenv('SMTP_USER', 'info@maibhisinger.com')
    smtp_pass = os.getenv('SMTP_PASSWORD', '')
    smtp_port = int(os.getenv('SMTP_PORT', 587))

    # Create and send the email (as before)
    msg = MIMEMultipart()
    msg['From'] = smtp_user
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(personalized_content, 'plain'))

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
            print("Email sent successfully!")
    except Exception as e:
        print(f"Failed to send email: {e}")
