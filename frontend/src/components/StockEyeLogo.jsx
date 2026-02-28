import React from 'react';

/**
 * StockEye full wordmark logo (integrated animated eye and ticker).
 * Aspect Ratio: 3:1 (1200x400) full, 1:1 icon only
 *
 * Props:
 *   size     — Base height in pixels. (Width will auto-scale to size * 3, or size if iconOnly).
 *   bare     — If true, removes the background rectangle to blend into headers.
 *   iconOnly — If true, zooms SVG viewBox to just the animated eye.
 */
export default function StockEyeLogo({ size = 36, bare = false, iconOnly = false }) {
  const uid = React.useId().replace(/:/g, '');
  const width = iconOnly ? size * 1.5 : size * 3;
  const height = size;

  // Crop to just the animated eye bounds
  const viewBoxStr = iconOnly ? "380 140 130 130" : "0 0 1200 400";

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox={viewBoxStr}
      width={width}
      height={height}
      style={{ display: 'block', flexShrink: 0 }}
    >
      <defs>
        <linearGradient id={`bgGrad-${uid}`} x1="0" y1="0" x2="1200" y2="400" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#04080f" />
          <stop offset="50%" stopColor="#08101e" />
          <stop offset="100%" stopColor="#0b1520" />
        </linearGradient>

        <linearGradient id={`ltFill-${uid}`} x1="140" y1="160" x2="1000" y2="260" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#8ca0b4" />
          <stop offset="25%" stopColor="#a8bcd0" />
          <stop offset="50%" stopColor="#c0d0dc" />
          <stop offset="75%" stopColor="#a8bcd0" />
          <stop offset="100%" stopColor="#8ca0b4" />
        </linearGradient>

        <linearGradient id={`shine-${uid}`} x1="0" y1="0" x2="200" y2="0" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0" />
          <stop offset="40%" stopColor="#ffffff" stopOpacity="0" />
          <stop offset="50%" stopColor="#ffffff" stopOpacity="0.7" />
          <stop offset="60%" stopColor="#ffffff" stopOpacity="0" />
          <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
          <animateTransform attributeName="gradientTransform" type="translate" values="-200,0;1100,0;1100,0" keyTimes="0;0.6;1" dur="5s" repeatCount="indefinite" />
        </linearGradient>

        <linearGradient id={`eyeFill-${uid}`} x1="-44" y1="-40" x2="44" y2="40" gradientUnits="objectBoundingBox">
          <stop offset="0%">
            <animate attributeName="stop-color" values="#a0c8d8;#70d4b8;#d4c88a;#a0c8d8" dur="8s" repeatCount="indefinite" />
          </stop>
          <stop offset="100%">
            <animate attributeName="stop-color" values="#6098b0;#48b890;#b8a060;#6098b0" dur="8s" repeatCount="indefinite" />
          </stop>
        </linearGradient>

        <radialGradient id={`irisGlow-${uid}`} cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopOpacity="0.4">
            <animate attributeName="stop-color" values="#80d0e0;#60d8b0;#d0c080;#80d0e0" dur="8s" repeatCount="indefinite" />
          </stop>
          <stop offset="100%" stopColor="#000" stopOpacity="0" />
        </radialGradient>

        <linearGradient id={`tickerGrad-${uid}`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#2a8a6a" stopOpacity="0" />
          <stop offset="15%" stopColor="#2a8a6a" stopOpacity="0.6" />
          <stop offset="85%" stopColor="#30c888" stopOpacity="0.6" />
          <stop offset="100%" stopColor="#30c888" stopOpacity="0" />
        </linearGradient>

        <clipPath id={`textClip-${uid}`}>
          <text x="225" y="240"
            fontFamily="'Neue Haas Grotesk Display','Helvetica Neue','Suisse Intl','Aktiv Grotesk',Helvetica,Arial,sans-serif"
            fontWeight="500" fontSize="112" letterSpacing="5">ST</text>
          <text x="510" y="240"
            fontFamily="'Neue Haas Grotesk Display','Helvetica Neue','Suisse Intl','Aktiv Grotesk',Helvetica,Arial,sans-serif"
            fontWeight="500" fontSize="112" letterSpacing="5">CKEYE</text>
          <path transform="translate(444,199)" d="M-44,0 C-36,-22 -20,-40 0,-40 C20,-40 36,-22 44,0 C36,22 20,40 0,40 C-20,40 -36,22 -44,0Z" />
          <circle cx="444" cy="199" r="23" />
        </clipPath>

        <radialGradient id={`greenPulse-${uid}`} cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#40e890" stopOpacity="0.8" />
          <stop offset="100%" stopColor="#40e890" stopOpacity="0" />
        </radialGradient>

      </defs>

      {!bare && <rect width="1200" height="400" fill={`url(#bgGrad-${uid})`} />}

      <g opacity="0.35">
        <polyline
          fill="none" stroke={`url(#tickerGrad-${uid})`} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
          points="160,290 190,288 210,292 240,285 265,287 290,278 310,282 340,274 365,276 390,268 420,272 445,264 470,268 500,260 525,265 550,256 575,262 600,254 625,258 650,248 680,252 700,244 730,250 755,242 780,246 810,236 840,240 870,232 900,238 930,228 960,234 990,225"
          strokeDasharray="1200"
          strokeDashoffset="1200">
          <animate attributeName="stroke-dashoffset" values="1200;0" dur="4s" fill="freeze" repeatCount="indefinite" />
        </polyline>
        <polygon
          fill="#30c888" opacity="0.06"
          points="160,290 190,288 210,292 240,285 265,287 290,278 310,282 340,274 365,276 390,268 420,272 445,264 470,268 500,260 525,265 550,256 575,262 600,254 625,258 650,248 680,252 700,244 730,250 755,242 780,246 810,236 840,240 870,232 900,238 930,228 960,234 990,225 990,300 160,300">
          <animate attributeName="opacity" values="0;0.06;0.06;0" keyTimes="0;0.2;0.8;1" dur="4s" repeatCount="indefinite" />
        </polygon>
      </g>

      <g opacity="0.15">
        <polyline
          fill="none" stroke="#4a90b0" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round"
          points="160,295 200,292 230,298 260,290 290,294 320,284 350,290 380,280 410,286 440,276 470,282 500,272 530,278 560,268 590,274 620,264 650,270 680,260 710,266 740,256 770,262 800,252 830,258 860,248 890,254 920,244 950,250 990,240"
          strokeDasharray="1200"
          strokeDashoffset="1200">
          <animate attributeName="stroke-dashoffset" values="1200;0" dur="5s" fill="freeze" repeatCount="indefinite" />
        </polyline>
      </g>

      <g opacity="0.04" stroke="#4080a0" strokeWidth="0.5">
        <line x1="160" y1="270" x2="990" y2="270" />
        <line x1="160" y1="280" x2="990" y2="280" />
        <line x1="160" y1="290" x2="990" y2="290" />
        <line x1="160" y1="300" x2="990" y2="300" />
        <line x1="300" y1="260" x2="300" y2="305" />
        <line x1="440" y1="260" x2="440" y2="305" />
        <line x1="580" y1="260" x2="580" y2="305" />
        <line x1="720" y1="260" x2="720" y2="305" />
        <line x1="860" y1="260" x2="860" y2="305" />
      </g>

      <g opacity="0.12">
        <g fill="#30c888" stroke="#30c888" strokeWidth="0.8">
          <line x1="210" y1="284" x2="210" y2="296" /><rect x="207" y="286" width="6" height="6" rx="0.5" />
          <line x1="280" y1="278" x2="280" y2="292" /><rect x="277" y="280" width="6" height="7" rx="0.5" />
          <line x1="370" y1="272" x2="370" y2="286" /><rect x="367" y="274" width="6" height="6" rx="0.5" />
          <line x1="480" y1="264" x2="480" y2="280" /><rect x="477" y="266" width="6" height="8" rx="0.5" />
          <line x1="560" y1="260" x2="560" y2="274" /><rect x="557" y="262" width="6" height="6" rx="0.5" />
          <line x1="680" y1="250" x2="680" y2="266" /><rect x="677" y="252" width="6" height="8" rx="0.5" />
          <line x1="790" y1="242" x2="790" y2="258" /><rect x="787" y="244" width="6" height="7" rx="0.5" />
          <line x1="900" y1="234" x2="900" y2="250" /><rect x="897" y="236" width="6" height="8" rx="0.5" />
        </g>
        <g fill="#c85050" stroke="#c85050" strokeWidth="0.8">
          <line x1="245" y1="286" x2="245" y2="296" /><rect x="242" y="288" width="6" height="4" rx="0.5" />
          <line x1="420" y1="270" x2="420" y2="282" /><rect x="417" y="272" width="6" height="5" rx="0.5" />
          <line x1="620" y1="256" x2="620" y2="268" /><rect x="617" y="258" width="6" height="5" rx="0.5" />
          <line x1="840" y1="240" x2="840" y2="252" /><rect x="837" y="242" width="6" height="4" rx="0.5" />
        </g>
        <animate attributeName="opacity" values="0;0.12;0.12;0" keyTimes="0;0.15;0.85;1" dur="4s" repeatCount="indefinite" />
      </g>

      <text x="225" y="240"
        fontFamily="'Neue Haas Grotesk Display','Helvetica Neue','Suisse Intl','Aktiv Grotesk',Helvetica,Arial,sans-serif"
        fontWeight="500" fontSize="112" letterSpacing="5"
        fill={`url(#ltFill-${uid})`} textRendering="geometricPrecision">ST</text>

      <text x="510" y="240"
        fontFamily="'Neue Haas Grotesk Display','Helvetica Neue','Suisse Intl','Aktiv Grotesk',Helvetica,Arial,sans-serif"
        fontWeight="500" fontSize="112" letterSpacing="5"
        fill={`url(#ltFill-${uid})`} textRendering="geometricPrecision">CKEYE</text>

      <g clipPath={`url(#textClip-${uid})`}>
        <rect x="0" y="120" width="1200" height="160" fill={`url(#shine-${uid})`} />
      </g>

      <g transform="translate(444, 199)">
        <circle cx="0" cy="0" r="32" fill={`url(#irisGlow-${uid})`} opacity="0">
          <animate attributeName="opacity" values="0;0.7;0" dur="4s" repeatCount="indefinite" calcMode="spline" keySplines="0.4 0 0.2 1;0.4 0 0.2 1" />
          <animate attributeName="r" values="30;42;30" dur="4s" repeatCount="indefinite" calcMode="spline" keySplines="0.4 0 0.2 1;0.4 0 0.2 1" />
        </circle>

        <path d="M-44,0 C-36,-22 -20,-40 0,-40 C20,-40 36,-22 44,0 C36,22 20,40 0,40 C-20,40 -36,22 -44,0Z"
          fill="none" stroke={`url(#eyeFill-${uid})`} strokeWidth="9.5" strokeLinejoin="round" />

        <circle cx="0" cy="0" r="19" fill="none" stroke={`url(#eyeFill-${uid})`} strokeWidth="7.5">
          <animate attributeName="r" values="19;20.5;19" dur="4s" repeatCount="indefinite" calcMode="spline" keySplines="0.4 0 0.2 1;0.4 0 0.2 1" />
          <animate attributeName="stroke-width" values="7.5;6;7.5" dur="4s" repeatCount="indefinite" calcMode="spline" keySplines="0.4 0 0.2 1;0.4 0 0.2 1" />
        </circle>

        <circle cx="0" cy="0" r="10.5" fill={`url(#eyeFill-${uid})`}>
          <animate attributeName="r" values="10.5;8;10.5" dur="4s" repeatCount="indefinite" calcMode="spline" keySplines="0.4 0 0.2 1;0.4 0 0.2 1" />
        </circle>

        <polyline points="-6,3.5 -2.2,0.8 1.5,2.8 6,-4.5"
          fill="none" stroke="#060e18" strokeWidth="1.8"
          strokeLinecap="round" strokeLinejoin="round"
          strokeDasharray="22" strokeDashoffset="22">
          <animate attributeName="stroke-dashoffset"
            values="22;0;0;22" keyTimes="0;0.3;0.7;1"
            dur="4s" repeatCount="indefinite"
            calcMode="spline" keySplines="0.4 0 0.2 1;0.1 0 0.1 1;0.4 0 0.2 1" />
        </polyline>

        <line x1="-38" y1="0" x2="38" y2="0" strokeWidth="1.2" opacity="0" strokeLinecap="round">
          <animate attributeName="stroke" values="#80d0e0;#60d8b0;#d0c080;#80d0e0" dur="8s" repeatCount="indefinite" />
          <animate attributeName="y1" values="-36;36;-36" dur="6s" repeatCount="indefinite" calcMode="spline" keySplines="0.3 0 0.7 1;0.3 0 0.7 1" />
          <animate attributeName="y2" values="-36;36;-36" dur="6s" repeatCount="indefinite" calcMode="spline" keySplines="0.3 0 0.7 1;0.3 0 0.7 1" />
          <animate attributeName="opacity" values="0;0.5;0.5;0.5;0" keyTimes="0;0.05;0.5;0.95;1" dur="6s" repeatCount="indefinite" />
        </line>

        <circle cx="0" cy="0" r="14" fill="none" strokeWidth="1.2" opacity="0">
          <animate attributeName="stroke" values="#b0d0e0;#60d8b8;#d8c890;#b0d0e0" dur="8s" repeatCount="indefinite" />
          <animate attributeName="opacity" values="0;0.55;0" dur="4s" repeatCount="indefinite" calcMode="spline" keySplines="0.4 0 0.2 1;0.4 0 0.2 1" />
          <animate attributeName="r" values="12;17;12" dur="4s" repeatCount="indefinite" calcMode="spline" keySplines="0.4 0 0.2 1;0.4 0 0.2 1" />
        </circle>
      </g>

      <g>
        <circle cx="990" cy="225" r="3" fill="#30c888" opacity="0">
          <animate attributeName="opacity" values="0;0;1;1;0.5;1;1;0" keyTimes="0;0.18;0.2;0.4;0.5;0.6;0.85;1" dur="4s" repeatCount="indefinite" />
        </circle>
        <circle cx="990" cy="225" r="3" fill={`url(#greenPulse-${uid})`} opacity="0">
          <animate attributeName="r" values="3;10;3" dur="2s" repeatCount="indefinite" calcMode="spline" keySplines="0.4 0 0.2 1;0.4 0 0.2 1" />
          <animate attributeName="opacity" values="0;0;0.5;0;0" keyTimes="0;0.18;0.3;0.5;1" dur="4s" repeatCount="indefinite" />
        </circle>
      </g>

      <g fontFamily="'SF Mono','Roboto Mono','Courier New',monospace" fontSize="9" fill="#30c888" opacity="0" letterSpacing="0.5">
        <animate attributeName="opacity" values="0;0;0.3;0.3;0" keyTimes="0;0.2;0.25;0.85;1" dur="4s" repeatCount="indefinite" />
        <text x="170" y="318">+2.84%</text>
        <text x="310" y="318" fill="#4a90b0">VOL 1.2M</text>
        <text x="460" y="318">+0.47%</text>
        <text x="600" y="318" fill="#4a90b0">MKT OPEN</text>
        <text x="750" y="318">+1.12%</text>
        <text x="890" y="318" fill="#4a90b0">▲ 4,821.06</text>
      </g>

    </svg>
  );
}
