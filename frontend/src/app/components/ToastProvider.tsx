'use client';

import React from 'react';
import { Toaster } from 'sonner';

export default function ToastProvider() {
  return (
    <Toaster
      position="bottom-right"
      toastOptions={{
        style: {
          background: '#0f1629',
          border: '1px solid #1e2d4a',
          color: '#e2e8f0',
          fontFamily: 'var(--font-dm-sans)',
          fontSize: '13px',
        },
      }}
    />
  );
}