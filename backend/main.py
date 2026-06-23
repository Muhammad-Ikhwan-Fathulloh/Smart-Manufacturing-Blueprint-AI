import os
import subprocess
import time
import httpx
import shutil
import asyncio
import base64
from fastapi import FastAPI, HTTPException, File, UploadFile
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

app = FastAPI(title="Smart Manufacturing AI (Ultra-High Performance GGUF Mode)")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(os.path.dirname(BASE_DIR), "models")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
BIN_DIR = os.path.join(BASE_DIR, "bin")

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# Config
QWEN_VL_GGUF = "Qwen2-VL-2B-Instruct-Q4_K_M.gguf"
QWEN_VL_MMPROJ = "mmproj-Qwen2-VL-2B-Instruct-f16.gguf"
QWEN_REASON_GGUF = "qwen2.5-0.5b-instruct-q4_k_m.gguf"
LLAMA_SERVER_EXE = os.path.join(BIN_DIR, "llama-server.exe")

# Global Instances
vision_server = None
reason_server = None

class PersistentGGUFServer:
    def __init__(self, name: str, model_path: str, port: int, mmproj_path: str = None):
        self.name = name
        self.model_path = model_path
        self.port = port
        self.mmproj_path = mmproj_path
        self.process = None

    def start(self):
        if not os.path.exists(self.model_path):
            print(f"[{self.name}] ERROR: Model not found: {self.model_path}")
            return False
            
        cmd = [
            LLAMA_SERVER_EXE,
            "-m", self.model_path,
            "--port", str(self.port),
            "-c", "2048",
            "--n-gpu-layers", "0"  # Force CPU
        ]
        
        if self.mmproj_path:
            if os.path.exists(self.mmproj_path):
                cmd.extend(["--mmproj", self.mmproj_path])
            else:
                print(f"[{self.name}] WARNING: MMProj not found: {self.mmproj_path}")

        print(f"[{self.name}] Starting server on port {self.port}...")
        self.process = subprocess.Popen(
            cmd, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        # Wait for ready
        for i in range(20):
            try:
                with httpx.Client() as client:
                    resp = client.get(f"http://localhost:{self.port}/health")
                    if resp.status_code == 200:
                        print(f"[{self.name}] Server ready.")
                        return True
            except:
                pass
            time.sleep(1)
        return False

    def stop(self):
        if self.process:
            self.process.terminate()

    async def generate_chat(self, messages: list):
        url = f"http://localhost:{self.port}/v1/chat/completions"
        payload = {
            "messages": messages,
            "temperature": 0.2
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)
            return resp.json()["choices"][0]["message"]["content"]

@app.on_event("startup")
async def startup_event():
    global vision_server, reason_server
    
    # 1. Start Vision Engine (Qwen2-VL)
    vision_model = os.path.join(MODELS_DIR, QWEN_VL_GGUF)
    vision_mmproj = os.path.join(MODELS_DIR, QWEN_VL_MMPROJ)
    vision_server = PersistentGGUFServer("Vision", vision_model, 8080, vision_mmproj)
    vision_server.start()

    # 2. Start Reasoning Engine (Qwen 0.5B)
    reason_model = os.path.join(MODELS_DIR, QWEN_REASON_GGUF)
    reason_server = PersistentGGUFServer("Reasoning", reason_model, 8081)
    reason_server.start()

@app.on_event("shutdown")
def shutdown_event():
    if vision_server: vision_server.stop()
    if reason_server: reason_server.stop()

class AnalysisRequest(BaseModel):
    image_path: str = None
    user_text: str = ""
    prompt: str = "Describe this industrial blueprint in detail, listing components and materials."

@app.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"image_path": file_path, "status": "success"}

@app.post("/analyze")
async def analyze(request: AnalysisRequest):
    try:
        vision_output = ""
        if request.image_path and os.path.exists(request.image_path):
            # Encode image to base64 for GGUF Server
            with open(request.image_path, "rb") as f:
                base64_image = base64.b64encode(f.read()).decode('utf-8')
            
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": request.prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ]
            vision_output = await vision_server.generate_chat(messages)

        # Step 2: Reasoning (Refine output)
        reason_messages = [
            {"role": "system", "content": "You are a professional manufacturing engineer."},
            {"role": "user", "content": f"Vision Data: {vision_output}\nUser Request: {request.user_text}\nFormat as a technical report."}
        ]
        final_report = await reason_server.generate_chat(reason_messages)

        return {
            "analysis": final_report,
            "vision_raw": vision_output,
            "status": "success"
        }

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
