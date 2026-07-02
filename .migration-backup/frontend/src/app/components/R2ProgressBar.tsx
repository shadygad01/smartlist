'use client';

import React, { useEffect, useState } from 'react';

interface R2ProgressBarProps {
  value: number; // 0–1
  color?: string;
  height?: number;
}

export default function R2ProgressBar({
  value,
  color = 'var(--signal-reaccum)',
  height = 6,
}: R2ProgressBarProps) {
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => {
      setWidth(value * 100);
    }, 100);
    return () => clearTimeout(timer);
  }, [value]);

  return (
    <div
      className="w-full rounded-full overflow-hidden"
      style={{ height: `${height}px`, backgroundColor: 'rgba(255,255,255,0.08)' }}
    >
      <div
        className="h-full rounded-full"
        style={{
          width: `${width}%`,
          background: `linear-gradient(90deg, ${color}88 0%, ${color} 100%)`,
          transition: 'width 800ms cubic-bezier(0.4, 0, 0.2, 1)',
        }}
      />
    </div>
  );
}