import React from 'react';

/**
 * Stockeye modern AI fintech logo.
 * Style: Minimal, corporate, intelligent. Geometric sans, "o" as an integrated eye/graph.
 *
 * Props:
 *   size     — Base height in pixels. (Width will auto-scale to size * 3.75).
 *   bare     — If true, removes the navy background.
 *   iconOnly — If true, crop just to the "o" symbol.
 */
export default function StockEyeLogo({ size = 36, bare = false, iconOnly = false }) {
  const width = iconOnly ? size * 1.5 : size * 3.75;
  const height = size;

  // ViewBox: Full wordmark is 450x120. Icon focuses directly on the "o" at x:148, y:65.
  const viewBoxStr = iconOnly ? "124 40 50 50" : "0 0 450 120";

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox={viewBoxStr}
      width={width}
      height={height}
      style={{ display: 'block', flexShrink: 0 }}
    >
      {/* Background */}
      {!bare && <rect width="450" height="120" fill="#0A111F" />}

      {/* Typography: "St" */}
      <text
        x="64"
        y="80"
        fontFamily="'Inter', 'Circular', 'Helvetica Neue', sans-serif"
        fontWeight="600"
        fontSize="56"
        letterSpacing="1"
        fill="#F4F5F7"
      >
        St
      </text>

      {/* The geometric "o" eye/graph element
          - Lifted Y to 64 to perfect baseline alignment
          - Broadened radius
          - Tuned stroke down slightly so the inner gap breathes better
      */}
      <g transform="translate(148, 64)">
        {/* Outer Circular Stroke: Much more generous inner space (radius 15.5) */}
        <circle cx="0" cy="0" r="15.5" fill="none" stroke="#F4F5F7" strokeWidth="6" />

        {/* Internal Graph Line: Smooth upward curve, 3 points. Taller amplitude. */}
        <path
          d="M -7 4 L -2 -1 L 2 3 L 8 -6"
          fill="none"
          stroke="#00FF88"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Internal Pupil Dot: Sharp center */}
        <circle cx="0" cy="0" r="2" fill="#00FF88" />
      </g>

      {/* Typography: "ckeye" */}
      <text
        x="172"
        y="80"
        fontFamily="'Inter', 'Circular', 'Helvetica Neue', sans-serif"
        fontWeight="600"
        fontSize="56"
        letterSpacing="1"
        fill="#F4F5F7"
      >
        ckeye
      </text>
    </svg>
  );
}
