#!/bin/bash
# Start Flask app
flask run --host=0.0.0.0 &

# Start 4 RQ workers
rq worker default & 
rq worker default & 


# Wait for all background jobs to finish
wait

kill $(jobs -p)