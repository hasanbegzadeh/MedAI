/**
 * RadAI Findings Panel Extension for OHIF v3.12
 *
 * Provides:
 * - List of AI-detected findings for current study
 * - Accept, reject, or modify each finding
 * - Batch operations (accept all, reject all)
 * - Manual finding creation
 * - Radiologist notes per finding
 */

import React, { useState, useEffect, useCallback } from 'react';

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
  findingCard: {
    padding: '10px',
    background: '#1a1a2e',
    borderRadius: '6px',
    marginBottom: '8px',
    border: '1px solid #333',
  },
  findingHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '6px',
  },
  findingType: {
    fontWeight: 600,
    color: '#fff',
    textTransform: 'uppercase',
    fontSize: '12px',
  },
  badge: {
    padding: '2px 6px',
    borderRadius: '3px',
    fontSize: '10px',
    fontWeight: 600,
  },
  statusPending: { background: '#ff9800', color: '#000' },
  statusAccepted: { background: '#4caf50', color: '#fff' },
  statusRejected: { background: '#f44336', color: '#fff' },
  statusModified: { background: '#2196f3', color: '#fff' },
  location: {
    color: '#aaa',
    fontSize: '12px',
    marginBottom: '4px',
  },
  measurements: {
    color: '#888',
    fontSize: '11px',
    marginBottom: '8px',
  },
  actions: {
    display: 'flex',
    gap: '4px',
    marginTop: '8px',
  },
  button: {
    flex: 1,
    padding: '6px 8px',
    border: 'none',
    borderRadius: '4px',
    fontSize: '11px',
    cursor: 'pointer',
    fontWeight: 500,
  },
  acceptBtn: { background: '#4caf50', color: '#fff' },
  rejectBtn: { background: '#f44336', color: '#fff' },
  modifyBtn: { background: '#2196f3', color: '#fff' },
  batchActions: {
    display: 'flex',
    gap: '8px',
    marginBottom: '12px',
  },
  batchBtn: {
    flex: 1,
    padding: '8px',
    border: 'none',
    borderRadius: '4px',
    fontSize: '12px',
    cursor: 'pointer',
    fontWeight: 500,
    background: '#333',
    color: '#ccc',
  },
  notesInput: {
    width: '100%',
    padding: '6px',
    background: '#222',
    border: '1px solid #444',
    borderRadius: '4px',
    color: '#ccc',
    fontSize: '11px',
    resize: 'vertical',
    marginTop: '6px',
  },
  empty: {
    textAlign: 'center',
    color: '#666',
    padding: '24px 0',
  },
  loading: {
    textAlign: 'center',
    padding: '24px 0',
    color: '#888',
  },
  error: {
    background: '#3e1a1a',
    color: '#ff6666',
    padding: '8px',
    borderRadius: '4px',
    marginBottom: '12px',
    fontSize: '12px',
  },
};

// ─── Finding Card Component ──────────────────────────────────────────────────
const FindingCard = ({ finding, onUpdate }) => {
  const [showNotes, setShowNotes] = useState(false);
  const [notes, setNotes] = useState(finding.radiologist_notes || '');

  const statusStyle = {
    pending: styles.statusPending,
    accepted: styles.statusAccepted,
    rejected: styles.statusRejected,
    modified: styles.statusModified,
  }[finding.status] || styles.statusPending;

  const formatMeasurement = (m) => {
    if (!m) return null;
    const parts = [];
    if (m.longest_diameter_mm) parts.push(`${m.longest_diameter_mm.toFixed(1)}mm`);
    if (m.volume_mm3) parts.push(`${m.volume_mm3.toFixed(0)}mm³`);
    if (m.mean_hu !== null && m.mean_hu !== undefined) parts.push(`${m.mean_hu} HU`);
    return parts.join(', ');
  };

  const handleStatusUpdate = async (newStatus) => {
    await onUpdate(finding.id, { status: newStatus, radiologist_notes: notes });
  };

  return (
    <div style={styles.findingCard}>
      <div style={styles.findingHeader}>
        <span style={styles.findingType}>{finding.finding_type}</span>
        <span style={{ ...styles.badge, ...statusStyle }}>{finding.status}</span>
      </div>

      {finding.location && (
        <div style={styles.location}>📍 {finding.location}{finding.laterality ? ` (${finding.laterality})` : ''}</div>
      )}

      {finding.measurements && Object.keys(finding.measurements).length > 0 && (
        <div style={styles.measurements}>📏 {formatMeasurement(finding.measurements)}</div>
      )}

      {finding.confidence && (
        <div style={styles.measurements}>🤖 AI Confidence: {(finding.confidence * 100).toFixed(0)}%</div>
      )}

      {finding.characteristics && finding.characteristics.length > 0 && (
        <div style={styles.measurements}>
          🏷️ {finding.characteristics.join(', ')}
        </div>
      )}

      <div style={styles.actions}>
        <button
          style={{ ...styles.button, ...styles.acceptBtn }}
          onClick={() => handleStatusUpdate('accepted')}
          disabled={finding.status === 'accepted'}
        >
          ✓ Accept
        </button>
        <button
          style={{ ...styles.button, ...styles.rejectBtn }}
          onClick={() => handleStatusUpdate('rejected')}
          disabled={finding.status === 'rejected'}
        >
          ✗ Reject
        </button>
        <button
          style={{ ...styles.button, ...styles.modifyBtn }}
          onClick={() => setShowNotes(!showNotes)}
        >
          📝 Notes
        </button>
      </div>

      {showNotes && (
        <textarea
          style={styles.notesInput}
          rows={2}
          placeholder="Add radiologist notes..."
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          onBlur={() => handleStatusUpdate(finding.status === 'pending' ? 'modified' : finding.status)}
        />
      )}
    </div>
  );
};

