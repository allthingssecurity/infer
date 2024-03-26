#!/bin/sh

# Start the Flask application in the background
flask run --host=0.0.0.0 &

# Start the RQ workers in the background
# Assuming you have defined a Flask CLI command "start-workers" as shown in previous examples
flask start-workers &

# Wait for any processes to exit
wait -n

# If any process exits, terminate the others
kill 0
