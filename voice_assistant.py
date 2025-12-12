#!/usr/bin/env python3
"""
Voice assistant for Raspberry Pi

- STT: OpenAI Whisper (tiny)
- LLM: phi3:mini served by Ollama on localhost
- TTS: pyttsx3 (offline)
- Tool: "navigation" that the LLM can call via structured JSON output

Dependencies to install (example):

    pip install openai-whisper sounddevice numpy requests pyttsx3

You also need:
    - Ollama installed and running
    - The phi3:mini model pulled:
        ollama pull phi3:mini
"""

import os
import sys
import json
import time
import queue
import threading
import traceback

import numpy as np
import sounddevice as sd
import requests
import whisper
import pyttsx3
import fastapi_poe as fp
import asyncio
import pvporcupine
import requests 
import subprocess 




# -----------------------
# Configuration
# -----------------------

WHISPER_MODEL_NAME = "tiny"          # whisper model size
SAMPLE_RATE = 16000                  # Whisper default is 16000 Hz
CHANNELS = 1                         # mono audio
LISTEN_SECONDS = 5                   # seconds per recording
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "phi3:mini"

POE_API_KEY = "QcQOJvdfGWtrKcJx_DBd_Xds1KBfI89W1odz_a_jkE0"
GEOCODE_API_KEY = "6935ecd83e8fe231705840rvga127ce"

# You will tweak this prompt yourself to describe the role, tools, etc.
SYSTEM_PROMPT = """
You are a voice assistant running on a Raspberry Pi based smart walking cane for the blind. You have a GPS conneceted and communicate to a backend for communication services. 

You have two responsibilities:
1) Chat naturally with the user with empathy and understanding. Answer questions, provide information, and be friendly. Answer in a short sentence. 
2) When the user asks for directions, navigation, or anything location related
   that the robot can handle, you call the navigation tool. 

You must always respond in the following JSON format, with no extra text:

{
  "mode": "reply" | "tool_call",
  "reply": "<natural language response to speak to user>",
  "tool": null OR "navigation",
  "arguments": null OR {
    "destination": "<string description of where to go>",
    "mode": "<optional mode such as walking, driving, etc>"
  }
}

Rules:
- If you just want to talk or answer a question, use:
    "mode": "reply",
    "reply": "<your response>",
    "tool": null,
    "arguments": null
- If the user wants navigation or directions that the robot should follow, use:
    "mode": "tool_call",
    "reply": "<your response to speak to the user>",
    "tool": "navigation",
    "arguments": { ... } with destination and optional mode
- Always return valid JSON. No comments. No trailing commas.
- The reply string must always be present and should be something brief
  that I can read aloud, even for tool calls.

  OUTPUT: the JSON only, nothing else.
""".strip()

porcupine = pvporcupine.create(
  access_key='uKVGjlcc6FVYNWNilRlTJtcN7xHKnVjfoCHAXtlWjuNUfGueGeAoww==',
  keyword_paths=["/home/iot/prj/Hey-Navi_en_raspberry-pi_v3_0_0.ppn"]
)

navigation_process = None  
# -----------------------
# Audio Recording
# -----------------------

def listen_for_wake_word():
    """
    Block until the Porcupine wake word is detected.
    Uses a low level RawInputStream so we get int16 PCM for Porcupine.
    """
    print("[wake] Say 'Hey Navi' to wake me up...")

    try:
        with sd.RawInputStream(
            samplerate=porcupine.sample_rate,
            blocksize=porcupine.frame_length,
            channels=1,
            dtype='int16'
        ) as stream:
            while True:
                pcm_bytes, _ = stream.read(porcupine.frame_length)
                pcm = np.frombuffer(pcm_bytes, dtype=np.int16)

                keyword_index = porcupine.process(pcm)
                if keyword_index >= 0:
                    print("[wake] Wake word detected.")
                    return
    except Exception as e:
        print("[wake] Error in wake word loop:", e)
        traceback.print_exc()


