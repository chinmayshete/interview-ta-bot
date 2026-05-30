import pyaudiowpatch as pyaudio
import time

def test_loopback_blocking():
    p = pyaudio.PyAudio()
    wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
    
    if not default_speakers["isLoopbackDevice"]:
        for loopback in p.get_loopback_device_info_generator():
            if default_speakers["name"] in loopback["name"]:
                default_speakers = loopback
                break
                
    print(f"Using device: {default_speakers['name']}")
    
    stream = p.open(format=pyaudio.paInt16,
                    channels=default_speakers["maxInputChannels"],
                    rate=int(default_speakers["defaultSampleRate"]),
                    frames_per_buffer=1024,
                    input=True,
                    input_device_index=default_speakers["index"])
                    
    print("Listening for 5 seconds in blocking mode...")
    frames = []
    
    # Try reading 50 chunks
    for i in range(50):
        try:
            data = stream.read(1024, exception_on_overflow=False)
            frames.append(data)
        except Exception as e:
            print("Error reading:", e)
            
    stream.stop_stream()
    stream.close()
    p.terminate()
    
    print(f"Captured {len(frames)} frames")

if __name__ == "__main__":
    test_loopback_blocking()
