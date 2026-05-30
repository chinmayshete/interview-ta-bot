import { useState, useEffect, useRef } from 'react';
import { apiPost } from '../api/client';
import QuestionCard from '../components/QuestionCard';
import EvaluationCard from '../components/EvaluationCard';

export default function LiveInterviewPage({ sessionId, setPage, showToast, showSpinner, hideSpinner }) {
  const [liveData, setLiveData] = useState(window.liveSessionData || {});
  const [transcript, setTranscript] = useState([]);
  const [currentState, setCurrentState] = useState('STATE_IDLE');
  const [activeQuestion, setActiveQuestion] = useState(null);
  const [suggestedQuestion, setSuggestedQuestion] = useState(null);
  const [isCapturing, setIsCapturing] = useState(false);
  const [isConnecting, setIsConnecting] = useState(true);
  
  const wsRef = useRef(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (!liveData.live_session_id) {
      showToast('No live session found. Returning to setup.', 'error');
      setPage('setup');
      return;
    }

    // Connect WebSocket
    const wsUrl = liveData.ws_url;
    console.log('[Live] Connecting to:', wsUrl);
    
    const socket = new WebSocket(wsUrl);
    wsRef.current = socket;

    socket.onopen = () => {
      console.log('[Live] WebSocket connected');
      setIsConnecting(false);
      showToast('Connected to live transcription engine', 'success');
    };

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log('[Live] Received:', data);

      switch (data.event_type) {
        case 'transcript':
          setTranscript(prev => [...prev, {
            speaker: data.speaker_role || 'unknown',
            text: data.text,
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
          }]);
          break;
        case 'state_change':
          setCurrentState(data.conversation_state);
          break;
        case 'next_question':
          setSuggestedQuestion(data.next_question);
          setActiveQuestion(data.active_question);
          break;
        case 'override':
          showToast(data.text, 'info');
          break;
        case 'error':
          showToast(data.error, 'error');
          break;
        default:
          break;
      }
    };

    socket.onclose = () => {
      console.log('[Live] WebSocket closed');
      setIsConnecting(false);
    };

    return () => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.close();
      }
    };
  }, [liveData]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [transcript]);

  const toggleCapture = async () => {
    const liveId = liveData.live_session_id;
    try {
      if (isCapturing) {
        await apiPost(`/api/live/${liveId}/stop-capture`);
        setIsCapturing(false);
        showToast('Stopped listening.', 'info');
      } else {
        await apiPost(`/api/live/${liveId}/start-capture`);
        setIsCapturing(true);
        showToast('Now listening to system audio...', 'success');
      }
    } catch (err) {
      showToast(`Capture error: ${err.message}`, 'error');
    }
  };

  const endSession = async () => {
    if (!confirm('End live session?')) return;
    const liveId = liveData.live_session_id;
    try {
      await apiPost(`/api/live/${liveId}/end`);
      setPage('summary');
    } catch (err) {
      showToast('Failed to end session', 'error');
    }
  };

  const getStateColor = () => {
    switch(currentState) {
      case 'STATE_INTERVIEWER_ASKING': return '#38bdf8';
      case 'STATE_CANDIDATE_ANSWERING': return '#4ade80';
      case 'STATE_PROCESSING': return '#f59e0b';
      default: return 'var(--text-muted)';
    }
  };

  const getStateLabel = () => {
    switch(currentState) {
      case 'STATE_INTERVIEWER_ASKING': return 'Interviewer is asking...';
      case 'STATE_CANDIDATE_ANSWERING': return 'Candidate is answering...';
      case 'STATE_PROCESSING': return 'Processing answer...';
      default: return 'Waiting for speech...';
    }
  };

  return (
    <section id="live-interview-panel" className="fade-in">
      <div className="actions-bar">
        <div className="actions-bar-left">
          <span className={`live-badge ${isCapturing ? 'active' : ''}`}>
            {isCapturing ? '● LIVE CAPTURING' : '○ CAPTURE PAUSED'}
          </span>
          <div className="state-display" style={{ marginLeft: '20px', display: 'flex', alignItems: 'center', gap: '8px' }}>
             <span className="pulse-dot" style={{ backgroundColor: getStateColor() }}></span>
             <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>{getStateLabel()}</span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button className={`btn-secondary ${isCapturing ? 'recording' : ''}`} onClick={toggleCapture}>
            {isCapturing ? '⏹ Stop Capture' : '🎙️ Start Capture'}
          </button>
          <button className="btn-danger" onClick={endSession}>
            End Interview
          </button>
        </div>
      </div>

      <div className="interview-grid" style={{ gridTemplateColumns: '1fr 380px' }}>
        <div className="main-column">
          {/* Transcript Feed */}
          <div className="glass-card transcript-container">
             <div className="card-header">
                <span className="icon">💬</span>
                <h2>Live Transcript</h2>
             </div>
             <div className="card-body transcript-feed" ref={scrollRef}>
                {transcript.length === 0 && (
                  <div className="empty-state">
                     <p>Transcript will appear here in real-time...</p>
                  </div>
                )}
                {transcript.map((item, i) => (
                  <div key={i} className={`transcript-item ${item.speaker}`}>
                    <div className="transcript-meta">
                       <span className="speaker-name">{item.speaker.toUpperCase()}</span>
                       <span className="timestamp">{item.time}</span>
                    </div>
                    <div className="transcript-text">{item.text}</div>
                  </div>
                ))}
             </div>
          </div>

          {/* Active Question Display */}
          <div className="glass-card" style={{ marginTop: '20px' }}>
             <div className="card-header">
                <span className="icon">❓</span>
                <h2>Active Question</h2>
             </div>
             <div className="card-body">
                <div className="active-question-text">
                   {activeQuestion || "No question has been identified yet."}
                </div>
             </div>
          </div>
        </div>

        <div className="sidebar-column">
           {/* Suggested Next Question (Bot) */}
           <div className="glass-card suggested-card">
              <div className="card-header">
                 <span className="icon">🤖</span>
                 <h2>Bot Suggestion</h2>
              </div>
              <div className="card-body">
                 {!suggestedQuestion ? (
                   <p className="hint-text">The bot will suggest a follow-up or next question once the candidate finishes speaking.</p>
                 ) : (
                   <div className="suggestion-content">
                      <div className="difficulty-tag" data-difficulty={suggestedQuestion.next_question?.difficulty}>
                         {suggestedQuestion.next_question?.difficulty?.toUpperCase()}
                      </div>
                      <p className="question-text">{suggestedQuestion.next_question?.question}</p>
                      
                      <div className="expected-answer-section">
                         <h4>Expected Answer:</h4>
                         <p>{suggestedQuestion.expected_answer?.ideal_answer}</p>
                      </div>
                   </div>
                 )}
              </div>
           </div>

           <EvaluationCard data={suggestedQuestion?.evaluation} />
        </div>
      </div>
      
      <style>{`
        .transcript-feed {
          height: 400px;
          overflow-y: auto;
          padding-right: 10px;
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        .transcript-item {
          padding: 10px 14px;
          border-radius: 12px;
          max-width: 90%;
          animation: slideIn 0.2s ease-out;
        }
        .transcript-item.interviewer {
          align-self: flex-start;
          background: rgba(56, 189, 248, 0.1);
          border-left: 3px solid #38bdf8;
        }
        .transcript-item.candidate {
          align-self: flex-end;
          background: rgba(74, 222, 128, 0.1);
          border-right: 3px solid #4ade80;
          text-align: right;
        }
        .transcript-meta {
          display: flex;
          justify-content: space-between;
          font-size: 0.7rem;
          margin-bottom: 4px;
          opacity: 0.7;
        }
        .speaker-name { font-weight: 700; }
        .active-question-text {
          font-size: 1.1rem;
          line-height: 1.5;
          color: #f8fafc;
        }
        .live-badge {
          font-size: 0.75rem;
          font-weight: 700;
          padding: 4px 8px;
          border-radius: 4px;
          background: rgba(255,255,255,0.05);
          color: var(--text-muted);
        }
        .live-badge.active {
          color: #ef4444;
          background: rgba(239, 68, 68, 0.1);
          animation: blink 2s infinite;
        }
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        @keyframes slideIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .pulse-dot {
          width: 10px;
          height: 10px;
          border-radius: 50%;
          display: inline-block;
        }
        .empty-state {
          display: flex;
          height: 100%;
          align-items: center;
          justify-content: center;
          color: var(--text-muted);
          font-style: italic;
        }
        .suggestion-content .difficulty-tag {
          display: inline-block;
          padding: 2px 8px;
          border-radius: 4px;
          font-size: 0.7rem;
          font-weight: 800;
          margin-bottom: 10px;
        }
        .suggestion-content .difficulty-tag[data-difficulty="easy"] { background: rgba(74, 222, 128, 0.2); color: #4ade80; }
        .suggestion-content .difficulty-tag[data-difficulty="medium"] { background: rgba(245, 158, 11, 0.2); color: #f59e0b; }
        .suggestion-content .difficulty-tag[data-difficulty="hard"] { background: rgba(239, 68, 68, 0.2); color: #ef4444; }
        .expected-answer-section h4 {
          font-size: 0.8rem;
          color: var(--text-secondary);
          margin-top: 15px;
          margin-bottom: 5px;
        }
        .expected-answer-section p {
          font-size: 0.85rem;
          line-height: 1.4;
          color: var(--text-muted);
        }
      `}</style>
    </section>
  );
}
