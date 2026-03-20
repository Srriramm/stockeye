import React from 'react';

/**
 * StockEye Executive Wordmark.
 * A world-class minimalist identity for a premium AI trading platform.
 * 
 * Props:
 *   size     — Overall height in px
 *   dark     — true for white text
 *   iconOnly — true for collapsed sidebar (renders the abstract sensor mark)
 */
export default function StockEyeLogo({ size = 32, dark = false, iconOnly = false }) {
  const animId = React.useId().replace(/:/g, '');
  const textColor = dark ? '#F8FAFC' : '#0F172A';
  const brandBlue = '#2563EB';

  const h = size;
  const sensorSize = h * 0.7;

  if (iconOnly) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: h }}>
        <svg width={sensorSize} height={sensorSize} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect x="10" y="48" width="80" height="4" rx="2" fill={brandBlue} />
          <circle cx="50" cy="50" r="10" fill={brandBlue}>
            <animate attributeName="opacity" values="0.5;1;0.5" dur="2s" repeatCount="indefinite" />
          </circle>
        </svg>
      </div>
    );
  }

  return (
    <div style={{
      display: 'inline-flex',
      flexDirection: 'column',
      alignItems: 'flex-start',
      height: h,
      fontFamily: "'Inter', system-ui, sans-serif",
      userSelect: 'none',
      cursor: 'pointer'
    }}>
      {/* ─── TECHNICAL MONITORING BAR ─── */}
      <div style={{
        width: '100%',
        height: h * 0.05,
        marginBottom: h * 0.08,
        position: 'relative',
        display: 'flex',
        justifyContent: 'flex-end'
      }}>
        <div style={{
          width: '35%',
          height: '100%',
          background: brandBlue,
          borderRadius: '4px',
          opacity: 0.8,
          position: 'relative',
          overflow: 'hidden'
        }}>
          <div style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '20%',
            height: '100%',
            background: '#FFFFFF',
            filter: 'blur(2px)',
            animation: `shimmer_${animId} 3s infinite linear`
          }} />
        </div>
      </div>

      {/* ─── EXECUTIVE WORDMARK ─── */}
      <div style={{
        display: 'flex',
        alignItems: 'baseline',
        fontSize: h * 0.75,
        fontWeight: 600,
        color: textColor,
        letterSpacing: '-0.045em',
        lineHeight: 1
      }}>
        <span style={{ opacity: 0.8 }}>Stock</span>
        <span style={{ color: brandBlue, fontWeight: 800 }}>Eye</span>
      </div>

      <style>{`
        @keyframes shimmer_${animId} {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(500%); }
        }
      `}</style>
    </div>
  );
}
