import React from 'react';

/**
 * StockEye text logo — Poppins Bold 700.
 * The letter "o" in "Stockeye" pulses blue → teal in a continuous loop.
 *
 * Props
 *   size     — approximate height in px (controls font-size proportionally)
 *   dark     — true = white text for dark backgrounds (login page)
 *              false (default) = dark text for light backgrounds (sidebar)
 *   iconOnly — true = renders only the animated "o" (collapsed sidebar icon)
 */
export default function StockEyeLogo({ size = 36, dark = false, iconOnly = false }) {
  const animId   = React.useId().replace(/:/g, '');
  const kf       = `se_o_${animId}`;
  const fontSize = Math.round(size * 0.58);
  const textColor = dark ? '#f1f5f9' : '#0f172a';

  const font = "'Poppins', 'Nunito', 'Google Sans', system-ui, sans-serif";

  const keyframes = `
    @keyframes ${kf} {
      0%, 100% { color: ${textColor}; text-shadow: none; }
      40%  { color: #3b82f6; text-shadow: 0 0 14px rgba(59,130,246,0.55); }
      60%  { color: #06b6d4; text-shadow: 0 0 14px rgba(6,182,212,0.55); }
    }
  `;

  const oStyle = {
    display: 'inline-block',
    animation: `${kf} 2.6s ease-in-out infinite`,
  };

  if (iconOnly) {
    const iconSize = Math.round(size * 0.9);
    return (
      <span style={{ fontFamily: font, fontWeight: 700, fontSize: iconSize, lineHeight: 1 }}>
        <span style={oStyle}>o</span>
        <style>{keyframes}</style>
      </span>
    );
  }

  return (
    <span style={{
      fontFamily: font,
      fontWeight: 700,
      fontSize,
      color: textColor,
      lineHeight: 1,
      letterSpacing: '-0.02em',
      display: 'inline-block',
    }}>
      St<span style={oStyle}>o</span>ckeye
      <style>{keyframes}</style>
    </span>
  );
}
