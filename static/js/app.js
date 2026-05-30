/**
 * app.js — Main application controller for the Interview Support Agent.
 *
 * Manages the full interview lifecycle:
 *   Setup → Active Interview → Review
 *
 * Depends on: ui.js, recorder.js
 */

const App = (() => {
    /* ── State ────────────────────────────────────────────────── */
    let sessionId = null;
    let resumeText = '';
    let jdText = '';
    let questionCount = 0;
    let currentQuestion = null;   // last AI response
    let isTranscribing = false;
    let historyData = [];         // Stores detailed history for modal viewing

    // Always point to the FastAPI backend on port 8000.
    const API = 'http://localhost:8000';

    /* ── API helpers ──────────────────────────────────────────── */

    async function apiPost(path, body, isFormData = false) {
        const opts = { method: 'POST' };
        if (isFormData) {
            opts.body = body;
        } else {
            opts.headers = { 'Content-Type': 'application/json' };
            opts.body = JSON.stringify(body);
        }
        const res = await fetch(`${API}${path}`, opts);
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            // If detail is an object/array (common in FastAPI 422), stringify it
            const msg = typeof err.detail === 'object' ? JSON.stringify(err.detail) : (err.detail || 'API request failed');
            throw new Error(msg);
        }
        return res.json();
    }

    async function apiGet(path) {
        const res = await fetch(`${API}${path}`);
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            const msg = typeof err.detail === 'object' ? JSON.stringify(err.detail) : (err.detail || 'API request failed');
            throw new Error(msg);
        }
        return res.json();
    }

    /* ── Resume Upload ────────────────────────────────────────── */

    async function handleResumeUpload(e) {
        const file = e.target.files[0];
        if (!file) return;

        const zone = document.getElementById('resume-upload-zone');
        try {
            const fd = new FormData();
            fd.append('file', file);
            const res = await apiPost('/api/upload/resume', fd, true);
            resumeText = res.text;
            UI.markUploaded(zone, file.name);
            UI.showToast(`Resume parsed — ${res.char_count} characters`, 'success');
            checkStartReady();
        } catch (err) {
            UI.showToast(`Resume upload failed: ${err.message}`, 'error');
        }
    }

    /* ── JD Input ─────────────────────────────────────────────── */

    function handleJDInput(e) {
        jdText = e.target.value.trim();
        checkStartReady();
    }

    function checkStartReady() {
        const btn = document.getElementById('start-btn');
        btn.disabled = !(resumeText && jdText.length > 20);
    }

    /* ── Start Interview ──────────────────────────────────────── */

    async function startInterview() {
        if (!resumeText || !jdText) return;

        UI.showSpinner('Starting interview — generating first question...');

        try {
            const res = await apiPost('/api/interview/start', {
                resume_text: resumeText,
                jd_text: jdText,
            });

            sessionId = res.session_id;
            questionCount = 1;
            currentQuestion = res;

            // Switch to interview panel
            UI.showInterviewPanel();
            UI.setHeaderStatus('Interview Active', true);
            UI.updateSessionBar(sessionId, res.next_question?.difficulty || 'easy');
            UI.renderQuestion(res, questionCount);

            // Show evaluation only if it has meaningful data (first turn has stub)
            if (res.evaluation && res.evaluation.rating) {
                UI.renderEvaluation(res.evaluation);
            }
            UI.renderFollowUp(res.follow_up);
            UI.renderGuidance(res.interview_guidance);

            UI.showToast('Interview started successfully!', 'success');
        } catch (err) {
            UI.showToast(`Failed to start: ${err.message}`, 'error');
        } finally {
            UI.hideSpinner();
        }
    }

    /* ── Submit Answer (text) ─────────────────────────────────── */

    async function submitAnswer() {
        const textarea = document.getElementById('answer-textarea');
        const answer = textarea.value.trim();
        if (!answer) {
            UI.showToast('Please type or record an answer first.', 'info');
            return;
        }

        UI.showSpinner('Evaluating answer & generating next question...');

        try {
            // Stop recording before we proceed, so it doesn't bleed into the next question
            if (AudioRecorder.isRecording()) {
                await toggleRecording();
            }

            // Save current question to history before moving on
            if (currentQuestion?.next_question) {
                const historyEntry = {
                    question: currentQuestion.next_question.question,
                    difficulty: currentQuestion.next_question.difficulty,
                    answer: answer,
                    rating: null, // to be updated below
                    summary: null,
                    index: questionCount
                };
                historyData.push(historyEntry);

                UI.addHistoryItem(historyEntry, questionCount, (entry) => {
                    UI.showHistoryModal(entry);
                });
            }

            const res = await apiPost('/api/interview/next', {
                session_id: sessionId,
                candidate_answer: answer,
            });

            questionCount++;
            currentQuestion = res;

            // Update the last history item's rating and summary
            if (historyData.length > 0) {
                const lastEntry = historyData[historyData.length - 1];
                lastEntry.rating = res.evaluation?.rating || 'partial';
                lastEntry.summary = res.evaluation?.candidate_answer_summary || '';
                
                const historyItems = document.querySelectorAll('.history-item');
                if (historyItems.length > 0) {
                    const last = historyItems[historyItems.length - 1];
                    const ratingIcons = { strong: '🟢', partial: '🟡', weak: '🔴' };
                    const ratingSpan = last.querySelector('.history-item-header span:last-child');
                    if (ratingSpan) ratingSpan.textContent = ratingIcons[lastEntry.rating] || '🟡';
                }
            }

            // Render new data
            UI.updateSessionBar(sessionId, res.next_question?.difficulty || 'easy');
            UI.renderQuestion(res, questionCount);
            UI.renderEvaluation(res.evaluation);
            UI.renderFollowUp(res.follow_up);
            UI.renderGuidance(res.interview_guidance);

            // Clear answer
            textarea.value = '';

        } catch (err) {
            UI.showToast(`Failed: ${err.message}`, 'error');
        } finally {
            UI.hideSpinner();
        }
    }

    /* ── Audio Recording ──────────────────────────────────────── */

    let baseTextWhenRecordingStarted = "";

    async function toggleRecording() {
        const btn = document.getElementById('record-btn');
        const waveform = document.getElementById('waveform-container');
        const transcribingLabel = document.getElementById('transcribing-label');
        const textarea = document.getElementById('answer-textarea');

        if (AudioRecorder.isRecording()) {
            // Stop recording
            btn.classList.remove('recording');
            btn.innerHTML = '🎙️';
            
            // Get the recorded audio blob
            const blob = await AudioRecorder.stop();
            waveform.classList.remove('active');
            
            // Although live dictation (Web Speech API) populated the box while speaking,
            // we will now send the full audio to Azure Whisper to get perfectly 
            // punctuated, high-accuracy text, replacing the raw live text.
            if (blob && blob.size > 0) {
                isTranscribing = true;
                transcribingLabel.classList.add('active');
                transcribingLabel.textContent = 'Correcting spellings (Azure)...';
                try {
                    if (!sessionId) {
                        throw new Error('No active session. Please start the interview first.');
                    }
                    const fd = new FormData();
                    fd.append('session_id', sessionId);
                    
                    // Explicitly define field names to match FastAPI expectations
                    const rawText = (textarea.value.substring(baseTextWhenRecordingStarted.length)).trim();
                    if (rawText.length > 0) {
                        fd.append('raw_text', rawText);
                    } else {
                        // If no text, send audio as fallback
                        fd.append('audio', blob, 'recording.webm');
                    }
                    
                    const res = await apiPost('/api/interview/transcribe', fd, true);

                    // Replace the raw dictated text with the spelling-corrected transcript
                    if (baseTextWhenRecordingStarted) {
                        textarea.value = baseTextWhenRecordingStarted + (baseTextWhenRecordingStarted.endsWith('\n') ? '' : '\n') + res.text;
                    } else {
                        textarea.value = res.text;
                    }
                    UI.showToast('Text formatting applied successfully!', 'success');
                } catch (err) {
                    UI.showToast(`Azure spelling correction failed: ${err.message}`, 'error');
                } finally {
                    isTranscribing = false;
                    transcribingLabel.classList.remove('active');
                }
            } else {
                isTranscribing = false;
                transcribingLabel.classList.remove('active');
            }
        } else {
            // Start recording
            try {
                baseTextWhenRecordingStarted = textarea.value.trim();
                
                // Show listening indicator immediately so user knows text typing is ready
                isTranscribing = true;
                transcribingLabel.classList.add('active');
                transcribingLabel.textContent = 'Listening...';
                
                await AudioRecorder.start(waveform, (finalText, interimText) => {
                    let newText = baseTextWhenRecordingStarted;
                    if (newText && (finalText || interimText)) newText += '\n';
                    newText += finalText + interimText;
                    
                    textarea.value = newText;
                    textarea.scrollTop = textarea.scrollHeight;
                });
                
                btn.classList.add('recording');
                btn.innerHTML = '⏹️';
            } catch (err) {
                UI.showToast('Microphone access denied or Speech API failed.', 'error');
                isTranscribing = false;
                transcribingLabel.classList.remove('active');
            }
        }
    }

    /* ── End Interview ────────────────────────────────────────── */

    async function endInterview() {
        if (!sessionId) return;
        if (!confirm('Are you sure you want to end this interview?')) return;

        UI.showSpinner('Finalising interview and generating summary...');

        try {
            await fetch(`${API}/api/interview/end/${sessionId}`, { method: 'POST' });
            UI.setHeaderStatus('Interview Ended', false);
            
            // Fetch the summary
            const summary = await apiGet(`/api/interview/summary/${sessionId}`);
            UI.renderSummary(summary);
            UI.showToast('Interview session ended. Summary generated.', 'success');

            // Disable main inputs (panel will be hidden anyway)
            document.getElementById('answer-textarea').disabled = true;
            document.getElementById('submit-btn').disabled = true;
            document.getElementById('record-btn').disabled = true;
        } catch (err) {
            UI.showToast(`Failed to end session: ${err.message}`, 'error');
        } finally {
            UI.hideSpinner();
        }
    }

    /* ── Initialisation ───────────────────────────────────────── */

    function init() {
        // Resume upload
        document.getElementById('resume-file-input')
            .addEventListener('change', handleResumeUpload);

        // JD input
        document.getElementById('jd-textarea')
            .addEventListener('input', handleJDInput);

        // Start button
        document.getElementById('start-btn')
            .addEventListener('click', startInterview);

        // Submit answer
        document.getElementById('submit-btn')
            .addEventListener('click', submitAnswer);

        // Record button
        document.getElementById('record-btn')
            .addEventListener('click', toggleRecording);

        // End interview
        document.getElementById('end-btn')
            .addEventListener('click', endInterview);

        // Download Summary
        document.getElementById('download-pdf-btn').addEventListener('click', () => {
            window.location.href = `${API}/api/interview/export/${sessionId}/pdf`;
        });
        document.getElementById('download-docx-btn').addEventListener('click', () => {
            window.location.href = `${API}/api/interview/export/${sessionId}/docx`;
        });

        // Modal Close
        document.getElementById('history-modal-close')
            .addEventListener('click', UI.hideHistoryModal);
        
        document.getElementById('history-modal-overlay')
            .addEventListener('click', (e) => {
                if (e.target.id === 'history-modal-overlay') UI.hideHistoryModal();
            });

        // Drag-and-drop on resume zone
        const zone = document.getElementById('resume-upload-zone');
        zone.addEventListener('dragover', (e) => {
            e.preventDefault();
            zone.classList.add('dragover');
        });
        zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
        zone.addEventListener('drop', (e) => {
            e.preventDefault();
            zone.classList.remove('dragover');
            const fileInput = document.getElementById('resume-file-input');
            fileInput.files = e.dataTransfer.files;
            fileInput.dispatchEvent(new Event('change'));
        });

        // Keyboard shortcut: Ctrl+Enter to submit
        document.getElementById('answer-textarea')
            .addEventListener('keydown', (e) => {
                if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                    e.preventDefault();
                    submitAnswer();
                }
            });

        UI.showSetupPanel();
        UI.setHeaderStatus('Ready to Start', false);
    }

    // Auto-init on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    return { startInterview, submitAnswer, endInterview };
})();
