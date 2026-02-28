import React from 'react';

/**
 * Stockeye modern AI fintech logo.
 * Style: Minimal, corporate, intelligent. Geometric sans, "o" as an integrated eye/graph.
 *
 * Props:
 *   size     — Base height in pixels. (Width will auto-scale to roughly size * 4.6).
 *   bare     — If true, removes the navy background.
 *   iconOnly — If true, crop just to the "o" symbol.
 */
export default function StockEyeLogo({ size = 36, bare = false, iconOnly = false }) {
  const width = iconOnly ? size * 1.2 : size * 4.6;
  const height = size;

  // ViewBox: Full wordmark is ~ 550x120. Icon only focuses on the "o" at x:200.
  const viewBoxStr = iconOnly ? "188 35 44 44" : "0 0 550 120";

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox={viewBoxStr}
      width={width}
      height={height}
      style={{ display: 'block', flexShrink: 0 }}
    >
      {/* Background */}
      {!bare && <rect width="550" height="120" fill="#0A111F" />}

      {/* Typography: "St" */}
      <text
        x="60"
        y="80"
        fontFamily="'Inter', 'Circular', 'Helvetica Neue', sans-serif"
        fontWeight="600"
        fontSize="56"
        letterSpacing="1.5"
        fill="#F4F5F7"
      >
        St
      </text>

      {/* The geometric "o" eye/graph element */}
      <g transform="translate(210, 57)">
        {/* Outer Circular Stroke (Slightly thicker than other letters for balance, strictly 1 circle) */}
        <circle cx="0" cy="0" r="18" fill="none" stroke="#F4F5F7" strokeWidth="6" />

        {/* Internal Graph Line (Hairline weight, clean upward trend, 3 anchor points) */}
        <path
          d="M -9 4 L -2 -1 L 2 2 L 9 -5"
          fill="none"
          stroke="#00FF88"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Internal Pupil Dot */}
        <circle cx="0" cy="0" r="2.5" fill="#00FF88" />
      </g>

      {/* Typography: "ckeye" */}
      <text
        x="245"
        y="80"
        fontFamily="'Inter', 'Circular', 'Helvetica Neue', sans-serif"
        fontWeight="600"
        fontSize="56"
        letterSpacing="1.5"
        fill="#F4F5F7"
      >
        ckeye
      </text>
    </svg>
  );
}
