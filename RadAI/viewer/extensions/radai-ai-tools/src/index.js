/**
 * RadAI AI Tools Panel Extension for OHIF v3.12
 *
 * Provides:
 * - "Run AI Analysis" button to trigger TotalSegmentator
 * - Live progress bar for AI jobs
 * - List of completed segmentation jobs
 */

import React, { useState, useEffect } from 'react';

// ─── AI Panel Component ─────────────────────────────────────────────────────
const AIPanel = ({ servicesManager, commandsManager }) => {
  const { studyInstanceUid } = servicesManager.services.studyMetadata.getCurrentStudy() || {};
  const [jobs, setJobs] = useState([]);
  const [running, setRunning] = useState(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState(null);

  const runTotalSegmentator = async () => {
    if (!studyInstanceUid) {
      setError('No study selected');
      return;
    }

    setRunning('totalsegmentator');
    setProgress(0);
    setError(null);

    try {
      // Call RadAI backend
      const response = await fetch(`/api/v1/ai/studies/${studyInstanceUid}/run`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          // Auth token would be injected from OHIF auth service
        },
        body: JSON.stringify({
          job_type: 'totalsegmentator',
          fast: true,
          tier: 1,
        }),
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const job = await response.json();
      setJobs(prev => [...prev, job]);

      // Poll for progress
      const pollInterval = setInterval(async () => {
        const statusResp = await fetch(`/api/v1/ai/jobs/${job.id}`);
        const jobStatus = await statusResp.json();
        setProgress(jobStatus.progress_pct);

        if (jobStatus.status === 'completed') {
          clearInterval(pollInterval);
          setRunning(null);
          setProgress(100);
        } else if (jobStatus.status === 'failed') {
          clearInterval(pollInterval);
          setRunning(null);
          setError(jobStatus.error_message);
        }
      }, 2000);
    } catch (err) {
      setRunning(null);
      setError(err.message);
    }
  };

  return (
    <div style={{ padding: '16px', color: '#ccc', fontSize: '14px' }}>
      <h3 style={{ margin: '0 0 12px', color: '#fff' }}>RadAI AI Tools</h3>

      <button
        onClick={runTotalSegmentator}
        disabled={running || !studyInstanceUid}
        style={{
          width: '100%',
          padding: '10px',
          background: running ? '#666' : '#0066cc',
          color: 'white',
          border: 'none',
          borderRadius: '4px',
          cursor: running ? 'not-allowed' : 'pointer',
          fontSize: '14px',
        }}
      >
        {running === 'totalsegmentator' ? 'Running...' : 'Run TotalSegmentator'}
      </button>

      {running && (
        <div style={{ marginTop: '12px' }}>
          <div style={{ background: '#333', borderRadius: '4px', overflow: 'hidden' }}>
            <div
              style={{
                width: `${progress}%`,
                background: '#00cc66',
                padding: '4px 8px',
                transition: 'width 0.3s',
              }}
            >
              {progress}%
            </div>
          </div>
        </div>
      )}

      {error && (
        <div style={{ marginTop: '12px', color: '#ff6666', fontSize: '12px' }}>
          Error: {error}
        </div>
      )}

      {jobs.length > 0 && (
        <div style={{ marginTop: '16px' }}>
          <h4 style={{ margin: '0 0 8px', color: '#fff' }}>Completed Jobs</h4>
          {jobs.map(job => (
            <div
              key={job.id}
              style={{
                padding: '8px',
                background: '#222',
                borderRadius: '4px',
                marginBottom: '4px',
                fontSize: '12px',
              }}
            >
              <div>{job.job_type}</div>
              <div style={{ color: '#888' }}>Status: {job.status}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ─── OHIF Extension Definition ──────────────────────────────────────────────
const id = '@radai/extension-ai-panel';

/**
 * Get the panel module definition
 */
function getPanelModule() {
  return [
    {
      name: 'radaiAiPanel',
      component: AIPanel,
    },
  ];
}

/**
 * Extension entry point
 */
export default {
  id,
  name: 'RadAI AI Tools',
  getPanelModule,
};
