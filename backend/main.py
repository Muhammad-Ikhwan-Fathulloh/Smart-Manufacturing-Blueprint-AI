import os
import io
import subprocess
import threading
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

# ---------------------------------------------------------------------------
# CPU tuning
# ---------------------------------------------------------------------------
# Jangan biarkan llama.cpp "menebak" jumlah thread sendiri. Di Windows, auto
# detect kadang ikut menghitung hyperthread/E-core yang bikin context-switch
# overhead lebih besar dari manfaatnya. Kita set manual:
CPU_COUNT = os.cpu_count() or 4
VISION_THREADS = max(1, CPU_COUNT - 1)        # model 2B + image encoder, butuh tenaga lebih
REASON_THREADS = max(1, min(4, CPU_COUNT))    # model 0.5B, sudah cepat dengan sedikit thread

# Resize gambar sebelum dikirim ke vision model. Ini adalah satu perubahan
# paling berdampak untuk CPU: biaya vision encoder ~proporsional dengan
# jumlah pixel, jadi foto kamera HP (3000-4000px) bisa 5-10x lebih lambat
# diproses dibanding versi yang sudah di-resize ke 1024px, dengan hasil baca
# blueprint yang nyaris tidak berbeda.
IMAGE_MAX_DIMENSION = 1024
IMAGE_JPEG_QUALITY = 82

# Global Instances
vision_server = None
reason_server = None


def optimize_image_for_inference(image_path: str) -> bytes:
    """
    Resize + compress gambar sebelum di-encode ke base64 untuk vision model.
    Mengembalikan bytes JPEG yang sudah dioptimasi.
    """
    try:
        resample = Image.Resampling.LANCZOS  # Pillow >= 9.1
    except AttributeError:
        resample = Image.LANCZOS  # Pillow lama

    with Image.open(image_path) as img:
        # Normalisasi mode warna (handle PNG transparan, scan CMYK, grayscale, dll)
        if img.mode != "RGB":
            img = img.convert("RGB")

        w, h = img.size
        scale = min(1.0, IMAGE_MAX_DIMENSION / max(w, h))
        if scale < 1.0:
            new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
            img = img.resize(new_size, resample)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=IMAGE_JPEG_QUALITY, optimize=True)
        return buffer.getvalue()


