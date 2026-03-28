import React from 'react';
import StockEyeLogo from './StockEyeLogo';
import { ArrowLeft } from 'lucide-react';

const LAST_UPDATED = '28 March 2026';

export default function TermsPage() {
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
        <h1 style={{ fontSize: 28, fontWeight: 800, color: '#0f172a', marginBottom: 6 }}>Terms of Service</h1>
        <p style={{ color: '#94a3b8', fontSize: 13, marginBottom: 36 }}>Last updated: {LAST_UPDATED}</p>

        {[
          {
            title: '1. Paper Trading Only',
            body: `StockEye is a paper trading simulation platform. All trades executed on the platform are simulated and do not involve real money, real securities, or real brokerage accounts. No actual buy or sell orders are placed on any exchange including NSE or BSE.`,
          },
          {
            title: '2. Not Investment Advice',
            body: `Nothing on StockEye — including AI-generated signals, recommendations, composite scores, market analysis, or any other content — constitutes financial, investment, legal, or tax advice. You should consult a registered investment advisor (RIA) or SEBI-registered research analyst before making any real investment decisions.`,
          },
          {
            title: '3. No Guarantee of Returns',
            body: `Past paper trading performance shown on StockEye does not guarantee or predict future returns in real markets. Simulated results may differ materially from actual trading results due to slippage, liquidity, transaction costs, and other market factors.`,
          },
          {
            title: '4. Use of AI',
            body: `StockEye uses large language models (including Anthropic Claude) to generate analysis, trade rationale, and portfolio reviews. AI-generated content may contain errors, hallucinations, or outdated information. Always verify signals independently before acting on them.`,
          },
          {
            title: '5. Data Accuracy',
            body: `StockEye relies on third-party data providers for market prices, FII/DII flows, option chain data, and news. We do not guarantee the accuracy, completeness, or timeliness of this data.`,
          },
          {
            title: '6. Account & Security',
            body: `You are responsible for maintaining the confidentiality of your account credentials. Notify us immediately if you suspect unauthorised access. We use Supabase for authentication and never store plain-text passwords.`,
          },
          {
            title: '7. Acceptable Use',
            body: `You agree not to use StockEye to circumvent securities laws, engage in market manipulation, or collect data for redistribution. Automated scraping of the platform is prohibited.`,
          },
          {
            title: '8. Limitation of Liability',
            body: `To the maximum extent permitted by law, StockEye and its operators shall not be liable for any direct, indirect, incidental, or consequential damages arising from your use of the platform.`,
          },
          {
            title: '9. Changes to Terms',
            body: `We may update these terms from time to time. Continued use of StockEye after changes constitutes acceptance of the revised terms.`,
          },
          {
            title: '10. Contact',
            body: `For questions about these terms, please contact us through the StockEye platform.`,
          },
        ].map(({ title, body }) => (
          <section key={title} style={{ marginBottom: 28 }}>
            <h2 style={{ fontSize: 16, fontWeight: 700, color: '#0f172a', marginBottom: 8 }}>{title}</h2>
            <p style={{ fontSize: 14, color: '#475569', lineHeight: 1.75, margin: 0 }}>{body}</p>
          </section>
        ))}

        <div style={{
          marginTop: 40, padding: '16px 20px', background: '#fef3c7',
          border: '1px solid #fde68a', borderRadius: 10,
        }}>
          <p style={{ margin: 0, fontSize: 13, color: '#92400e', fontWeight: 600 }}>
            StockEye is a paper trading research tool for educational purposes only.
            It is not a SEBI-registered investment advisor, broker, or research analyst.
            Do not use signals from this platform to make real investment decisions.
          </p>
        </div>
      </div>
    </div>
  );
}
