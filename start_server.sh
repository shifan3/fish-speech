set -e
NUM_THREAD=${NUM_THREAD:-4}
NUM_WORKER=${NUM_WORKER:-4}
TIMEOUT=${TIMEOUT:-600}
PORT=${PORT:-13255}
BIND_ADDR="0.0.0.0:$PORT"
LOG_FILE_BASE=engine.log

ACCESS_LOG_FORMAT='%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'
mkdir -p logs
LOG_FILE=./logs/engine.`date "+%Y-%m-%d-%H-%M-%S"`.log
ACCESS_LOG_FILE=./logs/engine_access.`date "+%Y-%m-%d-%H-%M-%S"`.log
PID_FILE=engine.pid
rm -f $PID_FILE
rm -f $LOG_FILE_BASE
ln -s $LOG_FILE $LOG_FILE_BASE

gunicorn --daemon -c gunicorn_config.py --worker-class uvicorn.workers.UvicornWorker \
    -w $NUM_WORKER --threads $NUM_THREAD  --timeout $TIMEOUT -b $BIND_ADDR -p $PID_FILE server:app \
    --capture-output --log-file $LOG_FILE --access-logfile $ACCESS_LOG_FILE --access-logformat "$ACCESS_LOG_FORMAT"

last_line=""
for j in {1..10000}
do
    sleep 0.2
    n_finished=`cat $LOG_FILE | grep "Engine Setup Done, Warmup is Required" | wc -l`
    if [ $n_finished -eq $NUM_WORKER ]; then
        echo "engine started"
        break
    else
        curr_line=`cat $LOG_FILE | tail -n 1`
        if [ "$curr_line" != "$last_line" ]; then
            echo "$curr_line"
        fi
        last_line=$curr_line
    fi
done
echo "start warmup"
python3 force_compile.py -n $NUM_WORKER --url "http://localhost:$PORT/tts/generate"
echo "warmup done"
