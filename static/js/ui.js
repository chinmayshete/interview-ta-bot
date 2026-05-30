/**
 * ui.js — DOM rendering functions for the interview dashboard.
 *
 * Each function receives data and updates the corresponding DOM elements.
 * Animations and transitions are handled via CSS classes.
 */

const UI = (() => {

    /* ── Toast Notifications ──────────────────────────────────── */

    function showToast(message, type = 'info', duration = 4000) {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;

        const icons = { success: '✓', error: '✕', info: 'ℹ' };
        toast.innerHTML = `
            <span style="font-size:1.1rem">${icons[type] || 'ℹ'}</span>
            <span class="toast-message">${message}</span>
        `;

        container.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'slide-out 0.3s ease-in forwards';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    /* ── Loading Spinner ──────────────────────────────────────── */

    function showSpinner(text = 'Processing...') {
        const overlay = document.getElementById('spinner-overlay');
        overlay.querySelector('.spinner-text').textContent = text;
        overlay.classList.add('active');
    }

    function hideSpinner() {
        document.getElementById('spinner-overlay').classList.remove('active');
    }

    /* ── Panel Switching ──────────────────────────────────────── */

    function showSetupPanel() {
        document.getElementById('setup-panel').style.display = 'block';
        document.getElementById('interview-panel').style.display = 'none';
    }

    function showInterviewPanel() {
        document.getElementById('setup-panel').style.display = 'none';
        const panel = document.getElementById('interview-panel');
        panel.style.display = 'block';
        panel.classList.add('fade-in');
    }

    /* ── Header Status ────────────────────────────────────────── */

    function setHeaderStatus(text, active = false) {
        const status = document.getElementById('header-status');
        const dot = status.querySelector('.status-dot');
        status.querySelector('.status-text').textContent = text;
        if (active) {
            status.classList.add('active');
            dot.classList.add('active');
        } else {
            status.classList.remove('active');
            dot.classList.remove('active');
        }
    }

    /* ── Session Bar ──────────────────────────────────────────── */

    function updateSessionBar(sessionId, difficulty) {
        document.getElementById('session-id-display').textContent = `#${sessionId}`;

        const steps = document.querySelectorAll('.difficulty-step');
        steps.forEach(s => s.className = 'difficulty-step');

        if (difficulty === 'easy' || difficulty === 'medium' || difficulty === 'hard') {
            steps[0].classList.add('active-easy');
        }
        if (difficulty === 'medium' || difficulty === 'hard') {
            steps[1].classList.add('active-medium');
        }
        if (difficulty === 'hard') {
            steps[2].classList.add('active-hard');
        }
    }

    /* ── Question Card ────────────────────────────────────────── */

    function renderQuestion(data, questionNumber) {
        const q = data.next_question || {};
        const difficulty = q.difficulty || 'easy';
        const category = (q.category || 'technical').replace('_', ' ');

        document.getElementById('question-difficulty').textContent = difficulty.toUpperCase();
        document.getElementById('question-difficulty').className = `badge badge-${difficulty}`;

        document.getElementById('question-category').textContent = category.toUpperCase();
        document.getElementById('question-number').textContent = `Q${questionNumber}`;
        document.getElementById('question-text').textContent = q.question || '';

        // Expected answer
        const expectedEl = document.getElementById('expected-answer-text');
        expectedEl.textContent = data.expected_answer || '';
        document.getElementById('expected-answer-section').style.display =
            data.expected_answer ? 'block' : 'none';

        // Reference Answer (Ideal comprehensive answer to the current question)
        const refAnswerEl = document.getElementById('reference-answer-question-text');
        const refSectionEl = document.getElementById('reference-answer-question-section');
        if (data.reference_answer) {
            refAnswerEl.textContent = data.reference_answer;
            refSectionEl.style.display = 'block';
        } else {
            refSectionEl.style.display = 'none';
        }

        // Scroll to question
        document.getElementById('question-card').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    /* ── Evaluation Card ──────────────────────────────────────── */

    function renderEvaluation(evaluation) {
        const evalCard = document.getElementById('evaluation-card');
        if (!evaluation) {
            evalCard.style.display = 'none';
            return;
        }
        evalCard.style.display = 'block';
        evalCard.classList.add('fade-in');

        // Rating
        const ratingEl = document.getElementById('eval-rating');
        const rating = evaluation.rating || 'partial';
        const ratingIcons = { strong: '🟢', partial: '🟡', weak: '🔴' };
        ratingEl.innerHTML = `${ratingIcons[rating] || '🟡'} ${rating.toUpperCase()}`;
        ratingEl.className = `eval-rating ${rating}`;

        // Confidence
        const score = evaluation.confidence_score ?? 50;
        document.getElementById('confidence-value').textContent = score;
        document.getElementById('confidence-bar').style.width = `${score}%`;

        // Summary
        document.getElementById('eval-summary').textContent =
            evaluation.candidate_answer_summary || '';

        // Reasoning
        document.getElementById('eval-reasoning').textContent =
            evaluation.reasoning || '';
    }

    /* ── Follow-up Card ───────────────────────────────────────── */

    function renderFollowUp(followUp) {
        const card = document.getElementById('followup-card');
        if (!followUp || !followUp.should_ask) {
            card.style.display = 'none';
            return;
        }
        card.style.display = 'block';
        card.classList.add('fade-in');
        document.getElementById('followup-question').textContent =
            followUp.question || '';
    }

    /* ── Guidance Card ────────────────────────────────────────── */

    function renderGuidance(guidance) {
        const card = document.getElementById('guidance-card');
        if (!guidance) {
            card.style.display = 'none';
            return;
        }
        card.style.display = 'block';
        card.classList.add('fade-in');

        document.getElementById('guidance-suggestion').textContent =
            guidance.suggestion_to_interviewer || '';

        const riskEl = document.getElementById('risk-flag');
        const risk = guidance.risk_flag || 'none';
        const riskLabels = {
            none: '✓ No Risks',
            resume_mismatch: '⚠ Resume Mismatch',
            shallow_knowledge: '⚠ Shallow Knowledge',
            overclaiming: '⚠ Overclaiming',
        };
        riskEl.textContent = riskLabels[risk] || risk;
        riskEl.className = `risk-flag risk-${risk}`;
    }

    /* ── Final Summary Panel ──────────────────────────────────── */

    function renderSummary(summary) {
        // Hide interview panel, show summary panel
        document.getElementById('interview-panel').style.display = 'none';
        const panel = document.getElementById('summary-panel');
        panel.style.display = 'block';
        panel.classList.add('fade-in');

        // Score Chart
        const score = summary.overall_score || 0;
        const circle = document.getElementById('summary-score-circle');
        const text = document.getElementById('summary-score-text');
        
        circle.style.strokeDasharray = `${score}, 100`;
        text.textContent = `${score}%`;

        // Metadata
        const badge = document.getElementById('summary-rating-badge');
        badge.textContent = (summary.overall_rating || 'N/A').toUpperCase();
        document.getElementById('summary-statement').textContent = summary.summary_statement || '';

        // Strengths & Weaknesses
        const strengthsList = document.getElementById('summary-strengths-list');
        strengthsList.innerHTML = '';
        (summary.strengths || []).forEach(s => {
            const li = document.createElement('li');
            li.textContent = s;
            strengthsList.appendChild(li);
        });

        const weaknessesList = document.getElementById('summary-weaknesses-list');
        weaknessesList.innerHTML = '';
        (summary.weaknesses || []).forEach(w => {
            const li = document.createElement('li');
            li.textContent = w;
            weaknessesList.appendChild(li);
        });

        // Other fields
        document.getElementById('summary-technical').textContent = summary.technical_proficiency || '';
        document.getElementById('summary-behavioral').textContent = summary.behavioral_fit || '';
        document.getElementById('summary-recommendation').textContent = summary.recommendation || '';
    }

    /* ── History Modal ────────────────────────────────────────── */

    function showHistoryModal(data) {
        const overlay = document.getElementById('history-modal-overlay');
        
        // Populate modal data
        document.getElementById('modal-q-number').textContent = `Q${data.index}`;
        document.getElementById('modal-q-difficulty').textContent = (data.difficulty || 'easy').toUpperCase();
        document.getElementById('modal-q-difficulty').className = `badge badge-${data.difficulty || 'easy'}`;
        document.getElementById('modal-q-text').textContent = data.question || '';
        document.getElementById('modal-q-answer').textContent = data.answer || '(No answer recorded)';
        
        const ratingEl = document.getElementById('modal-q-rating');
        const rating = data.rating || 'partial';
        const ratingIcons = { strong: '🟢', partial: '🟡', weak: '🔴' };
        ratingEl.innerHTML = `${ratingIcons[rating] || '🟡'} ${rating.toUpperCase()}`;
        ratingEl.className = `eval-rating ${rating}`;
        
        document.getElementById('modal-q-summary').textContent = data.summary || '';
        
        overlay.classList.add('active');
    }

    function hideHistoryModal() {
        document.getElementById('history-modal-overlay').classList.remove('active');
    }

    /* ── History Sidebar ──────────────────────────────────────── */

    function addHistoryItem(entry, index, onClick) {
        const list = document.getElementById('history-list');
        const empty = list.querySelector('.history-empty');
        if (empty) empty.remove();

        const rating = entry.rating || 'partial';
        const ratingIcons = { strong: '🟢', partial: '🟡', weak: '🔴' };

        const item = document.createElement('div');
        item.className = 'history-item fade-in';
        item.style.cursor = 'pointer';
        item.innerHTML = `
            <div class="history-item-header">
                <span class="history-item-number">Q${index}</span>
                <span class="badge badge-${entry.difficulty || 'easy'}">${(entry.difficulty || 'easy').toUpperCase()}</span>
                <span>${ratingIcons[rating] || '🟡'}</span>
            </div>
            <div class="history-item-question">${entry.question || ''}</div>
        `;
        
        if (onClick) {
            item.addEventListener('click', () => onClick(entry, index));
        }
        
        list.appendChild(item);
        list.scrollTop = list.scrollHeight;
    }

    /* ── Upload Zone ──────────────────────────────────────────── */

    function markUploaded(zone, filename) {
        zone.classList.add('uploaded');
        zone.querySelector('.upload-label').textContent = filename;
        zone.querySelector('.upload-hint').textContent = '✓ Uploaded successfully';
        zone.querySelector('.upload-icon').textContent = '✅';
    }

    return {
        showToast,
        showSpinner,
        hideSpinner,
        showSetupPanel,
        showInterviewPanel,
        setHeaderStatus,
        updateSessionBar,
        renderQuestion,
        renderEvaluation,
        renderFollowUp,
        renderGuidance,
        addHistoryItem,
        markUploaded,
        showHistoryModal,
        hideHistoryModal,
        renderSummary
    };
})();
