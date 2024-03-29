import redis
from redis import Redis
import os
import logging
from logging.handlers import RotatingFileHandler

redis_host = os.getenv('REDIS_HOST', 'default_host')
redis_port = int(os.getenv('REDIS_PORT', 25061))  # Default Redis port
redis_username = os.getenv('REDIS_USERNAME', 'default')
redis_password = os.getenv('REDIS_PASSWORD', '')
#redis_conn = Redis(host=redis_host, port=redis_port, username=redis_username, password=redis_password, ssl=True, ssl_cert_reqs=None)




redis_client = Redis(host=redis_host, port=redis_port, username=redis_username, password=redis_password, ssl=True, ssl_cert_reqs=None)


# Middleware or decorator to check if user is logged in
def get_user_credits(user_email, activity):
    """
    Retrieves the current number of credits for a given user and activity.
    """
    return int(redis_client.hget(f"user:{user_email}", f"{activity}_credits") or 0)

def update_user_credits(user_email, activity, credits):
    """
    Updates the number of credits for a given user and activity.
    """
    redis_client.hset(f"user:{user_email}", f"{activity}_credits", credits)


def add_credits(app,user_email, activity,credits):
    """
    Attempts to use a credit for the specified activity, consuming one credit.
    """
    try:
        app.logger.info(f"inside adding credits of user {user_email}")
        current_credits = get_user_credits(user_email, activity)
        app.logger.info(f"got current credits {current_credits}")
    
        update_user_credits(user_email, activity, current_credits + credits)
    #print(f"Credit used. Remaining {activity} credits: {credits - 1}")
        app.logger.info("credits updated")
        
    except Exception as e:
        print(e)  # Log the error for debugging
        app.logger.info(f"error:{str(e)}")
        #response = {'status': 'failure', 'error': str(e)}
        #return jsonify(response), 500
        
    


def use_credit(user_email, activity):
    """
    Attempts to use a credit for the specified activity, consuming one credit.
    """
    credits = get_user_credits(user_email, activity)
    
    if credits > 0:
        print(f"Using one credit for {activity} for {user_email}.")
        # Deduct one credit and update Redis
        update_user_credits(user_email, activity, credits - 1)
        print(f"Credit used. Remaining {activity} credits: {credits - 1}")
        return True
    else:
        print(f"Insufficient {activity} credits for {user_email}.")
        return False

