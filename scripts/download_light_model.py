import os
import sys
import requests

# Model and mmproj URLs from bartowski/Qwen2-VL-2B-Instruct-GGUF
MODEL_URL = "https://huggingface.co/bartowski/Qwen2-VL-2B-Instruct-GGUF/resolve/main/Qwen2-VL-2B-Instruct-Q4_K_M.gguf"
MMPROJ_URL = "https://huggingface.co/bartowski/Qwen2-VL-2B-Instruct-GGUF/resolve/main/mmproj-Qwen2-VL-2B-Instruct-f16.gguf"
QWEN_05B_URL = "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf"

models_dir = r"d:\Smart Manufacturing Blueprint Analyzer\models"
if not os.path.exists(models_dir):
    os.makedirs(models_dir)

def download_file_chunked(url, filename):
    target_path = os.path.join(models_dir, filename)
    
    # Check remote size first
    print(f"Checking remote size for {filename}...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        with requests.get(url, headers=headers, stream=True, timeout=10) as response:
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))
    except Exception as e:
        print(f"Failed to check remote size for {filename}: {e}")
        total_size = 0

    # Check if file exists and verify size
    if os.path.exists(target_path):
        local_size = os.path.getsize(target_path)
        if local_size == 0:
            print(f"Removing 0-byte file: {filename}")
            os.remove(target_path)
        elif total_size > 0 and local_size < total_size:
            print(f"File {filename} is incomplete (Local: {local_size}, Remote: {total_size}). Removing and redownloading...")
            os.remove(target_path)
        elif total_size > 0 and local_size == total_size:
            print(f"File {filename} already exists and matches remote size. Skipping.")
            return
        elif local_size > 0:
            print(f"File {filename} exists (Size: {local_size}). Skipping (Remote size check was inconclusive or matched).")
            return
    
    print(f"Downloading {filename} from {url}...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        with requests.get(url, headers=headers, stream=True) as response:
            response.raise_for_status()  # Raise an exception for HTTP errors
            total_size = int(response.headers.get('content-length', 0))
            
            with open(target_path, 'wb') as out_file:
                chunk_size = 1024 * 64  # 64KB chunks
                downloaded = 0
                
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        out_file.write(chunk)
                        downloaded += len(chunk)
                        if downloaded % (1024 * 1024 * 10) < chunk_size:  # Every ~10MB
                            print(f"[{filename}] Downloaded {downloaded / (1024*1024):.2f} MB...", end='\r')
                print()
        
        # Verify download complete
        if os.path.exists(target_path):
            final_size = os.path.getsize(target_path)
            if total_size > 0 and final_size < total_size:
                print(f"Warning: Download incomplete! Expected {total_size} bytes, got {final_size} bytes.")
                os.remove(target_path)
                return
            print(f"Successfully downloaded {filename} (Size: {final_size / (1024*1024):.2f} MB)")
    except Exception as e:
        print(f"Failed to download {filename}: {e}")
        # Clean up partial file
        if os.path.exists(target_path):
            os.remove(target_path)

if __name__ == "__main__":
    download_file_chunked(QWEN_05B_URL, "qwen2.5-0.5b-instruct-q4_k_m.gguf")
    download_file_chunked(MODEL_URL, "Qwen2-VL-2B-Instruct-Q4_K_M.gguf")
    download_file_chunked(MMPROJ_URL, "mmproj-Qwen2-VL-2B-Instruct-f16.gguf")
