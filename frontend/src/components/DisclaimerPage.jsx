import React from 'react';
import StockEyeLogo from './StockEyeLogo';
import { ArrowLeft, AlertTriangle } from 'lucide-react';

export default function DisclaimerPage() {
  return (
    <div style={{ minHeight: '100vh', background: '#f8fafc', fontFamily: 'system-ui, sans-serif' }}>
      <header style={{
        background: '#ffffff', borderBottom: '1px solid #e2e8f0',
        padding: '0 24px', height: 56, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <StockEyeLogo size={44} dark={false} />
        </div>
        <a href="/" style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 13, color: '#64748b', textDecoration: 'none' }}>
          <ArrowLeft size={13} /> Back
        </a>
      </header>

      <div style={{ maxWidth: 780, margin: '0 auto', padding: '40px 20px' }}>
        {/* Alert banner */}
        <div style={{
          display: 'flex', gap: 12, alignItems: 'flex-start',
          background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 12,
          padding: '16px 20px', marginBottom: 36,
        }}>
          <AlertTriangle size={20} style={{ color: '#dc2626', flexShrink: 0, marginTop: 2 }} />
          <div>
            <div style={{ fontWeight: 700, color: '#991b1b', fontSize: 15, marginBottom: 4 }}>
              Important Risk Disclosure
            </div>
            <p style={{ margin: 0, fontSize: 13, color: '#b91c1c', lineHeight: 1.6 }}>
              StockEye is a paper trading simulation. No real money is involved.
              Trading in real equity markets involves substantial risk of loss. Please read this disclaimer carefully.
            </p>
          </div>
        </div>

        <h1 style={{ fontSize: 28, fontWeight: 800, color: '#0f172a', marginBottom: 32 }}>Risk Disclaimer</h1>

        {[
          {
            heading: 'Paper Trading Simulation',
            text: `All trades on StockEye are simulated paper trades. They are executed at indicative prices and do not represent actual market transactions. Real trading involves slippage, impact cost, brokerage, STT, exchange charges, and other costs that are partially or not accounted for in this simulation.`,
            bg: '#f0f9ff', border: '#bae6fd', color: '#0369a1',
          },
          {
            heading: 'AI Signal Limitations',
            text: `StockEye uses AI models (Claude by Anthropic) to generate trading signals and recommendations. AI models can and do make mistakes, hallucinate data, or reach incorrect conclusions. Signal scores are probabilistic and do not guarantee any particular outcome. Historical signal accuracy does not predict future performance.`,
            bg: '#faf5ff', border: '#e9d5ff', color: '#6d28d9',
          },
          {
            heading: 'Market Data Disclaimer',
            text: `Price data, FII/DII flows, PCR ratios, and other market data are sourced from NSE and third-party providers. This data may be delayed, incomplete, or erroneous. StockEye does not warrant the accuracy of any market data shown on the platform.`,
            bg: '#fff7ed', border: '#fed7aa', color: '#c2410c',
          },
          {
            heading: 'No SEBI Registration',
            text: `StockEye is not a SEBI-registered Investment Advisor, Research Analyst, Stock Broker, or Portfolio Manager. Content on this platform does not constitute investment advice under the SEBI (Investment Advisers) Regulations, 2013 or the SEBI (Research Analysts) Regulations, 2014.`,
            bg: '#fef2f2', border: '#fecaca', color: '#991b1b',
          },
          {
            heading: 'Real Trading Risk',
            text: `If you choose to trade in real markets based on ideas from StockEye, you do so entirely at your own risk. Equity investments are subject to market risk. You may lose some or all of your invested capital. Past performance — both real and simulated — is not indicative of future returns.`,
            bg: '#f0fdf4', border: '#bbf7d0', color: '#166534',
          },
          {
            heading: 'Regulatory Compliance',
            text: `Users are responsible for ensuring that their trading activities comply with applicable laws and regulations in their jurisdiction, including SEBI regulations, FEMA regulations for NRIs, and any applicable tax laws.`,
            bg: '#f8fafc', border: '#e2e8f0', color: '#334155',
          },
        ].map(({ heading, text, bg, border, color }) => (
          <div key={heading} style={{
            background: bg, border: `1px solid ${border}`, borderRadius: 12,
            padding: '18px 20px', marginBottom: 16,
          }}>
            <h2 style={{ fontSize: 14, fontWeight: 700, color, marginBottom: 8, margin: '0 0 8px' }}>{heading}</h2>
            <p style={{ fontSize: 13, color: '#475569', lineHeight: 1.75, margin: 0 }}>{text}</p>
          </div>
        ))}

        <div style={{ marginTop: 40, fontSize: 12, color: '#94a3b8', textAlign: 'center', lineHeight: 1.8 }}>
          <p>By using StockEye you acknowledge that you have read, understood, and agreed to this disclaimer.</p>
          <p>
            <a href="/terms" style={{ color: '#2563eb' }}>Terms of Service</a>
            {' · '}
            StockEye © {new Date().getFullYear()}
          </p>
        </div>
      </div>
    </div>
  );
}
