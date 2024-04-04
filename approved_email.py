import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Your Mailchimp SMTP credentials
smtp_server = 'smtp.mandrillapp.com'  # This might be different, check your account
smtp_user = 'info'  # Your SMTP username
smtp_pass = 'md-Ph8jEVKFpGWbPflEFWIxWg'  # Your SMTP API key

# Email details
from_email = 'info@maibhisinger.com'  # Your email address
to_email = 'jain.sm@gmail.com'  # Recipient's email address
subject = 'Hello from MaiBhiSinger!'
body = """Dear Shashank ,

The stage is set, and the spotlight is on you! 🎤 Welcome to your trial at www.maibhisinger.com, where your voice is the star of the show.

Here's how you can start creating magic:

Log In: Access your account [here] with the email you signed up with.
Explore: Take a tour of our platform - familiarize yourself with the tools and features that will help you create your songs.
Create: record your voice for machine to learn about your voice patterns.  After that sing like any other singer.
Need inspiration? Our [Resource Page/Blog] is filled with creative prompts, success stories, and tutorials to help you hit the right notes.

🎉 Let's make music that resonates and tells your story. If you have any questions or need a little guidance, our support team is here for you at [info@maibhisinger].

Welcome to the beginning of your unforgettable musical journey,
The maibhisinger.com Team

"""
# Create MIME message
msg = MIMEMultipart()
msg['From'] = from_email
msg['To'] = to_email
msg['Subject'] = subject
msg.attach(MIMEText(body, 'plain'))

# Send the email
try:
    with smtplib.SMTP(smtp_server, 587) as server:  # Use 587 or 25 for non-encrypted connection
        server.starttls()  # Secure the connection
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
        print("Email sent successfully!")
except Exception as e:
    print(f"Failed to send email: {e}")
