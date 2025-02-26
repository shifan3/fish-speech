import json
import sseclient
import pyaudio
import base64
import urllib.parse
from threading import Thread
from queue import Queue
import time


text = """With apologies for the missing accents here and in the French bits of the long posting which follows - the dedication to 'Le Pouvoir dans la Peau' (Power in the skin) reads 'A Alastair Campbell, mon spin doctor prefere' (three missing accents in one word - mes excuses sinceres). 
So what did I do for this honour, you are asking? """

#text = "The post has just arrived and in it a very nice surprise"
text = urllib.parse.quote(text)
url = 'http://10.33.10.64:13255/tts/generate'
headers = {'Accept': 'text/event-stream'}

reference_id = "1"
url = url + f"?text={text}&reference_id={reference_id}"
print(url)
#response = with_requests(url, headers)
p = pyaudio.PyAudio()  
stream = None
queue = Queue()

def watch_queue():
    while True:
        segment = queue.get()
        if segment is None:
            print("stopping stream")
            stream.stop_stream()
            stream.close()
            p.terminate()
            return
        stream.write(segment)

thread = Thread(target=watch_queue)
thread.start()

start_time = time.time()
client = sseclient.SSEClient(url, headers=headers)
print("connection created", time.time() - start_time)
start_time = time.time()

try:
    print('start')
    for event in client:
        BRK = False
        for line in event.data.split('\n'):
            data = json.loads(line)
            if data['action'] == 'segment':
                samplerate = data['samplerate']
                if stream is None:
                    print("latency", time.time() - start_time)
                    stream = p.open(format = p.get_format_from_width(4),  
                        channels = 1,  
                        rate = samplerate,  
                        output = True, start=True)  
                audio = base64.b64decode(data['audio'])
                queue.put(audio)
            elif data['action'] == 'final':
                print('final', time.time() - start_time)
                queue.put(None)
                BRK = True
                break
        if BRK:
            break
except Exception as e:
    print("ERROR", e)
    queue.put(None)
    exit(1)
print("done")