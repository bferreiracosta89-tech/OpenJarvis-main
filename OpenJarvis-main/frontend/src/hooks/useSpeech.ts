import { useState, useCallback, useRef, useEffect } from 'react';
import { transcribeAudio, fetchSpeechHealth } from '../lib/api';

export type SpeechState = 'idle' | 'recording' | 'transcribing';

interface BrowserRecognition {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
}

function createBrowserRecognition(): BrowserRecognition | null {
  const speechWindow = window as Window & {
    SpeechRecognition?: new () => BrowserRecognition;
    webkitSpeechRecognition?: new () => BrowserRecognition;
  };
  const Constructor = speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition;
  return Constructor ? new Constructor() : null;
}

export function useSpeech() {
  const [state, setState] = useState<SpeechState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [available, setAvailable] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const browserRecognitionRef = useRef<BrowserRecognition | null>(null);
  const browserTranscriptRef = useRef('');
  const browserStopResolveRef = useRef<((text: string) => void) | null>(null);

  // Check if speech backend is available on mount
  useEffect(() => {
    fetchSpeechHealth()
      .then((health) => setAvailable(health.available || !!createBrowserRecognition()))
      .catch(() => setAvailable(!!createBrowserRecognition()));
  }, []);

  const startRecording = useCallback(async (): Promise<void> => {
    setError(null);

    if (!navigator.mediaDevices?.getUserMedia) {
      setError('Microfone não suportado neste navegador');
      return;
    }

    const browserRecognition = createBrowserRecognition();
    if (!available && browserRecognition) {
      browserTranscriptRef.current = '';
      browserRecognition.continuous = false;
      browserRecognition.interimResults = false;
      browserRecognition.lang = document.documentElement.lang || 'pt-BR';
      browserRecognition.onresult = (event) => {
        const result = event.results[0]?.[0];
        browserTranscriptRef.current = result?.transcript || '';
      };
      browserRecognition.onerror = (event) => {
        setError(event.error ? `Falha no reconhecimento de voz: ${event.error}` : 'Falha no reconhecimento de voz');
        setState('idle');
        browserStopResolveRef.current?.('');
        browserStopResolveRef.current = null;
      };
      browserRecognition.onend = () => {
        setState('idle');
        browserStopResolveRef.current?.(browserTranscriptRef.current.trim());
        browserStopResolveRef.current = null;
      };
      try {
        browserRecognition.start();
        browserRecognitionRef.current = browserRecognition;
        setState('recording');
      } catch {
        setError('Não foi possível iniciar o reconhecimento de voz');
      }
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.start();
      mediaRecorderRef.current = recorder;
      setState('recording');
    } catch (err) {
      setError('Acesso ao microfone negado. Permita o microfone no navegador.');
      setState('idle');
    }
  }, []);

  const stopRecording = useCallback(async (): Promise<string> => {
    if (browserRecognitionRef.current) {
      const recognition = browserRecognitionRef.current;
      browserRecognitionRef.current = null;
      return new Promise((resolve) => {
        browserStopResolveRef.current = resolve;
        recognition.stop();
      });
    }
    return new Promise((resolve, reject) => {
      const recorder = mediaRecorderRef.current;
      if (!recorder || recorder.state !== 'recording') {
        reject(new Error('Not recording'));
        return;
      }

      recorder.onstop = async () => {
        setState('transcribing');

        // Stop all audio tracks
        streamRef.current?.getTracks().forEach((track) => track.stop());
        streamRef.current = null;

        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        chunksRef.current = [];

        try {
          const result = await transcribeAudio(blob);
          setState('idle');
          resolve(result.text);
        } catch (err) {
          setState('idle');
          const msg = err instanceof Error ? err.message : 'Transcription failed';
          setError(msg);
          reject(err);
        }
      };

      recorder.stop();
    });
  }, []);

  return {
    state,
    error,
    available,
    startRecording,
    stopRecording,
    isRecording: state === 'recording',
    isTranscribing: state === 'transcribing',
  };
}
