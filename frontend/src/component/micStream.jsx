// App.js
import React, { useState, useRef, useEffect } from 'react';

function MicStream() {
  const [isRecording, setIsRecording] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [status, setStatus] = useState('Ready to start');
  const ws = useRef(null);
  const mediaRecorder = useRef(null);

  useEffect(() => {
    return () => {
      if (ws.current) {
        ws.current.close();
      }
    };
  }, []);

  const startRecording = async () => {
    try {
      setStatus('Requesting microphone access...');
      
      // Get microphone stream
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true
        } 
      });

      setStatus('Connecting to server...');
      
      // Connect to WebSocket
      ws.current = new WebSocket('ws://localhost:8000/ws/transcribe');
      
      ws.current.onopen = () => {
        setStatus('Recording...');
        setIsRecording(true);
        setTranscript('');
        
        // Setup media recorder
        mediaRecorder.current = new MediaRecorder(stream, {
          mimeType: 'audio/webm;codecs=opus'
        });
        
        // Process audio data
        const audioContext = new AudioContext({ sampleRate: 16000 });
        const source = audioContext.createMediaStreamSource(stream);
        const processor = audioContext.createScriptProcessor(4096, 1, 1);
        
        source.connect(processor);
        processor.connect(audioContext.destination);
        
        processor.onaudioprocess = (e) => {
          if (!isRecording) return;
          
          // Convert audio to Int16
          const inputData = e.inputBuffer.getChannelData(0);
          const int16Data = convertFloat32ToInt16(inputData);
          
          // Send to server via WebSocket
          if (ws.current && ws.current.readyState === WebSocket.OPEN) {
            ws.current.send(int16Data);
          }
        };
        
        // Handle transcriptions from server
        ws.current.onmessage = (e) => {
          if (e.data.startsWith('ERROR:')) {
            setStatus(e.data);
          } else {
            setTranscript(prev => prev + ' ' + e.data);
          }
        };
        
        ws.current.onerror = (e) => {
          setStatus('WebSocket error');
          console.error('WebSocket error:', e);
        };
        
        ws.current.onclose = () => {
          setStatus('Disconnected');
          setIsRecording(false);
        };
      };
      
    } catch (error) {
      setStatus(`Error: ${error.message}`);
      console.error('Error starting recording:', error);
    }
  };

  const stopRecording = () => {
    if (mediaRecorder.current && mediaRecorder.current.state === 'recording') {
      mediaRecorder.current.stop();
    }
    
    if (ws.current) {
      ws.current.close();
    }
    
    setIsRecording(false);
    setStatus('Recording stopped');
  };

  const convertFloat32ToInt16 = (buffer) => {
    const l = buffer.length;
    const buf = new Int16Array(l);
    for (let i = 0; i < l; i++) {
      buf[i] = Math.min(1, buffer[i]) * 0x7FFF;
    }
    return buf.buffer;
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>Real-Time Transcription</h1>
        
        <div className="controls">
          <button 
            onClick={isRecording ? stopRecording : startRecording}
            className={isRecording ? 'stop-btn' : 'start-btn'}
          >
            {isRecording ? 'Stop Recording' : 'Start Recording'}
          </button>
        </div>
        
        <div className="status">
          Status: {status}
        </div>
        
        <div className="transcript">
          <h2>Transcript:</h2>
          <p>{transcript || 'Start recording to see transcript here...'}</p>
        </div>
      </header>
    </div>
  );
}

export default MicStream;