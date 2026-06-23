# Smart Manufacturing Blueprint Analyzer

A local, privacy-first AI system for analyzing technical drawings and manufacturing blueprints. Powered by a **Dual-Engine GGUF** architecture for ultra-fast, CPU-optimized inference with minimal memory footprint.

## 🚀 Key Features
- **Dual-Engine Orchestrator**:
  - **Vision Engine** — Qwen2-VL 2B (GGUF) with multimodal projector (`mmproj`) for deep visual extraction from technical drawings.
  - **Reasoning Engine** — Qwen 2.5 0.5B (GGUF) for structuring raw visual data into professional manufacturing reports.
- **Ultra-Lightweight** — No `torch` or `transformers` required. The entire ML stack runs via native `llama-server.exe` binaries (~2 GB total RAM).
- **Modern Glassmorphism UI** — Clean, responsive, and premium web interface built with Bootstrap 5.
- **Privacy First** — All data is processed locally. No cloud dependency.

## 📂 Project Structure
```text
/
├── backend/
│   ├── bin/             # Native inference binaries (llama-server.exe)
│   ├── uploads/         # Temporary upload directory
│   ├── main.py          # FastAPI orchestrator (Dual-Engine)
│   └── requirements.txt
├── frontend/
│   └── index.html       # Web interface
├── models/              # GGUF model weights & vision projector
├── scripts/
│   └── download_light_model.py
└── README.md
```

## 🛠️ Setup & Installation

1.  **Create Virtual Environment:**
    ```powershell
    cd backend
    python -m venv venv
    .\venv\Scripts\activate
    ```

2.  **Install Dependencies (lightweight):**
    ```powershell
    pip install -r requirements.txt
    ```

3.  **Download Model Weights:**
    Run the automated download script to fetch the Vision and Reasoning GGUF models:
    ```powershell
    python ../scripts/download_light_model.py
    ```
    This downloads three files into the `models/` directory:
    - `qwen2.5-0.5b-instruct-q4_k_m.gguf` (~468 MB)
    - `Qwen2-VL-2B-Instruct-Q4_K_M.gguf` (~1.5 GB)
    - `mmproj-Qwen2-VL-2B-Instruct-f16.gguf` (~1.2 GB)

## 🖥️ Running the Application

Start the FastAPI backend — both GGUF engines are managed automatically in the background:

```powershell
cd backend
.\venv\Scripts\activate
uvicorn main:app --reload
```

Then open `frontend/index.html` in your browser.

## 📝 How It Works
1. **Upload** a technical blueprint or engineering drawing.
2. **Provide instructions** (optional) to focus the analysis on specific components or materials.
3. **Get results** — the Vision Engine extracts visual details, and the Reasoning Engine compiles them into a structured technical report.

## ⚖️ License
MIT License