def record_audio_block(duration=LISTEN_SECONDS, samplerate=SAMPLE_RATE, channels=CHANNELS):
    """
    Record audio from the default microphone for a fixed duration.
    Returns a NumPy float32 array at the given sample rate.
    """
    print(f"[audio] Recording for {duration} seconds...")
    audio = sd.rec(
        int(duration * samplerate),
        samplerate=samplerate,
        channels=channels,
        dtype='float32'
    )
    sd.wait()
    audio = np.squeeze(audio)  # shape (samples,)
    print("[audio] Recording complete.")
    return audio


# -----------------------
# Whisper STT
# -----------------------

class STTWhisper:
    def __init__(self, model_name=WHISPER_MODEL_NAME):
        print(f"[whisper] Loading model '{model_name}'...")
        self.model = whisper.load_model(model_name)
        print("[whisper] Model loaded.")

    def transcribe(self, audio, sample_rate=SAMPLE_RATE):
        """
        Transcribe an audio array using Whisper.
        """
        print("[whisper] Transcribing audio...")
        # Whisper expects audio at 16kHz float32. We already record that way.
        result = self.model.transcribe(audio, fp16=False, language='en', task='transcribe')
        text = result.get("text", "").strip()
        print(f"[whisper] Transcription: {text!r}")
        return text


# -----------------------
# TTS
# -----------------------

class TextToSpeech:
    def __init__(self):
        print("[tts] Initializing TTS engine...")
        self.engine = pyttsx3.init()
        # Optionally tweak voice rate or volume here
        # self.engine.setProperty("rate", 160)
        # self.engine.setProperty("volume", 1.0)
        print("[tts] TTS engine ready.")

    def speak(self, text):
        if not text:
            return
        print(f"[assistant] {text}")
        self.engine.say(text)
        self.engine.runAndWait()


# -----------------------
# LLM via Ollama
# -----------------------

def call_ollama_chat(messages, model=OLLAMA_MODEL, url=OLLAMA_URL):
    """
    Call Ollama chat endpoint with a list of messages.
    messages: [{"role": "system" | "user" | "assistant", "content": "..."}]
    Returns the assistant text.
    """
    payload = {
        "model": model,
        "messages": messages,
        "stream": False
    }
    print("[ollama] Sending request to LLM...")
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    # Ollama typical response structure:
    # {"message": {"role": "assistant", "content": "..."}, ...}
    message = data.get("message", {})
    content = message.get("content", "")
    print(f"[ollama] Raw response: {content[:200]!r}")
    return content

async def get_llm_response(user_text: str):
    system_msg = fp.ProtocolMessage(role="system", content=SYSTEM_PROMPT)
    user_msg = fp.ProtocolMessage(role="user", content=user_text)

    full_response = ""
    async for partial in fp.get_bot_response(
        messages=[system_msg, user_msg],
        bot_name='GPT-4o-Mini',
        api_key=POE_API_KEY,
    ):
        full_response += partial.text

    return full_response


def parse_llm_json(raw_text):
    """
    Try to parse the LLM response as JSON with the fields:
    mode, reply, tool, arguments

    If parsing fails or fields are missing, fall back to a simple reply mode.
    """
    def strip_code_fences(s: str) -> str:
        s = s.strip()
        if s.startswith("```") and s.endswith("```"):
            # Remove the outer ```
            s = s[3:-3].strip()
            # Optional "json" or "JSON" language tag at the start
            if s.lower().startswith("json"):
                s = s[4:].strip()
        return s

    try:
        cleaned = strip_code_fences(raw_text)
        obj = json.loads(cleaned)

        mode = obj.get("mode", "reply")
        reply = obj.get("reply", "")
        tool = obj.get("tool", None)
        arguments = obj.get("arguments", None)

        if mode not in ("reply", "tool_call"):
            mode = "reply"
        if reply is None:
            reply = ""
        return {
            "mode": mode,
            "reply": reply,
            "tool": tool,
            "arguments": arguments,
        }
    except Exception as e:
        print("[parse] Failed to parse JSON tool call, falling back to plain reply.")
        print("[parse] Error:", e)
        return {
            "mode": "reply",
            "reply": raw_text,
            "tool": None,
            "arguments": None,
        }


