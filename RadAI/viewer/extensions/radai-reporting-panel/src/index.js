/**
 * RadAI Reporting Panel Extension for OHIF v3.12
 *
 * Provides:
 * - Report generation from accepted findings
 * - Template selection (Lung-RADS, General CT)
 * - AI polish toggle (local Ollama or cloud Tier 2)
 * - Voice dictation integration
 * - PDF export
 * - DICOM-SR export
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';

// ─── Styles ──────────────────────────────────────────────────────────────────
const styles = {
  container: {
    padding: '16px',
    color: '#ccc',
    fontSize: '13px',
    maxHeight: '100vh',
    overflowY: 'auto',
  },
  header: {
    margin: '0 0 12px',
    color: '#fff',
    fontSize: '15px',
    fontWeight: 600,
  },
  section: {
    marginBottom: '16px',
  },
  label: {
    display: 'block',
    marginBottom: '4px',
    color: '#aaa',
    fontSize: '12px',
    fontWeight: 500,
  },
  select: {
    width: '100%',
    padding: '8px',
    background: '#222',
    border: '1px solid #444',
    borderRadius: '4px',
    color: '#ccc',
    fontSize: '12px',
  },
  checkbox: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    marginBottom: '8px',
  },
  generateBtn: {
    width: '100%',
    padding: '10px',
    background: '#0066cc',
    color: '#fff',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
    fontSize: '13px',
    fontWeight: 500,
    marginBottom: '8px',
  },
  exportBtn: {
    width: '100%',
    padding: '8px',
    background: '#333',
    color: '#ccc',
    border: '1px solid #555',
    borderRadius: '4px',
    cursor: 'pointer',
    fontSize: '12px',
    marginBottom: '6px',
  },
  reportContent: {
    background: '#1a1a2e',
    border: '1px solid #333',
    borderRadius: '6px',
    padding: '12px',
    fontSize: '12px',
    lineHeight: '1.6',
    whiteSpace: 'pre-wrap',
    maxHeight: '400px',
    overflowY: 'auto',
  },
  voiceBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    width: '100%',
    padding: '10px',
    background: '#6a1b9a',
    color: '#fff',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
    fontSize: '12px',
    fontWeight: 500,
  },
  voiceRecording: {
    background: '#f44336',
    animation: 'pulse 1s infinite',
  },
  status: {
    padding: '8px',
    borderRadius: '4px',
    fontSize: '12px',
    marginBottom: '8px',
  },
  statusSuccess: { background: '#1b3e1b', color: '#4caf50' },
  statusError: { background: '#3e1a1a', color: '#ff6666' },
  statusInfo: { background: '#1a2e3e', color: '#2196f3' },
  divider: {
    borderTop: '1px solid #333',
    margin: '12px 0',
  },
};

// ─── Status Message Component ────────────────────────────────────────────────
const StatusMessage = ({ type, message }) => {
  const style = {
    ...styles.status,
    ...(type === 'success' ? styles.statusSuccess : {}),
    ...(type === 'error' ? styles.statusError : {}),
    ...(type === 'info' ? styles.statusInfo : {}),
  };
  return <div style={style}>{message}</div>;
};

// ─── Reporting Panel Component ───────────────────────────────────────────────
const ReportingPanel = ({ servicesManager, commandsManager }) => {
  const [report, setReport] = useState(null);
  const [template, setTemplate] = useState('lung_rads');
  const [useAiPolish, setUseAiPolish] = useState(true);
  const [aiTier, setAiTier] = useState(1);
  const [generating, setGenerating] = useState(false);
  const [recording, setRecording] = useState(false);
  const [status, setStatus] = useState(null);
  const [classification, setClassification] = useState('');
  const [clinicalIndication, setClinicalIndication] = useState('');
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);

  const getStudyInstanceUid = useCallback(() => {
    return servicesManager?.services?.studyMetadata?.getCurrentStudy()?.studyInstanceUid || null;
  }, [servicesManager]);

  const handleGenerateReport = async () => {
    const studyInstanceUid = getStudyInstanceUid();
    if (!studyInstanceUid) {
      setStatus({ type: 'error', message: 'No study selected' });
      return;
    }

    setGenerating(true);
    setStatus({ type: 'info', message: 'Generating report...' });

    try {
      const response = await fetch(`/api/v1/reports/studies/${studyInstanceUid}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          template,
          use_ai_polish: useAiPolish,
          ai_tier: aiTier,
          classification: classification || null,
          clinical_indication: clinicalIndication || null,
        }),
      });

      if (!response.ok) {
        throw new Error(`Report generation failed: ${response.status}`);
      }

      const data = await response.json();
      setReport(data);
      setStatus({
        type: 'success',
        message: `Report generated${data.ai_polished ? ' with AI polish' : ''}`,
      });
    } catch (err) {
      setStatus({ type: 'error', message: err.message });
    } finally {
      setGenerating(false);
    }
  };

  const handleExportPdf = async () => {
    if (!report) return;

    try {
      const response = await fetch(`/api/v1/reports/reports/${report.id}/export-pdf`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ report_id: report.id }),
      });

      if (!response.ok) {
        throw new Error(`PDF export failed: ${response.status}`);
      }

      // Download the PDF
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `report_${report.id}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      setStatus({ type: 'success', message: 'PDF downloaded' });
    } catch (err) {
      setStatus({ type: 'error', message: err.message });
    }
  };

  const handleExportDicomSr = async () => {
    if (!report) return;

    try {
      const response = await fetch(`/api/v1/reports/reports/${report.id}/export-dicom-sr`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ report_id: report.id }),
      });

      if (!response.ok) {
        throw new Error(`DICOM-SR export failed: ${response.status}`);
      }

      const data = await response.json();
      setStatus({ type: 'success', message: `DICOM-SR uploaded to PACS (${data.sop_instance_uid})` });
    } catch (err) {
      setStatus({ type: 'error', message: err.message });
    }
  };

  // ─── Voice Dictation ──────────────────────────────────────────────────────
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(chunksRef.current, { type: 'audio/webm' });
        await transcribeAudio(audioBlob);
        stream.getTracks().forEach((track) => track.stop());
      };

      mediaRecorder.start();
      setRecording(true);
      setStatus({ type: 'info', message: 'Recording... click again to stop' });
    } catch (err) {
      setStatus({ type: 'error', message: `Microphone access denied: ${err.message}` });
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
      setRecording(false);
      setStatus({ type: 'info', message: 'Transcribing audio...' });
    }
  };

  const transcribeAudio = async (audioBlob) => {
    try {
      const formData = new FormData();
      formData.append('file', audioBlob, 'dictation.webm');

      const response = await fetch('/api/v1/voice/transcribe', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Transcription failed: ${response.status}`);
      }

      const data = await response.json();
      // In a real implementation, this would insert text into a report editor
      setStatus({ type: 'success', message: `Transcribed: ${data.text.substring(0, 50)}...` });
    } catch (err) {
      setStatus({ type: 'error', message: err.message });
    }
  };

  const toggleRecording = () => {
    if (recording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  // ─── Render ────────────────────────────────────────────────────────────────
  return (
    <div style={styles.container}>
      <h3 style={styles.header}>RadAI Reporting</h3>

      {status && <StatusMessage type={status.type} message={status.message} />}

      {/* Report Generation Controls */}
      <div style={styles.section}>
        <label style={styles.label}>Report Template</label>
        <select
          style={styles.select}
          value={template}
          onChange={(e) => setTemplate(e.target.value)}
        >
          <option value="lung_rads">Lung-RADS CT Chest</option>
          <option value="general_ct">General CT</option>
        </select>
      </div>

      {template === 'lung_rads' && (
        <div style={styles.section}>
          <label style={styles.label}>Lung-RADS Category (optional)</label>
          <select
            style={styles.select}
            value={classification}
            onChange={(e) => setClassification(e.target.value)}
          >
            <option value="">Auto-determine</option>
            <option value="Lung-RADS 1">Lung-RADS 1 (Negative)</option>
            <option value="Lung-RADS 2">Lung-RADS 2 (Benign)</option>
            <option value="Lung-RADS 3">Lung-RADS 3 (Probably Benign)</option>
            <option value="Lung-RADS 4A">Lung-RADS 4A (Suspicious)</option>
            <option value="Lung-RADS 4B">Lung-RADS 4B (Very Suspicious)</option>
          </select>
        </div>
      )}

      <div style={styles.section}>
        <label style={styles.label}>Clinical Indication (optional)</label>
        <input
          type="text"
          style={styles.select}
          placeholder="e.g., Lung cancer screening"
          value={clinicalIndication}
          onChange={(e) => setClinicalIndication(e.target.value)}
        />
      </div>

      <div style={styles.section}>
        <label style={styles.checkbox}>
          <input
            type="checkbox"
            checked={useAiPolish}
            onChange={(e) => setUseAiPolish(e.target.checked)}
          />
          Use AI polish for report prose
        </label>
      </div>

      {useAiPolish && (
        <div style={styles.section}>
          <label style={styles.label}>AI Tier</label>
          <select
            style={styles.select}
            value={aiTier}
            onChange={(e) => setAiTier(parseInt(e.target.value))}
          >
            <option value={1}>Tier 1: Local (MedGemma 4B)</option>
            <option value={2}>Tier 2: Cloud (Gemma 31B)</option>
          </select>
        </div>
      )}

      <button
        style={{
          ...styles.generateBtn,
          opacity: generating ? 0.6 : 1,
        }}
        onClick={handleGenerateReport}
        disabled={generating}
      >
        {generating ? 'Generating...' : 'Generate Report'}
      </button>

      {/* Voice Dictation */}
      <div style={styles.divider} />
      <div style={styles.section}>
        <button
          style={{
            ...styles.voiceBtn,
            ...(recording ? styles.voiceRecording : {}),
          }}
          onClick={toggleRecording}
        >
          {recording ? '⏹ Stop Recording' : '🎤 Voice Dictation'}
        </button>
      </div>

      {/* Report Display */}
      {report && report.content_text && (
        <>
          <div style={styles.divider} />
          <div style={styles.section}>
            <label style={styles.label}>Generated Report</label>
            <div style={styles.reportContent}>{report.content_text}</div>
            {report.ai_polished && (
              <div style={{ ...styles.status, ...styles.statusInfo, marginTop: '8px' }}>
                ✨ AI polished using {report.ai_model_used}
              </div>
            )}
          </div>
        </>
      )}

      {/* Export Buttons */}
      {report && (
        <>
          <div style={styles.divider} />
          <div style={styles.section}>
            <button style={styles.exportBtn} onClick={handleExportPdf}>
              📄 Export PDF
            </button>
            <button style={styles.exportBtn} onClick={handleExportDicomSr}>
              🏥 Export DICOM-SR (upload to PACS)
            </button>
          </div>
        </>
      )}
    </div>
  );
};

// ─── OHIF Extension Definition ──────────────────────────────────────────────
const id = '@radai/extension-reporting-panel';

function getPanelModule() {
  return [
    {
      name: 'radaiReportingPanel',
      component: ReportingPanel,
    },
  ];
}

export default {
  id,
  name: 'RadAI Reporting',
  getPanelModule,
};
