import urllib.request
import os
import sys

# Model and mmproj URLs from bartowski/Qwen2-VL-2B-Instruct-GGUF
MODEL_URL = "https://huggingface.co/bartowski/Qwen2-VL-2B-Instruct-GGUF/resolve/main/Qwen2-VL-2B-Instruct-Q4_K_M.gguf"
MMPROJ_URL = "https://huggingface.co/bartowski/Qwen2-VL-2B-Instruct-GGUF/resolve/main/mmproj-Qwen2-VL-2B-Instruct-f16.gguf"
QWEN_05B_URL = "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf"

models_dir = r"d:\Smart Manufacturing Blueprint Analyzer\models"
if not os.path.exists(models_dir):
    os.makedirs(models_dir)

def download_file_chunked(url, filename):
    target_path = os.path.join(models_dir, filename)
    
    # Check if 0-byte file exists and delete it
    if os.path.exists(target_path) and os.path.getsize(target_path) == 0:
        os.remove(target_path)

    if os.path.exists(target_path):
        print(f"File {filename} already exists and is non-zero size. Skipping.")
        return
    
    print(f"Downloading {filename} from {url}...")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            with open(target_path, 'wb') as out_file:
                chunk_size = 1024 * 64  # 64KB chunks
                downloaded = 0
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    # print periodically
                    if downloaded % (1024 * 1024 * 10) < chunk_size: # every 10MB approx
                        print(f"[{filename}] Downloaded {downloaded / (1024*1024):.2f} MB...", end='\r')
        print(f"\nSuccessfully downloaded {filename}")
    except Exception as e:
        print(f"Failed to download {filename}: {e}")
        # Clean up partial file on failure if it's 0-byte
        if os.path.exists(target_path) and os.path.getsize(target_path) == 0:
            os.remove(target_path)

if __name__ == "__main__":
    download_file_chunked(QWEN_05B_URL, "qwen2.5-0.5b-instruct-q4_k_m.gguf")
    download_file_chunked(MODEL_URL, "Qwen2-VL-2B-Instruct-Q4_K_M.gguf")
    download_file_chunked(MMPROJ_URL, "mmproj-Qwen2-VL-2B-Instruct-f16.gguf")
