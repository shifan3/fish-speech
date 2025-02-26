import os
import torch
#torch.set_num_threads(1)
from argparse import ArgumentParser
from pathlib import Path
from typing import Annotated
from  scipy.io import wavfile 
import json
import io
import logging
import base64

from tools.inference_engine import TTSInferenceEngine
from tools.llama.generate import launch_thread_safe_queue
from tools.schema import ServeTTSRequest
from tools.vqgan.inference import load_model as load_decoder_model
from websocket_server import WebsocketServer
from fastapi import FastAPI, Response, Header
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import json, uvicorn
from asyncio import sleep

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Make einx happy
os.environ["EINX_FILTER_TRACEBACK"] = "false"


@app.get("/tts/generate")
def tts(
    text: str,
    reference_id: str = None,
    streaming: bool = False,
    accept: Annotated[str | None, Header()] = None
):
    
    if accept == "text/event-stream":
        streaming = True
    inference_engine:TTSInferenceEngine = app.inference_engine
    resp = inference_engine.inference(
        ServeTTSRequest(
            text=text,
            references=[],
            reference_id=reference_id,
            max_new_tokens=1024,
            chunk_length=200,
            top_p=0.7,
            repetition_penalty=1.5,
            temperature=0.7,
            format="wav",
            streaming=streaming,
        )
    )
    if not streaming:
        samplerate, audio = list(resp)[-1].audio
        bytes_io = io.BytesIO()
        wavfile.write(bytes_io, samplerate, audio)
        bytes_io.seek(0)
        return Response(content=bytes_io.getvalue(), media_type="audio/wav")
    else:
        def eventStream(resp):
            for r in resp:
                if r.code == 'segment':
                    samplerate, audio = r.audio
                    yield "data: " +json.dumps({"action": r.code, 'samplerate':samplerate, 'audio':base64.b64encode(audio.tobytes()).decode("utf-8")}) + "\n\n"
            yield "data: " +json.dumps({"action": "final"}) + "\n\n"

        return StreamingResponse(eventStream(resp), media_type="text/event-stream")



def setup_logging(level=logging.INFO):
    logging.getLogger().setLevel(level)
    ch = logging.StreamHandler()
    ch.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s;%(process)d;%(levelname)s;%(message)s", "%Y-%m-%d %H:%M:%S")
    ch.setFormatter(formatter)
    logging.getLogger().handlers = [ch]


inference_engine = None
def setup_app():
    setup_logging(logging.INFO)
    torch.multiprocessing.set_start_method('spawn')
    LLAMA_CHECKPOINT_PATH = "checkpoints/fish-speech-1.5"
    DECODER_CHECKPOINT_PATH = "checkpoints/fish-speech-1.5/firefly-gan-vq-fsq-8x1024-21hz-generator.pth"
    DECODER_CONFIG_NAME = "firefly_gan_vq"
    global inference_engine


    logging.info("Loading Llama model...")
    llama_queue = launch_thread_safe_queue(
        checkpoint_path=LLAMA_CHECKPOINT_PATH,
        device="cuda",
        precision=torch.bfloat16,
        compile=True,
    )

    logging.info("Loading VQ-GAN model...")
    decoder_model = load_decoder_model(
        config_name=DECODER_CONFIG_NAME,
        checkpoint_path=DECODER_CHECKPOINT_PATH,
        device="cuda",
    )

    logging.info("Decoder model loaded, warming up...")

    # Create the inference engine
    inference_engine = TTSInferenceEngine(
        llama_queue=llama_queue,
        decoder_model=decoder_model,
        compile=True,
        precision=torch.bfloat16,
    )
    app.inference_engine = inference_engine
    """
    for resp in inference_engine.inference(
        ServeTTSRequest(
            text="Hello, how are you?",
            references=[],
            reference_id=None,
            streaming=False,
        )
    ):
        pass
    
    for resp in inference_engine.inference(
        ServeTTSRequest(
            text="Transformers provides APIs to quickly download and use those pretrained models on a given text",
            references=[],
            reference_id=None,
            streaming=False,
        )
    ):
        if resp.code == 'segment' or resp.code == 'final':
            samplerate, audio = resp.audio
            wavfile.write("/mnt/data5/test.wav", samplerate, audio)
    wavfile.write("/mnt/data5/test.wav", samplerate, audio)
    """
    logging.info("Engine Setup Done, Warmup is Required")

def message_received(client, server, message):
    message = json.loads(message)
    reference_id=message.get("reference_id", None)
    if reference_id:
        reference_id = str(reference_id)
    for i, resp in enumerate(inference_engine.inference(
        ServeTTSRequest(
            text=message["text"],
            references=[],
            reference_id=reference_id,
            streaming=True,
        ))
    ):
        
        if resp.code == 'segment':
            samplerate, audio = resp.audio
            server.send_message(client, json.dumps({"action": "segment", 'samplerate':samplerate, 'audio':base64.b64encode(audio.tobytes()).decode("utf-8")}))
    server.send_message(client, json.dumps({"action": "final"}))


def ws_main_thread():
    server = WebsocketServer(host='0.0.0.0', port=13254, loglevel=logging.INFO)
    server.set_fn_message_received(message_received)
    server.run_forever()

if __name__ == "__main__":
    setup_app()
    #Thread(target=ws_main_thread).start()
    uvicorn.run(app, host="0.0.0.0", port=13255)
else:
    setup_app()
