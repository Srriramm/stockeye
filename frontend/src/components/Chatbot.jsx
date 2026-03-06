import React, { useState, useEffect, useRef } from 'react';
import { Send, Bot, User, Trash2, Loader2, Sparkles, TrendingUp, Shield, Target, Wallet } from 'lucide-react';
import axios from 'axios';
import { authAxios } from '../utils/api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { toast } from 'react-toastify';

const QUICK_QUESTIONS = [
  { icon: <Target size={14} />, text: "I have ₹50,000 to invest for 5 years — what suits me?" },
  { icon: <TrendingUp size={14} />, text: "Analyze Reliance Industries for long-term investment" },
  { icon: <Sparkles size={14} />, text: "What's the market outlook for IT sector in 2025?" },
  { icon: <Wallet size={14} />, text: "Review my portfolio and suggest improvements" },
  { icon: <Shield size={14} />, text: "Best dividend stocks for passive income?" },
  { icon: <Bot size={14} />, text: "Compare TCS vs Infosys — which one to buy?" },
  { icon: <Shield size={14} />, text: "Safe options for a conservative, retired investor" },
  { icon: <TrendingUp size={14} />, text: "Top mid-cap growth stocks for aggressive investors" },
];

export default function Chatbot({ apiUrl }) {
  const [messages, setMessages] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [showQuickQuestions, setShowQuickQuestions] = useState(true);
  const [preferredProvider, setPreferredProvider] = useState('auto');
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => { fetchHistory(); }, []);
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const fetchHistory = async () => {
    try {
      const res = await authAxios.get(`${apiUrl}/api/chat/history?limit=200`);
      if (res.data.messages?.length > 0) {
        setMessages(res.data.messages.map(m => ({ role: m.role, content: m.content, timestamp: m.created_at })));
        setShowQuickQuestions(false);
      }
      if (res.data.conversation_id) {
        setConversationId(res.data.conversation_id);
      }
    } catch { }
  };

  const sendMessage = async (text) => {
    const msg = text || input.trim();
    if (!msg || loading) return;
    setInput('');
    setShowQuickQuestions(false);
    setMessages(prev => [...prev, { role: 'user', content: msg, timestamp: new Date().toISOString() }]);
    setLoading(true);
    try {
      const res = await authAxios.post(
        `${apiUrl}/api/chat`,
        { message: msg, provider: preferredProvider, conversation_id: conversationId },
        { timeout: 65000 }
      );
      // Persist the conversation_id so all messages go into the same conversation
      if (res.data.conversation_id) setConversationId(res.data.conversation_id);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: res.data.response,
        provider: res.data.provider_used,
        model_used: res.data.model_used,
        query_type: res.data.query_type,
        timestamp: res.data.timestamp,
        error: res.data.error,
      }]);
    } catch {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: "Sorry, I couldn't reach the server. Please ensure the backend is running.",
        timestamp: new Date().toISOString(),
        error: true,
      }]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const clearChat = async () => {
    try {
      await authAxios.post(`${apiUrl}/api/chat/clear`);
      setMessages([]);
      setConversationId(null);
      setShowQuickQuestions(true);
      toast.success('Conversation cleared');
    } catch { toast.error('Failed to clear'); }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  const MarkdownMessage = ({ content }) => (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        h1: ({ children }) => <h1 className="text-base font-bold mt-3 mb-1.5" style={{ color: '#0f172a' }}>{children}</h1>,
        h2: ({ children }) => <h2 className="text-sm font-bold mt-3 mb-1" style={{ color: '#0f172a' }}>{children}</h2>,
        h3: ({ children }) => <h3 className="text-sm font-semibold mt-2 mb-1" style={{ color: '#1e293b' }}>{children}</h3>,
        p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
        strong: ({ children }) => <strong className="font-semibold" style={{ color: '#0f172a' }}>{children}</strong>,
        em: ({ children }) => <em className="italic" style={{ color: '#475569' }}>{children}</em>,
        ul: ({ children }) => <ul className="mb-2 space-y-0.5 pl-4 list-disc">{children}</ul>,
        ol: ({ children }) => <ol className="mb-2 space-y-0.5 pl-4 list-decimal">{children}</ol>,
        li: ({ children }) => <li className="leading-relaxed">{children}</li>,
        hr: () => <hr className="my-3" style={{ borderColor: '#e2e8f0' }} />,
        pre: ({ children }) => (
          <pre className="p-3 rounded-lg overflow-x-auto my-2 text-xs font-mono" style={{ background: '#f1f5f9', color: '#0f172a' }}>{children}</pre>
        ),
        code: ({ children, className }) => className
          ? <code className={className}>{children}</code>
          : <code className="px-1 py-0.5 rounded text-xs font-mono" style={{ background: '#f1f5f9', color: '#0f172a' }}>{children}</code>,
        table: ({ children }) => (
          <div className="overflow-x-auto my-3 rounded-lg" style={{ border: '1px solid #e2e8f0' }}>
            <table className="w-full text-xs border-collapse">{children}</table>
          </div>
        ),
        thead: ({ children }) => <thead style={{ background: '#f8fafc' }}>{children}</thead>,
        tbody: ({ children }) => <tbody>{children}</tbody>,
        tr: ({ children }) => <tr style={{ borderBottom: '1px solid #f1f5f9' }}>{children}</tr>,
        th: ({ children }) => <th className="px-3 py-2 text-left font-semibold" style={{ color: '#475569', borderBottom: '1px solid #e2e8f0' }}>{children}</th>,
        td: ({ children }) => <td className="px-3 py-2 align-top" style={{ color: '#334155' }}>{children}</td>,
        blockquote: ({ children }) => (
          <blockquote className="pl-3 my-2 text-xs italic" style={{ borderLeft: '3px solid #e2e8f0', color: '#64748b' }}>{children}</blockquote>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );

  const providerBadge = (provider) => {
    if (provider === 'anthropic') return { label: 'Claude', bg: '#fff7ed', color: '#c2410c', border: '#fed7aa' };
    if (provider === 'openai') return { label: 'GPT-4', bg: '#f0fdf4', color: '#15803d', border: '#bbf7d0' };
    return { label: 'FinAI', bg: '#f8fafc', color: '#475569', border: '#e2e8f0' };
  };

  return (
    <div className="flex flex-col h-full" style={{ background: '#f8fafc' }}>

      {/* Header */}
      <div
        className="flex items-center justify-between px-6 py-4 flex-shrink-0"
        style={{ background: '#ffffff', borderBottom: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, #2563eb, #3b82f6)', boxShadow: '0 4px 12px rgba(37,99,235,0.25)' }}
          >
            <Bot size={18} className="text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="font-bold text-sm" style={{ color: '#0f172a' }}>FinAI Finance Consultant</h2>
              <span
                className="px-2 py-0.5 text-[10px] font-semibold rounded-full"
                style={{ background: '#dbeafe', color: '#1e40af' }}
              >
                Personalized
              </span>
            </div>
            <p className="text-xs mt-0.5" style={{ color: '#64748b' }}>
              {preferredProvider === 'auto' ? 'Smart routing — GPT-4 + Claude' :
                preferredProvider === 'anthropic' ? 'Powered by Anthropic Claude' :
                  'Powered by OpenAI GPT-4'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={preferredProvider}
            onChange={(e) => setPreferredProvider(e.target.value)}
            className="px-3 py-1.5 text-xs rounded-lg transition-all"
            style={{ background: '#f8fafc', border: '1px solid #e2e8f0', color: '#475569' }}
          >
            <option value="auto">Auto</option>
            <option value="openai">GPT-4</option>
            <option value="anthropic">Claude</option>
          </select>
          <button
            onClick={clearChat}
            className="p-2 rounded-lg transition-all"
            title="Clear conversation"
            style={{ background: '#f8fafc', border: '1px solid #e2e8f0', color: '#94a3b8' }}
            onMouseEnter={e => { e.currentTarget.style.background = '#fee2e2'; e.currentTarget.style.borderColor = '#fca5a5'; e.currentTarget.style.color = '#dc2626'; }}
            onMouseLeave={e => { e.currentTarget.style.background = '#f8fafc'; e.currentTarget.style.borderColor = '#e2e8f0'; e.currentTarget.style.color = '#94a3b8'; }}
          >
            <Trash2 size={15} />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-4 py-5 space-y-4 min-h-0">

        {/* Welcome Screen */}
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center min-h-full pb-10 fade-in">
            <div
              className="w-16 h-16 rounded-2xl flex items-center justify-center mb-5"
              style={{ background: 'linear-gradient(135deg, #eff6ff, #dbeafe)', border: '1px solid #bfdbfe' }}
            >
              <Sparkles size={28} style={{ color: '#2563eb' }} />
            </div>
            <h3 className="font-bold text-lg mb-2" style={{ color: '#0f172a' }}>Your Personal Finance Consultant</h3>
            <p className="text-sm text-center max-w-sm mb-6" style={{ color: '#64748b' }}>
              Tell me your financial goals, risk appetite, and investment horizon — I'll craft a personalized strategy just for you.
            </p>

            {/* Pillars */}
            <div className="grid grid-cols-2 gap-2 w-full max-w-sm mb-7">
              <Pillar icon={<Target size={14} />} text="Goal-Based Advice" />
              <Pillar icon={<Shield size={14} />} text="Risk Profiling" />
              <Pillar icon={<TrendingUp size={14} />} text="ML Forecasting" />
              <Pillar icon={<Wallet size={14} />} text="Portfolio Review" />
            </div>

            {/* Quick Questions */}
            {showQuickQuestions && (
              <div className="w-full max-w-2xl">
                <p className="text-xs text-center mb-3 font-semibold uppercase tracking-wider" style={{ color: '#94a3b8' }}>Try asking</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {QUICK_QUESTIONS.map((q, i) => (
                    <button
                      key={i}
                      onClick={() => sendMessage(q.text)}
                      className="flex items-center gap-3 px-4 py-3 rounded-xl text-left text-xs font-medium transition-all"
                      style={{ background: '#ffffff', border: '1px solid #e2e8f0', color: '#475569', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}
                      onMouseEnter={e => { e.currentTarget.style.background = '#eff6ff'; e.currentTarget.style.borderColor = '#bfdbfe'; e.currentTarget.style.color = '#1d4ed8'; e.currentTarget.style.boxShadow = '0 2px 8px rgba(37,99,235,0.1)'; }}
                      onMouseLeave={e => { e.currentTarget.style.background = '#ffffff'; e.currentTarget.style.borderColor = '#e2e8f0'; e.currentTarget.style.color = '#475569'; e.currentTarget.style.boxShadow = '0 1px 3px rgba(0,0,0,0.04)'; }}
                    >
                      <span style={{ color: '#2563eb', flexShrink: 0 }}>{q.icon}</span>
                      {q.text}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Chat Messages */}
        {messages.map((msg, i) => {
          const badge = msg.role === 'assistant' ? providerBadge(msg.provider) : null;
          return (
            <div key={i} className={`flex gap-3 slide-up ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {msg.role === 'assistant' && (
                <div
                  className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5"
                  style={{ background: 'linear-gradient(135deg, #2563eb, #3b82f6)' }}
                >
                  <Bot size={13} className="text-white" />
                </div>
              )}
              <div
                className="max-w-[78%] rounded-2xl px-4 py-3"
                style={msg.role === 'user'
                  ? { background: '#2563eb', color: '#ffffff', borderBottomRightRadius: 4 }
                  : msg.error
                    ? { background: '#fff1f2', border: '1px solid #fecdd3', color: '#991b1b', borderBottomLeftRadius: 4 }
                    : { background: '#ffffff', border: '1px solid #e2e8f0', color: '#0f172a', borderBottomLeftRadius: 4, boxShadow: '0 1px 4px rgba(0,0,0,0.06)' }
                }
              >
                <div className="text-sm leading-relaxed prose-sm max-w-none">
                  {msg.role === 'assistant'
                    ? <MarkdownMessage content={msg.content} />
                    : msg.content}
                </div>
                {msg.role === 'assistant' && badge && (
                  <div className="flex items-center gap-2 mt-2 pt-2" style={{ borderTop: '1px solid #f1f5f9' }}>
                    <span
                      className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
                      style={{ background: badge.bg, color: badge.color, border: `1px solid ${badge.border}` }}
                    >
                      {badge.label}
                    </span>
                    {msg.query_type && (
                      <span className="text-[10px]" style={{ color: '#94a3b8' }}>• {msg.query_type}</span>
                    )}
                    {msg.timestamp && (
                      <span className="text-[10px] ml-auto font-mono" style={{ color: '#94a3b8' }}>
                        {new Date(msg.timestamp).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    )}
                  </div>
                )}
              </div>
              {msg.role === 'user' && (
                <div
                  className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5"
                  style={{ background: '#f1f5f9', border: '1px solid #e2e8f0' }}
                >
                  <User size={13} style={{ color: '#64748b' }} />
                </div>
              )}
            </div>
          );
        })}

        {/* Typing Indicator */}
        {loading && (
          <div className="flex gap-3 slide-up">
            <div
              className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
              style={{ background: 'linear-gradient(135deg, #2563eb, #3b82f6)' }}
            >
              <Bot size={13} className="text-white" />
            </div>
            <div
              className="rounded-2xl px-4 py-3"
              style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderBottomLeftRadius: 4, boxShadow: '0 1px 4px rgba(0,0,0,0.06)' }}
            >
              <div className="flex items-center gap-2">
                <Loader2 size={13} className="animate-spin" style={{ color: '#2563eb' }} />
                <span className="text-xs" style={{ color: '#64748b' }}>Analyzing with FinAI...</span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div
        className="px-4 py-4 flex-shrink-0"
        style={{ background: '#ffffff', borderTop: '1px solid #e2e8f0' }}
      >
        <div className="max-w-4xl mx-auto">
          <div className="flex items-end gap-3">
            <div
              className="flex-1 rounded-2xl transition-all"
              style={{ background: '#f8fafc', border: '1px solid #e2e8f0' }}
              onFocusCapture={e => { e.currentTarget.style.borderColor = '#2563eb'; e.currentTarget.style.boxShadow = '0 0 0 3px rgba(37,99,235,0.1)'; }}
              onBlurCapture={e => { e.currentTarget.style.borderColor = '#e2e8f0'; e.currentTarget.style.boxShadow = ''; }}
            >
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about stocks, goals, market trends, or get a portfolio review..."
                className="w-full bg-transparent px-4 py-3 text-sm resize-none focus:outline-none max-h-28"
                style={{ color: '#0f172a' }}
                rows={1}
                disabled={loading}
              />
            </div>
            <button
              onClick={() => sendMessage()}
              disabled={!input.trim() || loading}
              className="w-10 h-10 rounded-xl flex items-center justify-center transition-all"
              style={{
                background: input.trim() && !loading ? '#2563eb' : '#f1f5f9',
                boxShadow: input.trim() && !loading ? '0 4px 12px rgba(37,99,235,0.3)' : 'none',
                cursor: !input.trim() || loading ? 'not-allowed' : 'pointer',
              }}
            >
              <Send size={16} style={{ color: input.trim() && !loading ? '#ffffff' : '#94a3b8' }} />
            </button>
          </div>
          <p className="text-[10px] text-center mt-2" style={{ color: '#94a3b8' }}>
            FinAI provides educational insights only · Always consult a SEBI-registered advisor before investing
          </p>
        </div>
      </div>
    </div>
  );
}

function Pillar({ icon, text }) {
  return (
    <div
      className="flex items-center gap-2.5 px-3 py-2.5 rounded-xl"
      style={{ background: '#ffffff', border: '1px solid #e2e8f0' }}
    >
      <span style={{ color: '#2563eb' }}>{icon}</span>
      <span className="text-xs font-medium" style={{ color: '#475569' }}>{text}</span>
    </div>
  );
}