// ─── Findings Panel Component ────────────────────────────────────────────────
const FindingsPanel = ({ servicesManager, commandsManager }) => {
  const [findings, setFindings] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [total, setTotal] = useState(0);

  const getStudyInstanceUid = useCallback(() => {
    return servicesManager?.services?.studyMetadata?.getCurrentStudy()?.studyInstanceUid || null;
  }, [servicesManager]);

  const loadFindings = useCallback(async () => {
    const studyInstanceUid = getStudyInstanceUid();
    if (!studyInstanceUid) return;

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`/api/v1/findings/studies/${studyInstanceUid}`, {
        headers: { 'Content-Type': 'application/json' },
      });

      if (!response.ok) {
        throw new Error(`Failed to load findings: ${response.status}`);
      }

      const data = await response.json();
      setFindings(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [getStudyInstanceUid]);

  useEffect(() => {
    loadFindings();
  }, [loadFindings]);

  const handleFindingUpdate = async (findingId, updates) => {
    try {
      const response = await fetch(`/api/v1/findings/${findingId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      });

      if (!response.ok) {
        throw new Error(`Failed to update finding: ${response.status}`);
      }

      // Refresh list
      await loadFindings();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleBatchAction = async (action) => {
    const studyInstanceUid = getStudyInstanceUid();
    if (!studyInstanceUid) return;

    try {
      const response = await fetch(
        `/api/v1/findings/studies/${studyInstanceUid}/batch-review?action=${action}`,
        { method: 'POST' }
      );

      if (!response.ok) {
        throw new Error(`Batch action failed: ${response.status}`);
      }

      await loadFindings();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div style={styles.container}>
      <h3 style={styles.header}>RadAI Findings ({total})</h3>

      {error && <div style={styles.error}>⚠ {error}</div>}

      {findings.length > 0 && (
        <div style={styles.batchActions}>
          <button
            style={styles.batchBtn}
            onClick={() => handleBatchAction('accept_all')}
          >
            ✓ Accept All Pending
          </button>
          <button
            style={styles.batchBtn}
            onClick={() => handleBatchAction('reject_all')}
          >
            ✗ Reject All Pending
          </button>
        </div>
      )}

      {loading ? (
        <div style={styles.loading}>Loading findings...</div>
      ) : findings.length === 0 ? (
        <div style={styles.empty}>
          No findings yet. Run AI analysis to detect abnormalities.
        </div>
      ) : (
        findings.map((finding) => (
          <FindingCard
            key={finding.id}
            finding={finding}
            onUpdate={handleFindingUpdate}
          />
        ))
      )}
    </div>
  );
};

// ─── OHIF Extension Definition ──────────────────────────────────────────────
const id = '@radai/extension-findings-panel';

function getPanelModule() {
  return [
    {
      name: 'radaiFindingsPanel',
      component: FindingsPanel,
    },
  ];
}

export default {
  id,
  name: 'RadAI Findings',
  getPanelModule,
};