class PersistentGGUFServer:
    def __init__(self, name: str, model_path: str, port: int, mmproj_path: str = None,
                 threads: int = 4, ctx_size: int = 2048, startup_timeout: int = 60):
        self.name = name
        self.model_path = model_path
        self.port = port
        self.mmproj_path = mmproj_path
        self.threads = threads
        self.ctx_size = ctx_size
        self.startup_timeout = startup_timeout
        self.process = None
        self.ready = False
        self._log_thread = None
        # Server hanya punya 1 slot decode (--parallel 1). Lock ini memastikan
        # request dari FastAPI tidak ditembak bersamaan ke slot yang sama --
        # request kedua akan menunggu rapi di sini, bukan menumpuk error di
        # sisi llama-server.
        self.lock = asyncio.Lock()

    def start(self):
        if not os.path.exists(self.model_path):
            print(f"[{self.name}] ERROR: Model not found: {self.model_path}")
            return False

        cmd = [
            LLAMA_SERVER_EXE,
            "-m", self.model_path,
            "--port", str(self.port),
            "-c", str(self.ctx_size),
            "--parallel", "1",          # 1 slot saja, hemat memori & hindari kontensi CPU
            "--n-gpu-layers", "0",      # paksa CPU
            "--threads", str(self.threads),
            "--threads-batch", str(self.threads),
            "--no-warmup",              # skip dummy inference saat startup -> ready lebih cepat
            "--no-perf",                 # kurangi log timing internal -> kurangi tekanan ke pipe stdout
        ]

        if self.mmproj_path:
            if os.path.exists(self.mmproj_path):
                cmd.extend(["--mmproj", self.mmproj_path])
                print(f"[{self.name}] Using mmproj: {self.mmproj_path}")
            else:
                print(f"[{self.name}] WARNING: MMProj not found: {self.mmproj_path}")

        print(f"[{self.name}] Starting server on port {self.port} (threads={self.threads}) "
              f"with command: {' '.join(cmd)}")
        self.process = subprocess.Popen(
            cmd,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        # PENTING: kuras stdout llama-server terus-menerus di background.
        # Kalau tidak dibaca, pipe buffer Windows (~64KB) akan penuh begitu
        # llama-server mulai mencetak log saat memproses request, dan
        # llama-server akan BLOCK saat menulis log berikutnya -- dari luar
        # ini terlihat seperti "hang"/timeout, padahal sebenarnya proses
        # cuma macet menunggu pipe dikosongkan.
        self._log_thread = threading.Thread(target=self._drain_output, daemon=True)
        self._log_thread.start()

        # Wait for ready. Model loading -- terutama yang punya mmproj/vision --
        # bisa jauh lebih lama dari 20 detik di disk/CPU yang pelan, jadi beri
        # waktu lebih panjang dan log progress supaya jelas masih hidup, bukan macet.
        max_wait = self.startup_timeout
        print(f"[{self.name}] Waiting for server to become ready (max {max_wait}s)...")
        for i in range(max_wait):
            try:
                with httpx.Client(timeout=2.0) as client:
                    resp = client.get(f"http://localhost:{self.port}/health")
                    if resp.status_code == 200:
                        print(f"[{self.name}] Server is ready and listening on http://localhost:{self.port}")
                        self.ready = True
                        return True
            except Exception:
                pass  # server belum mulai listen, normal di awal-awal

            if self.process.poll() is not None:
                print(f"[{self.name}] ERROR: Server process exited early (code {self.process.poll()}). "
                      f"Lihat baris log [{self.name}-srv] di atas untuk alasannya.")
                return False

            if i > 0 and i % 10 == 0:
                print(f"[{self.name}] Still loading model... ({i}s elapsed, max {max_wait}s)")
            time.sleep(1)

        # If we got here, timeout -- proses masih hidup, kemungkinan masih loading.
        # Jangan matikan; biarkan generate_chat() yang akan retry saat dipanggil nanti.
        print(f"[{self.name}] WARNING: Server not ready within {max_wait}s, but process is still alive. "
              f"It may still be loading -- requests will retry automatically.")
        return False

    def _drain_output(self):
        """Terus membaca stdout llama-server sepanjang hidup proses, agar
        pipe buffer tidak penuh dan menyebabkan proses macet saat menulis log."""
        try:
            for line in self.process.stdout:
                line = line.rstrip()
                if line:
                    print(f"[{self.name}-srv] {line}")
        except Exception:
            pass

    def stop(self):
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

    async def generate_chat(self, messages: list, max_tokens: int = 512):
        url = f"http://localhost:{self.port}/v1/chat/completions"
        payload = {
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": max_tokens,  # batasi panjang output -> batasi worst-case waktu CPU
        }
        max_retries = 30      # toleransi ~60s tambahan kalau model masih loading
        retry_delay = 2.0
        # Pisahkan connect timeout (harus instan, localhost) dari read timeout
        # (inference CPU bisa lama) -- biar gampang diagnosa kalau yang macet
        # ternyata koneksinya, bukan proses generate-nya.
        timeout = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)

        # Serialize: server ini cuma punya 1 slot decode, jadi request kedua
        # harus antri di sini, bukan dikirim bersamaan dan bikin llama-server kelimpungan.
        async with self.lock:
            async with httpx.AsyncClient(timeout=timeout) as client:
                for attempt in range(max_retries):
                    try:
                        resp = await client.post(url, json=payload)
                        data = resp.json()

                        # Model masih loading di background ("Loading model", 503) ->
                        # tunggu sebentar dan coba lagi, jangan langsung lempar error ke user.
                        if resp.status_code == 503:
                            print(f"[{self.name}] Model still loading (attempt {attempt + 1}/{max_retries}), retrying...")
                            self.ready = False
                            await asyncio.sleep(retry_delay)
                            continue

                        self.ready = True
                        print(f"[{self.name}] Response Status: {resp.status_code}")
                        if "choices" not in data:
                            print(f"[{self.name}] ERROR: Unexpected response body: {data}")
                            raise HTTPException(status_code=500, detail=f"LLM Server Error ({self.name}): {data}")
                        return data["choices"][0]["message"]["content"]

                    except HTTPException:
                        raise
                    except Exception as e:
                        print(f"[{self.name}] Request Failed: {e}")
                        raise HTTPException(status_code=500, detail=f"Request to {self.name} failed: {e}")

                # Sudah dicoba berkali-kali dan masih loading -> baru di sini menyerah
                raise HTTPException(
                    status_code=503,
                    detail=f"{self.name} server is still loading the model. Please try again in a moment."
                )


