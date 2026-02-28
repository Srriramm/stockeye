import React from 'react';

/**
 * Institutional wordmark: S T [EYE] C K E Y E
 * Transparent background. The eye symbol replaces the O.
 *
 * Props:
 *   width   — rendered pixel width (height auto from 3:1 aspect ratio)
 *   variant — 'light' (white letterforms, for dark backgrounds)
 *             'dark'  (navy letterforms, for light backgrounds)
 */
export default function StockEyeWordmark({ width = 300, variant = 'light' }) {
  const uid = React.useId().replace(/:/g, '');
  const height = Math.round(width * (400 / 1200));

  const c0 = variant === 'light' ? '#e6ebf2' : '#0f172a';
  const c1 = variant === 'light' ? '#dbe2eb' : '#1e293b';
  const microLine = variant === 'light' ? '#091320' : '#f1f5f9';
  const ruleLine  = variant === 'light' ? '#1a2840' : '#e2e8f0';

  const font = "'Neue Haas Grotesk Display','Helvetica Neue','Suisse Intl','Aktiv Grotesk',Helvetica,Arial,sans-serif";

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 1200 400"
      width={width}
      height={height}
      style={{ display: 'block' }}
    >
      <defs>
        <linearGradient id={`wm-fill-${uid}`} x1="0" y1="160" x2="0" y2="250" gradientUnits="userSpaceOnUse">
          <stop offset="0%"   stopColor={c0} />
          <stop offset="100%" stopColor={c1} />
        </linearGradient>
      </defs>

      {/* ── "ST" ── */}
      <text
        x="225" y="240"
        fontFamily={font}
        fontWeight="500"
        fontSize="112"
        letterSpacing="5"
        fill={`url(#wm-fill-${uid})`}
        textRendering="geometricPrecision"
      >ST</text>

      {/* ── "CKEYE" ── */}
      <text
        x="510" y="240"
        fontFamily={font}
        fontWeight="500"
        fontSize="112"
        letterSpacing="5"
        fill={`url(#wm-fill-${uid})`}
        textRendering="geometricPrecision"
      >CKEYE</text>

      {/* ── Geometric eye symbol — replaces O ── */}
      <g transform="translate(444,199)">
        {/* Outer almond */}
        <path
          d="M -44,0 C -36,-22 -20,-40 0,-40 C 20,-40 36,-22 44,0 C 36,22 20,40 0,40 C -20,40 -36,22 -44,0 Z"
          fill="none"
          stroke={`url(#wm-fill-${uid})`}
          strokeWidth="9.5"
          strokeLinejoin="round"
        />
        {/* Iris ring */}
        <circle cx="0" cy="0" r="19" fill="none" stroke={`url(#wm-fill-${uid})`} strokeWidth="7.5" />
        {/* Pupil */}
        <circle cx="0" cy="0" r="10.5" fill={`url(#wm-fill-${uid})`} />
        {/* Micro trend line inside pupil */}
        <polyline
          points="-6,3.5 -2.2,0.8 1.5,2.8 6,-4.5"
          fill="none"
          stroke={microLine}
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </g>

      {/* Subtle rule line */}
      <line x1="170" y1="280" x2="980" y2="280" stroke={ruleLine} strokeWidth="0.5" opacity="0.35" />
    </svg>
  );
}
