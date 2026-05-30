import { useState, useEffect, useRef } from 'react';
import { apiPost } from '../api/client';
import QuestionCard from '../components/QuestionCard';
import EvaluationCard from '../components/EvaluationCard';
import HistoryPanel from '../components/HistoryPanel';

export default function InterviewPage({ sessionId, setPage, showToast, showSpinner, hideSpinner }) {
  const [questionCount, setQuestionCount] = useState(1);
  const [currentData, setCurrentData] = useState(window.initialQuestion || {});
  const [answer, setAnswer] = useState('');
  const [history, setHistory] = useState([]);
  
  // Stealth capturing state — ON by default
  const [isListening, setIsListening] = useState(false);

  // Auto-start loopback capture on mount
  useEffect(() => {
    const autoStartCapture = async () => {
      try {
        await apiPost(`/api/audio/start-loopback/${sessionId}`);
        setIsListening(true);
        showToast('Audio capture started automatically', 'success');
      } catch (err) {
        console.error('[InterviewPage] Auto-start capture failed:', err);
        showToast(`Auto-capture failed: ${err.message}. Click the mic button to start manually.`, 'error');
      }
    };
    if (sessionId) {
      autoStartCapture();
    }

    // Cleanup: stop capture when leaving the page without transcribing
    return () => {
      if (sessionId) {
        apiPost(`/api/audio/stop-loopback/${sessionId}?transcribe=false`).catch(() => {});
      }
    };
  }, [sessionId]);



  const endInterview = async () => {
    if (!confirm('Are you sure you want to end this interview?')) return;
    
    showSpinner('Finalising and generating summary...');
    try {
      await apiPost(`/api/interview/end/${sessionId}`, {});

      setPage('summary');
    } catch (err) {
      showToast('Failed to end interview', 'error');
    } finally {
      hideSpinner();
    }
  };

  const submitAnswer = async () => {
    if (!answer.trim() && !isListening) {
      showToast('Please type an answer first.', 'info');
      return;
    }

    showSpinner('Evaluating & Generating next question...');
    try {
      let finalAnswer = answer;
      
      // If we are currently secretly listening to loopback, stop and transcribe
      if (isListening) {
        try {
          const res = await apiPost(`/api/audio/stop-loopback/${sessionId}`);
          finalAnswer = answer ? `${answer}\n${res.text}` : res.text;
          setIsListening(false);
          showToast('Audio transcribed successfully', 'success');
        } catch (e) {
          showToast(`Audio loopback capture failed: ${e.message}`, 'error');
        }
      }

      const qText = currentData?.next_question?.question;
      const qDiff = currentData?.next_question?.difficulty;

      const res = await apiPost('/api/interview/next', {
        session_id: sessionId,
        candidate_answer: finalAnswer,
      });

      // Add to history
      setHistory([...history, {
        index: questionCount,
        question: qText,
        difficulty: qDiff,
        answer: finalAnswer,
        rating: res.evaluation?.rating || 'partial',
        summary: res.evaluation?.candidate_answer_summary || ''
      }]);

      setCurrentData(res);
      setQuestionCount(c => c + 1);
      setAnswer('');

    } catch (err) {
      showToast(`Submission failed: ${err.message}`, 'error');
    } finally {
      hideSpinner();
    }
  };

  const toggleLoopback = async () => {
    if (isListening) {
       // Just stop listening but don't submit yet.
       showSpinner('Transcribing system audio...');
       try {
         const res = await apiPost(`/api/audio/stop-loopback/${sessionId}`);
         setAnswer(prev => prev ? `${prev}\n${res.text}` : res.text);
         showToast('Audio transcribed.', 'success');
       } catch (err) {
         showToast('Audio error: ' + err.message, 'error');
       } finally {
         setIsListening(false);
         hideSpinner();
       }
    } else {
       // Start listening to system output
       try {
         await apiPost(`/api/audio/start-loopback/${sessionId}`);
         setIsListening(true);
       } catch (err) {
         showToast(`Failed to capture system audio: ${err.message}. Is Stereo Mix enabled?`, 'error');
       }
    }
  };

  return (
    <section id="interview-panel" className="fade-in">
      <div className="actions-bar">
        <div className="actions-bar-left">
          <span className="session-id">#{sessionId}</span>
          <div className="difficulty-indicator">
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Difficulty</span>
            <div className={`difficulty-step ${currentData?.next_question?.difficulty ? 'active-easy' : ''}`}></div>
            <div className={`difficulty-step ${['medium','hard'].includes(currentData?.next_question?.difficulty) ? 'active-medium' : ''}`}></div>
            <div className={`difficulty-step ${currentData?.next_question?.difficulty === 'hard' ? 'active-hard' : ''}`}></div>
          </div>
        </div>
        <button className="btn-danger" onClick={endInterview}>
          <span>⏹</span> End Interview
        </button>
      </div>

      <div className="interview-grid">
        <div className="main-column">
          <QuestionCard data={currentData} number={questionCount} />

          <div className="glass-card answer-section">
            <div className="card-header">
              <span className="icon">💬</span>
              <h2>Candidate's Answer</h2>
            </div>
            <div className="card-body">
              <textarea
                className="answer-textarea"
                placeholder="Type the candidate's answer here or click 'Listen to System' to stealthily capture Zoom/Teams audio..."
                value={answer}
                onChange={e => setAnswer(e.target.value)}
                onKeyDown={(e) => {
                  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') submitAnswer();
                }}
              />

              <div className="answer-controls">
                <button 
                   className={`btn-secondary ${isListening ? 'recording' : ''}`} 
                   onClick={toggleLoopback}
                   style={{ padding: '12px', background: isListening ? 'rgba(239,68,68,0.2)' : '' }}
                >
                  {isListening ? '⏹ Stop System Listen' : '🎙️ Listen to System Audio'}
                </button>
                <button className="btn-primary" onClick={submitAnswer}>
                  <span>➡️</span> Submit & Next
                </button>
              </div>
              {isListening && <p style={{color: '#38bdf8', fontSize: '0.8rem', marginTop:'10px'}}>Secretly listening to system audio...</p>}
            </div>
          </div>

          <EvaluationCard data={currentData?.evaluation} />
        </div>

        <div className="sidebar-column">
          <HistoryPanel items={history} />
        </div>
      </div>
    </section>
  );
}
