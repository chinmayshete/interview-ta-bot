"""
Audio router — handles stealth WASAPI loopback capture on Windows.
"""

import os
import wave
import asyncio
from fastapi import APIRouter, HTTPException
import pyaudiowpatch as pyaudio

from services import session_manager
from services.transcription import transcribe_audio

router = APIRouter(prefix="/api/audio", tags=["audio"])

# Global state for the background recorder
recorder_state = {
    "is_recording": False,
    "frames": [],
    "pya": None,
    "stream": None
}

@router.post("/start-loopback/{session_id}")
async def start_loopback(session_id: str):
    """Start recording system audio secretly via WASAPI Loopback."""
    if recorder_state["is_recording"]:
        raise HTTPException(status_code=400, detail="Already recording.")
        
    state = session_manager.get_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found.")

    try:
        p = pyaudio.PyAudio()
        
        # Get WASAPI default loopback device
        wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
        
        if not default_speakers["isLoopbackDevice"]:
            for loopback in p.get_loopback_device_info_generator():
                if default_speakers["name"] in loopback["name"]:
                    default_speakers = loopback
                    break
        
        recorder_state["pya"] = p
        recorder_state["frames"] = []
        recorder_state["is_recording"] = True
        
        def callback(in_data, frame_count, time_info, status):
            recorder_state["frames"].append(in_data)
            return (in_data, pyaudio.paContinue)

        stream = p.open(format=pyaudio.paInt16,
                        channels=default_speakers["maxInputChannels"],
                        rate=int(default_speakers["defaultSampleRate"]),
                        frames_per_buffer=4096,  # Used to be 2, which crashes the callback
                        input=True,
                        input_device_index=default_speakers["index"],
                        stream_callback=callback)
                        
        recorder_state["stream"] = stream
        recorder_state["sample_rate"] = int(default_speakers["defaultSampleRate"])
        recorder_state["channels"] = default_speakers["maxInputChannels"]
        
    except Exception as e:
        recorder_state["is_recording"] = False
        raise HTTPException(status_code=500, detail=f"Failed to bind loopback (Stereo Mix might be disabled): {e}")
        
    return {"status": "started", "device": default_speakers["name"]}


@router.post("/stop-loopback/{session_id}")
async def stop_loopback(session_id: str, transcribe: bool = True):
    """Stop recording system audio and transcribe it via Azure."""
    if not recorder_state["is_recording"]:
        if not transcribe:
            return {"status": "already_stopped"}
        raise HTTPException(status_code=400, detail="Not recording.")
        
    recorder_state["is_recording"] = False
    stream = recorder_state["stream"]
    p = recorder_state["pya"]
    
    if stream:
        stream.stop_stream()
        stream.close()
    if p:
        p.terminate()
        
    frames = recorder_state["frames"]
    
    if not transcribe:
        return {"status": "aborted"}
        
    if not frames:
        raise HTTPException(status_code=400, detail="No audio was captured. Make sure audio is playing on your system.")
    
    # Save to a temporary WAV file
    temp_wav = f"temp_loopback_{session_id}.wav"
    wf = wave.open(temp_wav, 'wb')
    wf.setnchannels(recorder_state["channels"])
    wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
    wf.setframerate(recorder_state["sample_rate"])
    wf.writeframes(b''.join(frames))
    wf.close()
    
    # Transcribe
    try:
        with open(temp_wav, "rb") as f:
            audio_bytes = f.read()
        text = await transcribe_audio(audio_bytes, filename="audio.wav")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")
    finally:
        if os.path.exists(temp_wav):
            os.remove(temp_wav)
            
    return {"session_id": session_id, "text": text}
