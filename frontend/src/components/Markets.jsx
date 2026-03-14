/**
 * Markets page — Heatmap + Screener combined under one roof.
 * Toggle between views with the tab bar at the top.
 */
import React, { useState } from 'react';
import { Grid3X3, SlidersHorizontal } from 'lucide-react';
import SectorHeatmap from './SectorHeatmap';
import Screener from './Screener';

export default function Markets({ onNavigateToForecast }) {
    const [tab, setTab] = useState('heatmap');

    return (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
            {/* Tab bar */}
            <div style={{
                display: 'flex', alignItems: 'center', gap: 2,
                padding: '12px 24px 0',
                borderBottom: '1px solid #e2e8f0',
                background: '#fff',
                flexShrink: 0,
            }}>
                {[
                    { id: 'heatmap', icon: Grid3X3, label: 'Sector Heatmap' },
                    { id: 'screener', icon: SlidersHorizontal, label: 'Stock Screener' },
                ].map(({ id, icon: Icon, label }) => (
                    <button
                        key={id}
                        onClick={() => setTab(id)}
                        style={{
                            display: 'flex', alignItems: 'center', gap: 7,
                            padding: '8px 16px',
                            fontSize: 13, fontWeight: 600,
                            border: 'none', background: 'none', cursor: 'pointer',
                            color: tab === id ? '#1d4ed8' : '#64748b',
                            borderBottom: tab === id ? '2px solid #1d4ed8' : '2px solid transparent',
                            marginBottom: -1,
                            transition: 'all 0.15s',
                        }}
                    >
                        <Icon size={15} />
                        {label}
                    </button>
                ))}
            </div>

            {/* Content */}
            <div style={{ flex: 1, overflow: 'auto' }}>
                {tab === 'heatmap'  && <SectorHeatmap onNavigateToForecast={onNavigateToForecast} />}
                {tab === 'screener' && <Screener onNavigateToForecast={onNavigateToForecast} />}
            </div>
        </div>
    );
}
