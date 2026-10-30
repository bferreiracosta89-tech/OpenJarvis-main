import { useEffect, useState } from 'react';
import { Outlet, useNavigate } from 'react-router';
import { Bell, Search, Settings } from 'lucide-react';
import { ApprovalBell } from './ApprovalBell';
import { Sidebar } from './Sidebar/Sidebar';
import { SystemPulse } from './SystemPulse';
import { useAppStore } from '../lib/store';
import { checkHealth } from '../lib/api';

export function Layout() {
  const sidebarOpen = useAppStore((s) => s.sidebarOpen);
  const selectedModel = useAppStore((s) => s.selectedModel);
  const setCommandPaletteOpen = useAppStore((s) => s.setCommandPaletteOpen);
  const [apiReachable, setApiReachable] = useState<boolean | null>(null);

  useEffect(() => {
    const check = () => checkHealth().then(setApiReachable);
    check();
    const interval = setInterval(check, 30000);
    const onFocus = () => check();
    window.addEventListener('focus', onFocus);
    return () => {
      clearInterval(interval);
      window.removeEventListener('focus', onFocus);
    };
  }, []);

  const navigate = useNavigate();

  return (
    <div className="flex flex-col h-full w-full overflow-hidden relative" style={{ paddingTop: '3px' }}>
      <div className="hud-backdrop" aria-hidden="true" />
      <SystemPulse apiReachable={apiReachable} />
      <ApprovalBell />

      {/* Health check banner */}
      {apiReachable === false && (
        <div
          className="flex items-center gap-3 px-4 py-2 text-sm shrink-0"
          style={{
            background: 'color-mix(in srgb, var(--color-error) 8%, transparent)',
            borderBottom: '1px solid color-mix(in srgb, var(--color-error) 15%, transparent)',
            color: 'var(--color-text)',
          }}
        >
          <span
            className="w-1.5 h-1.5 rounded-full shrink-0"
            style={{ background: 'var(--color-error)' }}
          />
          <span>Cannot reach OpenJarvis backend</span>
          <button
            onClick={() => navigate('/settings')}
            className="text-sm underline cursor-pointer ml-auto shrink-0"
            style={{ color: 'var(--color-accent)' }}
          >
            Change URL
          </button>
        </div>
      )}

      <header className="h-14 shrink-0 flex items-center gap-3 px-4 md:px-6 relative z-20" style={{ background: 'var(--color-surface)', borderBottom: '1px solid var(--color-border)' }}>
        <button onClick={() => navigate('/dashboard')} className="flex items-center gap-2 shrink-0 cursor-pointer" title="Abrir início">
          <img src="/pwa-192x192.png" alt="JARVIS" className="w-8 h-8 rounded-xl" />
          <span className="hidden sm:block text-sm font-semibold tracking-wider" style={{ color: 'var(--color-text)', fontFamily: 'var(--font-display)' }}>JARVIS</span>
        </button>
        <button onClick={() => setCommandPaletteOpen(true)} className="flex items-center gap-2 max-w-xl flex-1 mx-auto rounded-xl px-3 py-2 text-left cursor-pointer" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', color: 'var(--color-text-tertiary)' }}>
          <Search size={15} /><span className="text-xs truncate">Pergunte ao Jarvis qualquer coisa...</span><kbd className="hidden md:block ml-auto text-[10px] font-mono">Ctrl K</kbd>
        </button>
        <div className="flex items-center gap-1 shrink-0">
          <button onClick={() => navigate('/notifications')} className="p-2 rounded-lg cursor-pointer" style={{ color: 'var(--color-text-secondary)' }} title="Notificações"><Bell size={17} /></button>
          <button onClick={() => navigate('/settings')} className="p-2 rounded-lg cursor-pointer" style={{ color: 'var(--color-text-secondary)' }} title="Configurações"><Settings size={17} /></button>
          <button onClick={() => navigate('/profile')} className="hidden md:flex items-center gap-2 ml-1 rounded-lg px-2 py-1.5 cursor-pointer" style={{ background: 'var(--color-bg-secondary)' }}><span className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-semibold" style={{ background: 'var(--color-accent)', color: 'var(--color-on-accent)' }}>J</span><span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>{selectedModel ? 'Operador' : 'Perfil'}</span></button>
        </div>
      </header>

      <div className="flex flex-1 min-h-0 relative z-10">
        <Sidebar />
        {sidebarOpen && (
          <div
            className="fixed inset-0 z-20 bg-black/40 md:hidden"
            onClick={() => useAppStore.getState().setSidebarOpen(false)}
          />
        )}
        <main className="flex-1 flex flex-col min-w-0 h-full relative overflow-hidden" style={{ background: 'transparent' }}>
          <div className="flex-1 flex flex-col min-w-0 min-h-0 relative z-[2]">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
