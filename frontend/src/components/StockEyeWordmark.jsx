import React from 'react';

/**
 * Animated institutional wordmark — STOCKEYE with eye replacing O.
 * Transparent background. Designed for dark surfaces.
 *
 * Props:
 *   width  — rendered pixel width (height auto-calculated from 3:1 ratio)
 */
export default function StockEyeWordmark({ width = 300 }) {
  const uid = React.useId().replace(/:/g, '');
  const height = Math.round(width * (400 / 1200));

  const font = "'Nunito', 'Google Sans', 'Helvetica Neue', system-ui, sans-serif";
  const lt   = `url(#lt-${uid})`;
  const eye  = `url(#eye-${uid})`;
  const glow = `url(#glow-${uid})`;
  const scan = `url(#scan-${uid})`;
  const rule = `url(#rule-${uid})`;

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 1200 400"
      width={width}
      height={height}
      style={{ display: 'block' }}
    >
      <defs>
        {/* ── Letterform gradient — silver → blue → teal → gold loop ── */}
        <linearGradient id={`lt-${uid}`} x1="140" y1="160" x2="1000" y2="260" gradientUnits="userSpaceOnUse">
          <stop offset="0%">
            <animate attributeName="stop-color" values="#c8d4e0;#7eb8d4;#5ab0a0;#d4c28a;#c8d4e0" dur="8s" repeatCount="indefinite"/>
          </stop>
          <stop offset="30%">
            <animate attributeName="stop-color" values="#a0b8cc;#5ca8c8;#48b89c;#c8b878;#a0b8cc" dur="8s" repeatCount="indefinite"/>
          </stop>
          <stop offset="60%">
            <animate attributeName="stop-color" values="#7ea8c0;#4ca0b8;#3cb090;#bca868;#7ea8c0" dur="8s" repeatCount="indefinite"/>
          </stop>
          <stop offset="100%">
            <animate attributeName="stop-color" values="#6098b0;#3c98b0;#38a888;#b09858;#6098b0" dur="8s" repeatCount="indefinite"/>
          </stop>
        </linearGradient>

        {/* ── Eye symbol accent ── */}
        <linearGradient id={`eye-${uid}`} x1="-44" y1="-40" x2="44" y2="40" gradientUnits="userSpaceOnUse">
          <stop offset="0%">
            <animate attributeName="stop-color" values="#d0dce8;#90d0e8;#6cd4b8;#e0d098;#d0dce8" dur="8s" repeatCount="indefinite"/>
          </stop>
          <stop offset="100%">
            <animate attributeName="stop-color" values="#90a8c0;#58b8d0;#48c8a0;#c8b070;#90a8c0" dur="8s" repeatCount="indefinite"/>
          </stop>
        </linearGradient>

        {/* ── Iris glow pulse ── */}
        <radialGradient id={`glow-${uid}`} cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopOpacity="0.4">
            <animate attributeName="stop-color" values="#a0c8d8;#70c8e0;#58d0b0;#d8c888;#a0c8d8" dur="8s" repeatCount="indefinite"/>
          </stop>
          <stop offset="100%" stopColor="#000000" stopOpacity="0"/>
        </radialGradient>

        {/* ── Scan line ── */}
        <linearGradient id={`scan-${uid}`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopOpacity="0.6">
            <animate attributeName="stop-color" values="#b0d0e0;#80d0e8;#60d8b8;#d8c890;#b0d0e0" dur="8s" repeatCount="indefinite"/>
          </stop>
          <stop offset="100%" stopOpacity="0">
            <animate attributeName="stop-color" values="#b0d0e0;#80d0e8;#60d8b8;#d8c890;#b0d0e0" dur="8s" repeatCount="indefinite"/>
          </stop>
        </linearGradient>

        {/* ── Baseline rule ── */}
        <linearGradient id={`rule-${uid}`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopOpacity="0.25">
            <animate attributeName="stop-color" values="#405060;#386878;#307060;#706840;#405060" dur="8s" repeatCount="indefinite"/>
          </stop>
          <stop offset="50%" stopOpacity="0.15">
            <animate attributeName="stop-color" values="#304050;#285868;#206050;#605830;#304050" dur="8s" repeatCount="indefinite"/>
          </stop>
          <stop offset="100%" stopOpacity="0">
            <animate attributeName="stop-color" values="#182028;#183040;#184030;#403018;#182028" dur="8s" repeatCount="indefinite"/>
          </stop>
        </linearGradient>
      </defs>

      {/* ── "ST" ── */}
      <text x="225" y="240" fontFamily={font} fontWeight="700" fontSize="112" letterSpacing="5"
        fill={lt} textRendering="geometricPrecision">ST</text>

      {/* ── "CKEYE" ── */}
      <text x="510" y="240" fontFamily={font} fontWeight="700" fontSize="112" letterSpacing="5"
        fill={lt} textRendering="geometricPrecision">CKEYE</text>

      {/* ── Geometric eye (replaces O) ── */}
      <g transform="translate(444,199)">

        {/* Ambient glow pulse */}
        <circle cx="0" cy="0" r="32" fill={glow} opacity="0">
          <animate attributeName="opacity" values="0;0.7;0" dur="4s" repeatCount="indefinite"
            calcMode="spline" keySplines="0.4 0 0.2 1;0.4 0 0.2 1"/>
          <animate attributeName="r" values="30;40;30" dur="4s" repeatCount="indefinite"
            calcMode="spline" keySplines="0.4 0 0.2 1;0.4 0 0.2 1"/>
        </circle>

        {/* Outer almond */}
        <path d="M -44,0 C -36,-22 -20,-40 0,-40 C 20,-40 36,-22 44,0 C 36,22 20,40 0,40 C -20,40 -36,22 -44,0 Z"
          fill="none" stroke={eye} strokeWidth="9.5" strokeLinejoin="round"/>

        {/* Iris ring — breathing */}
        <circle cx="0" cy="0" r="19" fill="none" stroke={eye} strokeWidth="7.5">
          <animate attributeName="r" values="19;20.5;19" dur="4s" repeatCount="indefinite"
            calcMode="spline" keySplines="0.4 0 0.2 1;0.4 0 0.2 1"/>
          <animate attributeName="stroke-width" values="7.5;6.2;7.5" dur="4s" repeatCount="indefinite"
            calcMode="spline" keySplines="0.4 0 0.2 1;0.4 0 0.2 1"/>
        </circle>

        {/* Pupil — dilation */}
        <circle cx="0" cy="0" r="10.5" fill={eye}>
          <animate attributeName="r" values="10.5;8;10.5" dur="4s" repeatCount="indefinite"
            calcMode="spline" keySplines="0.4 0 0.2 1;0.4 0 0.2 1"/>
        </circle>

        {/* Micro trend line — draw-on loop */}
        <polyline points="-6,3.5 -2.2,0.8 1.5,2.8 6,-4.5"
          fill="none" stroke="#060e18" strokeWidth="1.8"
          strokeLinecap="round" strokeLinejoin="round"
          strokeDasharray="22" strokeDashoffset="22">
          <animate attributeName="stroke-dashoffset"
            values="22;0;0;22" keyTimes="0;0.3;0.7;1"
            dur="4s" repeatCount="indefinite"
            calcMode="spline" keySplines="0.4 0 0.2 1;0.1 0 0.1 1;0.4 0 0.2 1"/>
        </polyline>

        {/* Scan line sweep */}
        <line x1="-38" y1="0" x2="38" y2="0"
          stroke={scan} strokeWidth="1.2" opacity="0" strokeLinecap="round">
          <animate attributeName="y1" values="-36;36;-36" dur="6s" repeatCount="indefinite"
            calcMode="spline" keySplines="0.3 0 0.7 1;0.3 0 0.7 1"/>
          <animate attributeName="y2" values="-36;36;-36" dur="6s" repeatCount="indefinite"
            calcMode="spline" keySplines="0.3 0 0.7 1;0.3 0 0.7 1"/>
          <animate attributeName="opacity"
            values="0;0.5;0.5;0.5;0" keyTimes="0;0.05;0.5;0.95;1" dur="6s" repeatCount="indefinite"/>
        </line>

        {/* Highlight ring flash */}
        <circle cx="0" cy="0" r="14" fill="none" strokeWidth="1.2" opacity="0">
          <animate attributeName="stroke"
            values="#b0d0e0;#80d0e8;#60d8b8;#d8c890;#b0d0e0" dur="8s" repeatCount="indefinite"/>
          <animate attributeName="opacity" values="0;0.55;0" dur="4s" repeatCount="indefinite"
            calcMode="spline" keySplines="0.4 0 0.2 1;0.4 0 0.2 1"/>
          <animate attributeName="r" values="12;17;12" dur="4s" repeatCount="indefinite"
            calcMode="spline" keySplines="0.4 0 0.2 1;0.4 0 0.2 1"/>
        </circle>
      </g>

      {/* Animated baseline rule */}
      <line x1="170" y1="280" x2="980" y2="280" stroke={rule} strokeWidth="0.75"/>
    </svg>
  );
}
