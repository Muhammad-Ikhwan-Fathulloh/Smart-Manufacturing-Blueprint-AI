const API = `${window.location.protocol}//${window.location.hostname}:8000`;

document.addEventListener('DOMContentLoaded', () => {
    // Elements
    const imageInput = document.getElementById('imageFile');
    const uploadZone = document.getElementById('uploadZone');
    const previewContainer = document.getElementById('previewContainer');
    const textInput = document.getElementById('textInput');
    const startBtn = document.getElementById('startBtn');
    const reasonBtn = document.getElementById('reasonBtn');
    const btnText = document.getElementById('btnText');
    const loader = document.getElementById('loader');
    const resultContent = document.getElementById('result-content');
    const statusBadge = document.getElementById('status-badge');
    const copyBtn = document.getElementById('copyBtn');

    let currentImagePath = null;
    let currentVisionData = null;

    // UI State Management
    const setUIState = (state, stage = 'vlm') => {
        if (state === 'loading') {
            const btn = stage === 'vlm' ? startBtn : reasonBtn;
            btn.disabled = true;
            if (stage === 'vlm') {
                btnText.textContent = "SEDANG MENGAMATI...";
                loader.style.display = 'block';
            } else {
                reasonBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Menyusun...';
            }
            statusBadge.className = 'status-badge status-loading';
            statusBadge.textContent = stage === 'vlm' ? 'Vision Analysis...' : 'Reasoning...';

            if (stage === 'vlm') {
                resultContent.innerHTML = `
                    <div class="placeholder-text">
                        <div class="loader mb-3" style="display:block; width:40px; height:40px; border-width:4px;"></div>
                        <p>AI sedang memindai blueprint...</p>
                    </div>
                `;
            }
        } else if (state === 'idle') {
            startBtn.disabled = false;
            reasonBtn.disabled = false;
            btnText.textContent = "Mulai Analisis AI";
            reasonBtn.innerHTML = '<i class="fas fa-magic"></i> Susun Laporan Teknis';
            loader.style.display = 'none';
            statusBadge.className = 'status-badge status-idle';
            statusBadge.textContent = 'System Standby';
        } else if (state === 'success') {
            startBtn.disabled = false;
            reasonBtn.disabled = false;
            btnText.textContent = "Mulai Analisis AI";
            reasonBtn.innerHTML = '<i class="fas fa-magic"></i> Susun Laporan Teknis';
            loader.style.display = 'none';
            statusBadge.className = 'status-badge status-success';
            statusBadge.textContent = stage === 'vlm' ? 'Vision Complete' : 'Report Ready';
        }
    };

    // Upload & Preview
    uploadZone.addEventListener('click', () => imageInput.click());

    imageInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = (e) => {
                previewContainer.innerHTML = `<img src="${e.target.result}" alt="Preview">`;
            };
            reader.readAsDataURL(file);
        }
    });

    // Stage 1: VLM Analysis
    startBtn.addEventListener('click', async (e) => {
        e.preventDefault();
        const imageFile = imageInput.files[0];
        if (!imageFile) {
            alert("Silakan pilih gambar blueprint terlebih dahulu.");
            return;
        }

        reasonBtn.classList.add('d-none');
        setUIState('loading', 'vlm');

        try {
            // Upload
            const formData = new FormData();
            formData.append('file', imageFile);
            const uploadRes = await fetch(`${API}/upload`, { method: 'POST', body: formData });
            if (!uploadRes.ok) throw new Error("Gagal mengunggah gambar.");
            const uploadData = await uploadRes.json();
            currentImagePath = uploadData.image_path;

            // VLM Scan
            const vlmRes = await fetch(`${API}/analyze/vlm`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image_path: currentImagePath })
            });
            if (!vlmRes.ok) throw new Error("VLM Analysis failed.");
            const vlmData = await vlmRes.json();
            currentVisionData = vlmData.vision_raw;

            // Show Raw Output
            resultContent.innerHTML = `
                <div class="vlm-report">
                    <h3 style="margin-top:0"><i class="fas fa-eye"></i> Hasil Observasi Visual</h3>
                    <p>${currentVisionData}</p>
                    <div style="background:#f8fafc; padding:1rem; border-radius:12px; font-size:0.85rem; color:var(--text-muted); margin-top:1.5rem;">
                        <i class="fas fa-info-circle"></i> Data mentah di atas adalah hasil deteksi model Vision. Anda dapat mengubahnya menjadi laporan teknis formal menggunakan tombol di bawah.
                    </div>
                </div>
            `;

            reasonBtn.classList.remove('d-none');
            setUIState('success', 'vlm');

        } catch (error) {
            console.error(error);
            setUIState('idle');
            resultContent.innerHTML = `<div class="status-badge status-idle">Error: ${error.message}</div>`;
        }
    });

    // Stage 2: LLM Reasoning
    reasonBtn.addEventListener('click', async (e) => {
        e.preventDefault();
        if (!currentVisionData) return;

        setUIState('loading', 'llm');
        const userText = textInput.value.trim();

        try {
            const llmRes = await fetch(`${API}/analyze/llm`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    vision_data: currentVisionData,
                    user_text: userText
                })
            });
            if (!llmRes.ok) throw new Error("Reasoning failed.");
            const llmData = await llmRes.json();

            // Render Markdown Result
            if (typeof marked !== 'undefined') {
                resultContent.innerHTML = marked.parse(llmData.analysis);
            } else {
                resultContent.innerHTML = `<div style="white-space: pre-wrap;">${llmData.analysis}</div>`;
            }

            setUIState('success', 'llm');
            reasonBtn.classList.add('d-none'); // Hide after success

        } catch (error) {
            console.error(error);
            setUIState('success', 'vlm'); // Revert to vlm success state
            alert("Gagal menyusun laporan: " + error.message);
        }
    });

    // Copy Feature
    copyBtn.addEventListener('click', () => {
        const text = resultContent.innerText;
        navigator.clipboard.writeText(text).then(() => {
            const icon = copyBtn.querySelector('i');
            icon.className = 'fas fa-check';
            icon.style.color = '#22c55e';
            setTimeout(() => {
                icon.className = 'far fa-copy';
                icon.style.color = '';
            }, 2000);
        });
    });
});
