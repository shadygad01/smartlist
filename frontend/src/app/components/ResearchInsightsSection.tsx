'use client';

import React, { useState } from 'react';
import { FlaskConical, ChevronDown, ChevronUp } from 'lucide-react';
import { useSnapshot } from '@/providers/SnapshotProvider';

function confidenceColor(conf: string): string {
  if (conf === 'HIGH')   return 'var(--signal-buy)';
  if (conf === 'MEDIUM') return 'var(--signal-near)';
  return 'var(--muted-foreground)';
}

function confidenceBg(conf: string): string {
  if (conf === 'HIGH')   return 'rgba(16,185,129,0.08)';
  if (conf === 'MEDIUM') return 'rgba(245,158,11,0.08)';
  return 'rgba(255,255,255,0.04)';
}

function confidenceBorder(conf: string): string {
  if (conf === 'HIGH')   return 'rgba(16,185,129,0.2)';
  if (conf === 'MEDIUM') return 'rgba(245,158,11,0.2)';
  return 'var(--border)';
}

export default function ResearchInsightsSection() {
  const { snapshot, loading } = useSnapshot();
  const [collapsed, setCollapsed] = useState(false);

  const insights = snapshot?.research_insights ?? [];
  const knowledgeCount = snapshot?.knowledge_count ?? 0;

  if (!loading && insights.length === 0) return null;

  return (
    <div
      className="rounded-xl"
      style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)', boxShadow: '0 2px 16px rgba(0,0,0,0.3)' }}
    >
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="section-header-btn w-full flex items-center justify-between px-4 py-3.5 rounded-t-xl"
        style={{ borderBottom: collapsed ? 'none' : '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <FlaskConical size={13} style={{ color: 'var(--signal-reaccum)' }} />
          <span className="font-mono font-semibold" style={{ fontSize: '12px', color: 'var(--foreground)', letterSpacing: '0.07em' }}>
            RESEARCH INSIGHTS
          </span>
          <span
            className="font-mono px-2 py-0.5 rounded-md"
            style={{ fontSize: '9px', backgroundColor: 'rgba(59,130,246,0.1)', color: 'var(--signal-reaccum)', border: '1px solid rgba(59,130,246,0.2)' }}
          >
            {loading ? '…' : `${knowledgeCount} VERIFIED FINDINGS`}
          </span>
        </div>
        {collapsed
          ? <ChevronDown size={13} style={{ color: 'var(--muted-foreground)' }} />
          : <ChevronUp size={13} style={{ color: 'var(--muted-foreground)' }} />}
      </button>

      {!collapsed && (
        <div className="p-3 flex flex-col gap-2">
          {loading ? (
            <div className="flex items-center justify-center py-6">
              <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>Loading…</span>
            </div>
          ) : (
            insights.map((ins, i) => (
              <div
                key={i}
                className="px-3 py-3 rounded-xl"
                style={{ backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}
              >
                <div className="flex items-start justify-between gap-3 mb-1.5">
                  <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)', flex: 1, minWidth: 0 }}>
                    {ins.question}
                  </span>
                  <span
                    className="font-mono font-bold px-2 py-0.5 rounded-md flex-shrink-0"
                    style={{
                      fontSize: '9px',
                      color: confidenceColor(ins.confidence),
                      backgroundColor: confidenceBg(ins.confidence),
                      border: `1px solid ${confidenceBorder(ins.confidence)}`,
                      letterSpacing: '0.06em',
                    }}
                  >
                    {ins.confidence}
                  </span>
                </div>
                <p className="font-mono" style={{ fontSize: '11px', color: 'var(--foreground)' }}>
                  {ins.conclusion}
                </p>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