# -----------------------
# Navigation tool stub
# -----------------------

def call_navigation_tool(arguments):
    global navigation_process
    """
    Stub for your navigation integration.

    arguments is expected to be a dict with keys like:
        {
          "destination": "kitchen",
          "mode": "walking"
        }

    You should replace this with the real interface to your
    navigation script, for example:
    - HTTP request to your navigation service
    - MQTT publish
    - Writing to a message queue or file
    """
    print("[tool:navigation] Called with arguments:", arguments)

    # Example: pretend we call some navigation API here
    # You will implement this depending on how your nav process works.
    destination = None
    mode = None

    if isinstance(arguments, dict):
        destination = arguments.get("destination")
        mode = arguments.get("mode")
        params = {
            "q": destination,
            "api_key": GEOCODE_API_KEY
        }
        response = requests.get("https://geocode.maps.co/search", params=params)
        response.raise_for_status()  # raises error if request failed
        data = response.json()

        if not data:
            return None, None

        lat, lon = float(data[0]["lat"]), float(data[0]["lon"])

    # If a previous navigation process is running, you may want to stop it
    if navigation_process is not None and navigation_process.poll() is None:
        print("[tool:navigation] Stopping previous navigation process")
        navigation_process.terminate()
        # Optionally wait or kill if needed

    # Start navigation.py as a background process
    cmd = ["python3", "/home/iot/prj/GPS_Module/navigation.py", str(lat), str(lon)]
    print("[tool:navigation] Starting navigation subprocess:", cmd)

    navigation_process = subprocess.Popen(cmd)

    # For now, we just log it. Replace with real integration.
    print(f"[tool:navigation] Go to destination={destination!r} mode={mode!r}")

    # Optionally return some status if you want to feed it back to the user.
    return {"status": "ok", "destination": destination, "mode": mode}


# -----------------------
# Main voice assistant loop
# -----------------------

def run_voice_assistant():
    stt = STTWhisper(WHISPER_MODEL_NAME)
    tts = TextToSpeech()

    print()
    print("Voice assistant ready.")
    print("Say 'Hey Navi' to start talking. Ctrl+C to quit.")
    print()

    while True:
        # 0) wait for wake word
        listen_for_wake_word()

        # 1) record audio after wake word
        audio = record_audio_block()

        # 2) speech to text
        try:
            text = stt.transcribe(audio)
        except Exception as e:
            print("[error] STT failed:", e)
            traceback.print_exc()
            tts.speak("Sorry, I could not understand you.")
            continue

        if not text:
            tts.speak("I did not hear anything useful. Please try again.")
            continue

        # 3) call LLM with tool instructions
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ]

        try:
            raw_response = asyncio.run(get_llm_response(text))
        except Exception as e:
            print("[error] LLM call failed:", e)
            traceback.print_exc()
            tts.speak("Sorry, I am having trouble thinking right now.")
            continue

        parsed = parse_llm_json(raw_response)
        mode = parsed["mode"]
        reply_text = parsed["reply"]
        tool = parsed["tool"]
        arguments = parsed["arguments"]

        if mode == "tool_call" and tool == "navigation":
            print("[main] LLM requested navigation tool.")
            try:
                result = call_navigation_tool(arguments)
            except Exception as e:
                print("[error] Navigation tool failed:", e)
                traceback.print_exc()
                reply_text = reply_text + " However, there was an error starting navigation."

        tts.speak(reply_text)



if __name__ == "__main__":
    try:
        run_voice_assistant()
    except KeyboardInterrupt:
        print("\n[main] Interrupted by user. Bye.")
    finally:
        if porcupine is not None:
            porcupine.delete()

