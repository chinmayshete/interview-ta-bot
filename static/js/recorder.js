/**
 * recorder.js — Browser audio recording + waveform visualization
 *
 * Uses the MediaRecorder API to capture microphone audio and the
 * Web Audio API (AnalyserNode) for a live waveform display.
 */

const AudioRecorder = (() => {
    let mediaRecorder = null;
    let audioChunks = [];
    let audioContext = null;
    let analyser = null;
    let microphone = null;
    let animationId = null;
    let startTime = null;
    let timerInterval = null;
    let recognition = null;

    const BAR_COUNT = 32;

    /**
     * Initialise the waveform bars inside the container element.
     */
    function initWaveformBars(container) {
        const barsDiv = container.querySelector('.waveform-bars');
        if (!barsDiv) return;
        barsDiv.innerHTML = '';
        for (let i = 0; i < BAR_COUNT; i++) {
            const bar = document.createElement('div');
            bar.classList.add('waveform-bar');
            bar.style.height = '4px';
            barsDiv.appendChild(bar);
        }
    }

    /**
     * Animate the waveform bars from the AnalyserNode frequency data.
     */
    function animateWaveform(container) {
        if (!analyser) return;
        const bars = container.querySelectorAll('.waveform-bar');
        const data = new Uint8Array(analyser.frequencyBinCount);

        function draw() {
            analyser.getByteFrequencyData(data);
            const step = Math.floor(data.length / BAR_COUNT);
            for (let i = 0; i < BAR_COUNT; i++) {
                const val = data[i * step] || 0;
                const height = Math.max(4, (val / 255) * 32);
                bars[i].style.height = `${height}px`;
            }
            animationId = requestAnimationFrame(draw);
        }
        draw();
    }

    /**
     * Update the recording timer display.
     */
    function updateTimer(container) {
        const el = container.querySelector('.recording-time');
        if (!el || !startTime) return;
        const elapsed = Math.floor((Date.now() - startTime) / 1000);
        const m = String(Math.floor(elapsed / 60)).padStart(2, '0');
        const s = String(elapsed % 60).padStart(2, '0');
        el.textContent = `${m}:${s}`;
    }

    /**
     * Start recording audio from the user's microphone.
     * Returns a Promise that resolves immediately once recording begins.
     * @param {HTMLElement} waveformContainer - Container for waveform animation
     * @param {Function} onTranscript - Callback for real-time text (finalText, interimText)
     */
    async function start(waveformContainer, onTranscript) {
        audioChunks = [];
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

        // MediaRecorder
        mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
        mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) audioChunks.push(e.data);
        };
        mediaRecorder.start();

        // Web Audio analyser
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        analyser = audioContext.createAnalyser();
        analyser.fftSize = 256;
        microphone = audioContext.createMediaStreamSource(stream);
        microphone.connect(analyser);

        // Waveform UI
        if (waveformContainer) {
            initWaveformBars(waveformContainer);
            waveformContainer.classList.add('active');
            animateWaveform(waveformContainer);
        }

        // Timer
        startTime = Date.now();
        timerInterval = setInterval(() => updateTimer(waveformContainer), 1000);

        // Web Speech API for real-time dictation
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (SpeechRecognition && onTranscript) {
            recognition = new SpeechRecognition();
            recognition.continuous = true;
            recognition.interimResults = true;
            
            let sessionFinalTranscript = '';
            
            recognition.onresult = (event) => {
                let currentInterimTranscript = '';
                
                for (let i = event.resultIndex; i < event.results.length; ++i) {
                    if (event.results[i].isFinal) {
                        sessionFinalTranscript += event.results[i][0].transcript;
                    } else {
                        currentInterimTranscript += event.results[i][0].transcript;
                    }
                }
                // Pass the fully accumulated final text + the current live interim text
                onTranscript(sessionFinalTranscript, currentInterimTranscript);
            };
            
            // Chrome often stops the recognizer automatically when a user pauses.
            // We must restart it to keep listening as long as our MediaRecorder is active.
            recognition.onend = () => {
                if (mediaRecorder && mediaRecorder.state === 'recording') {
                    try {
                        recognition.start();
                    } catch (e) {
                        console.warn("Could not restart speech recognition after pause:", e);
                    }
                }
            };
            
            recognition.onerror = (e) => console.warn("Speech recognition error:", e.error);
            
            try {
                recognition.start();
            } catch (e) {
                console.warn("Could not start speech recognition:", e);
            }
        }
    }

    /**
     * Stop recording and return the audio Blob.
     */
    function stop() {
        return new Promise((resolve) => {
            if (!mediaRecorder || mediaRecorder.state === 'inactive') {
                resolve(null);
                return;
            }

            mediaRecorder.onstop = () => {
                const blob = new Blob(audioChunks, { type: 'audio/webm' });
                audioChunks = [];

                // Cleanup
                if (animationId) cancelAnimationFrame(animationId);
                if (timerInterval) clearInterval(timerInterval);
                if (microphone) microphone.disconnect();
                if (audioContext) audioContext.close();
                mediaRecorder.stream.getTracks().forEach(t => t.stop());

                if (recognition) {
                    try {
                        recognition.stop();
                    } catch (e) {}
                    recognition = null;
                }

                mediaRecorder = null;
                analyser = null;
                microphone = null;
                audioContext = null;
                startTime = null;

                resolve(blob);
            };

            mediaRecorder.stop();
        });
    }

    /**
     * Check if currently recording.
     */
    function isRecording() {
        return mediaRecorder && mediaRecorder.state === 'recording';
    }

    return { start, stop, isRecording };
})();