@app.on_event("startup")
async def startup_event():
    global vision_server, reason_server

    # 1. Start Vision Engine (Qwen2-VL)
    vision_model = os.path.join(MODELS_DIR, QWEN_VL_GGUF)
    vision_mmproj = os.path.join(MODELS_DIR, QWEN_VL_MMPROJ)
    vision_server = PersistentGGUFServer(
        "Vision", vision_model, 8080, vision_mmproj,
        threads=VISION_THREADS, ctx_size=2048, startup_timeout=120,  # mmproj bikin loading lebih lama
    )
    vision_server.start()

    # 2. Start Reasoning Engine (Qwen 0.5B)
    reason_model = os.path.join(MODELS_DIR, QWEN_REASON_GGUF)
    reason_server = PersistentGGUFServer(
        "Reasoning", reason_model, 8081,
        threads=REASON_THREADS, ctx_size=1536, startup_timeout=30,  # model kecil, ctx lebih kecil cukup & lebih ringan
    )
    reason_server.start()


@app.on_event("shutdown")
def shutdown_event():
    if vision_server: vision_server.stop()
    if reason_server: reason_server.stop()


class AnalysisRequest(BaseModel):
    image_path: str = None
    user_text: str = ""
    vision_data: str = ""  # For second stage
    prompt: str = "Lakukan analisis mendalam pada gambar teknik ini. Sebutkan komponen (nama, spesifikasi, jumlah), deteksi anomali jika ada, dan berikan rekomendasi teknis."


@app.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"image_path": file_path, "status": "success"}


@app.post("/analyze/vlm")
async def analyze_vlm(request: AnalysisRequest):
    """Tahap 1: Hanya menjalankan Vision (VLM)"""
    try:
        if not request.image_path or not os.path.exists(request.image_path):
            raise HTTPException(status_code=400, detail="Image path valid is required.")

        optimized_bytes = optimize_image_for_inference(request.image_path)
        base64_image = base64.b64encode(optimized_bytes).decode('utf-8')

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": request.prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]
            }
        ]
        vision_output = await vision_server.generate_chat(messages, max_tokens=500)
        return {"vision_raw": vision_output, "status": "success"}

    except HTTPException: raise
    except Exception as e:
        print(f"[VLM] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze/llm")
async def analyze_llm(request: AnalysisRequest):
    """Tahap 2: Hanya menjalankan Reasoning (LLM) berdasarkan data VLM"""
    try:
        if not request.vision_data:
            raise HTTPException(status_code=400, detail="Vision data is required for LLM stage.")

        reason_messages = [
            {"role": "system", "content": "You are a professional manufacturing engineer. Process the vision data and format it into a professional technical report in Indonesian."},
            {"role": "user", "content": f"Vision Data: {request.vision_data}\nUser Request: {request.user_text}\nFormat as a structured technical report."}
        ]
        final_report = await reason_server.generate_chat(reason_messages, max_tokens=800)
        return {"analysis": final_report, "status": "success"}

    except HTTPException: raise
    except Exception as e:
        print(f"[LLM] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze")
async def analyze(request: AnalysisRequest):
    """Combined endpoint (Backward compatibility or legacy heavy flow)"""
    try:
        vlm_result = await analyze_vlm(request)
        request.vision_data = vlm_result["vision_raw"]
        llm_result = await analyze_llm(request)
        return {
            "analysis": llm_result["analysis"],
            "vision_raw": vlm_result["vision_raw"],
            "status": "success"
        }
    except HTTPException: raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)