import React from 'react';

/**
 * StockEye custom logo — an eye with a stock trend line inside,
 * on a blue-violet gradient rounded square background.
 *
 * Props:
 *   size     — pixel size (width = height), default 36
 *   bare     — if true, renders just the eye SVG without the rounded-square bg
 *              (useful when you supply your own container)
 */
export default function StockEyeLogo({ size = 36, bare = false }) {
  // Unique ID suffix so multiple instances don't clash on gradients / clipPaths
  const uid = React.useId().replace(/:/g, '');

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 36 36"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={{ display: 'block', flexShrink: 0 }}
    >
      <defs>
        {/* Background gradient */}
        <linearGradient id={`bg-${uid}`} x1="0" y1="0" x2="36" y2="36" gradientUnits="userSpaceOnUse">
          <stop offset="0%"   stopColor="#2563EB" />
          <stop offset="100%" stopColor="#7C3AED" />
        </linearGradient>

        {/* Chart line gradient (light → lighter) */}
        <linearGradient id={`line-${uid}`} x1="6" y1="18" x2="30" y2="18" gradientUnits="userSpaceOnUse">
          <stop offset="0%"   stopColor="#93C5FD" />
          <stop offset="100%" stopColor="#E0CFFF" />
        </linearGradient>

        {/* Clip path = eye shape, so the chart line is masked to the eye */}
        <clipPath id={`eye-${uid}`}>
          <path d="M5 18C8 12 12.5 9.5 18 9.5C23.5 9.5 28 12 31 18C28 24 23.5 26.5 18 26.5C12.5 26.5 8 24 5 18Z" />
        </clipPath>
      </defs>

      {/* ── Rounded square background ── */}
      {!bare && (
        <rect width="36" height="36" rx="9" fill={`url(#bg-${uid})`} />
      )}

      {/* ── Eye whites ── */}
      <path
        d="M5 18C8 12 12.5 9.5 18 9.5C23.5 9.5 28 12 31 18C28 24 23.5 26.5 18 26.5C12.5 26.5 8 24 5 18Z"
        fill="white"
      />

      {/* ── Iris ── */}
      <circle cx="18" cy="18" r="5.8" fill="#1E3A8A" />

      {/* ── Stock chart line (clipped inside eye) ── */}
      <g clipPath={`url(#eye-${uid})`}>
        <polyline
          points="5,23 9,17 13,20 17,13 22,17 30,10"
          stroke={`url(#line-${uid})`}
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      </g>

      {/* ── Pupil ── */}
      <circle cx="18" cy="18" r="2.2" fill="white" />

      {/* ── Specular highlight ── */}
      <circle cx="20.5" cy="15.5" r="1.1" fill="rgba(255,255,255,0.55)" />
    </svg>
  );
}
