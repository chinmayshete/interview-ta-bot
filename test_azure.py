import asyncio
import httpx
from dotenv import load_dotenv
import os
import io
import wave

# Load variables directly from your .env file
load_dotenv()

async def test_azure_stt():
    endpoint = os.getenv("AZURE_STT_ENDPOINT")
    api_key = os.getenv("AZURE_STT_API_KEY")
    deployment = os.getenv("AZURE_STT_DEPLOYMENT")

    print(f"==========================================")
    print(f"Endpoint     : {endpoint}")
    print(f"Deployment   : {deployment}")
    # print(f"API Key      : {api_key[:5]}... (Length: {len(api_key)})")
    print(f"==========================================\n")

    # The standard header for Azure OpenAI is api-key
    headers = {
        "api-key": api_key,
    }
    
    # Generate a dummy 0.5-second audio file to satisfy Azure's 0.1s minimum requirement
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav_file:
        wav_file.setnchannels(1) # Mono
        wav_file.setsampwidth(2) # 2 bytes per sample (16-bit)
        wav_file.setframerate(16000) # 16kHz
        # 16000 samples/sec * 2 bytes/sample * 0.5 seconds = 16000 bytes
        wav_file.writeframes(b'\x00' * 16000) 
    
    dummy_wav = buffer.getvalue()

    files = {
        "file": ("test.wav", dummy_wav, "audio/wav"),
    }
    data = {
        "model": deployment,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            print("Sending test request to Azure...\n")
            response = await client.post(
                endpoint,
                headers=headers,
                files=files,
                data=data,
            )
            
            print(f"Response Status Code : {response.status_code}")
            
            # 200 means perfect! 
            # 400 means it reached the model but rejected the dummy audio (still proves the network mapped successfully).
            # 401 means Invalid API Key.
            # 404 means DeploymentNotFound (model is definitely missing or wrong base type).
            print(f"Response Body        : {response.text}")
            
    except Exception as e:
        print(f"Connection Exception: {e}")

if __name__ == "__main__":
    # Ensure event loop handles it gracefully on Windows
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_azure_stt())
