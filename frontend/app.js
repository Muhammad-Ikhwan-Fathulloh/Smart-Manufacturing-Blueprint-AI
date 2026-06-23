document.addEventListener('DOMContentLoaded', () => {
    const ocrInput = document.getElementById('ocr-input');
    const analyzeBtn = document.getElementById('analyze-btn');
    const resultContent = document.getElementById('result-content');
    const statusBadge = document.getElementById('status-badge');
    const modelSelect = document.getElementById('model-select');
    const loader = document.getElementById('loader');

    analyzeBtn.addEventListener('click', async () => {
        const data = ocrInput.value.trim();
        if (!data) {
            alert('Silakan masukkan data OCR terlebih dahulu.');
            return;
        }

        // UI State: Loading
        analyzeBtn.disabled = true;
        loader.style.display = 'block';
        statusBadge.textContent = 'Analyzing...';
        statusBadge.className = 'status-badge status-loading';
        resultContent.innerHTML = '<div class="placeholder-text">AI sedang berpikir...</div>';

        try {
            const response = await fetch('http://localhost:8000/analyze', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    ocr_data: data,
                    model_name: modelSelect.value
                })
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || 'Terjadi kesalahan sistem.');
            }

            const result = await response.json();

            // UI State: Success
            displayResult(result);
            statusBadge.textContent = 'Completed';
            statusBadge.className = 'status-badge status-success';

        } catch (error) {
            console.error(error);
            resultContent.innerHTML = `<div style="color: #ef4444; padding: 1rem;">Error: ${error.message}</div>`;
            statusBadge.textContent = 'Error';
            statusBadge.className = 'status-badge status-idle';
        } finally {
            analyzeBtn.disabled = false;
            loader.style.display = 'none';
        }
    });

    function displayResult(data) {
        // Handle if response is string or object
        let parsed;
        try {
            parsed = typeof data === 'string' ? JSON.parse(data) : data;
        } catch (e) {
            parsed = data;
        }

        // Create structured view
        resultContent.innerHTML = '';
        const pre = document.createElement('pre');
        pre.textContent = JSON.stringify(parsed, null, 4);
        resultContent.appendChild(pre);

        // Highlight anomalies if any
        if (parsed.anomalies && parsed.anomalies.length > 0) {
            const warning = document.createElement('div');
            warning.style.marginTop = '1rem';
            warning.style.padding = '1rem';
            warning.style.background = 'rgba(234, 179, 8, 0.1)';
            warning.style.border = '1px solid #eab308';
            warning.style.borderRadius = '8px';
            warning.style.color = '#eab308';
            warning.innerHTML = `<strong>⚠️ Anomali Terdeteksi:</strong><ul style="margin-top: 0.5rem; margin-left: 1.5rem;">` +
                parsed.anomalies.map(a => `<li>${a}</li>`).join('') + `</ul>`;
            resultContent.appendChild(warning);
        }
    }
});
