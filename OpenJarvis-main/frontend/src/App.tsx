import { useEffect, useState, useCallback, useRef } from 'react';
import { Navigate, Routes, Route, useLocation } from 'react-router';
import { Layout } from './components/Layout';
import { ChatPage } from './pages/ChatPage';
import { DashboardPage } from './pages/DashboardPage';
import { SettingsPage } from './pages/SettingsPage';
import { GetStartedPage } from './pages/GetStartedPage';
import { AgentsPage } from './pages/AgentsPage';
import { DataSourcesPage } from './pages/DataSourcesPage';
import { LogsPage } from './pages/LogsPage';
import { WorkspacePage } from './pages/WorkspacePage';
import { LoginPage } from './pages/LoginPage';
import { CommandPalette } from './components/CommandPalette';
import { SetupScreen } from './components/SetupScreen';
import { Toaster } from './components/ui/sonner';
import { useAppStore } from './lib/store';
import { fetchAuthBootstrap, fetchCurrentUser, fetchModels, fetchServerInfo, fetchSavings, getAuthToken, setAuthToken, submitSavings, isTauri } from './lib/api';
import { OptInModal } from './components/OptInModal';
import { UpdateChecker } from './components/Desktop/UpdateChecker';
import { track, hashId } from './lib/analytics';
import { offerAnalyticsChoice } from './lib/analytics-invitation';

function AuthenticatedLayout() {
  const location = useLocation();
  const [status, setStatus] = useState<'loading' | 'required' | 'ready'>('loading');

  useEffect(() => {
    let active = true;
    const check = async () => {
      try {
        const bootstrap = await fetchAuthBootstrap();
        if (!bootstrap.configured || !getAuthToken()) {
          if (active) setStatus('required');
          return;
        }
        await fetchCurrentUser();
        if (active) setStatus('ready');
      } catch {
        if (getAuthToken()) setAuthToken('');
        // An unavailable backend should not blank the local desktop shell;
        // the normal health banner will report the connection problem.
        if (active) setStatus('ready');
      }
    };
    void check();
    return () => { active = false; };
  }, []);

  if (status === 'loading') {
    return <div className="min-h-screen flex items-center justify-center text-sm" style={{ background: 'var(--color-bg)', color: 'var(--color-text-secondary)' }}>Verificando acesso...</div>;
  }
  if (status === 'required') return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <Layout />;
}

export default function App() {
  const [setupDone, setSetupDone] = useState(!isTauri());
  const handleSetupReady = useCallback(() => {
    setSetupDone(true);
    // Only fire once per install — guard against setup screen re-appearing
    // on reinstalls or dev reloads.
    if (!localStorage.getItem('oj-setup-completed')) {
      localStorage.setItem('oj-setup-completed', '1');
      track('setup_completed', { preset: 'default' });
    }
  }, []);
  const prevModelRef = useRef<string>('');
  const setModels = useAppStore((s) => s.setModels);
  const setModelsLoading = useAppStore((s) => s.setModelsLoading);
  const selectedModel = useAppStore((s) => s.selectedModel);
  const setServerInfo = useAppStore((s) => s.setServerInfo);
  const setSavings = useAppStore((s) => s.setSavings);
  const settings = useAppStore((s) => s.settings);
  const commandPaletteOpen = useAppStore((s) => s.commandPaletteOpen);
  const setCommandPaletteOpen = useAppStore((s) => s.setCommandPaletteOpen);
  const optInEnabled = useAppStore((s) => s.optInEnabled);
  const optInDisplayName = useAppStore((s) => s.optInDisplayName);
  const optInEmail = useAppStore((s) => s.optInEmail);
  const optInAnonId = useAppStore((s) => s.optInAnonId);
  const optInModalSeen = useAppStore((s) => s.optInModalSeen);
  const optInModalOpen = useAppStore((s) => s.optInModalOpen);
  const setOptInModalOpen = useAppStore((s) => s.setOptInModalOpen);
  const markOptInModalSeen = useAppStore((s) => s.markOptInModalSeen);
  const savings = useAppStore((s) => s.savings);

  // Apply theme class to <html>
  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove('dark', 'light');
    if (settings.theme === 'dark') root.classList.add('dark');
    else if (settings.theme === 'light') root.classList.add('light');
    root.dataset.fontSize = settings.fontSize;
  }, [settings.theme, settings.fontSize]);

  // Sync overlay conversations into the main app
  const importOverlay = useAppStore((s) => s.importOverlayConversation);
  useEffect(() => {
    if (!isTauri()) return;
    importOverlay();
    const interval = setInterval(importOverlay, 5000);
    return () => clearInterval(interval);
  }, [importOverlay]);

  // Fetch models on mount
  useEffect(() => {
    fetchModels()
      .then((m) => {
        setModels(m);
      })
      .catch(() => setModels([]))
      .finally(() => setModelsLoading(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch server info
  useEffect(() => {
    fetchServerInfo().then(setServerInfo).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Poll savings and optionally share to Supabase
  useEffect(() => {
    const refresh = () =>
      fetchSavings()
        .then((data) => {
          setSavings(data);
          if (optInEnabled && optInDisplayName && data) {
            const claudeEntry = data.per_provider.find(
              (p) => p.provider === 'claude-fable-5',
            );
            const dollarSavings = claudeEntry ? claudeEntry.total_cost : 0;
            const energySaved = data.per_provider.reduce(
              (sum, p) => sum + (p.energy_wh || 0),
              0,
            );
            const flopsSaved = data.per_provider.reduce(
              (sum, p) => sum + (p.flops || 0),
              0,
            );
            submitSavings({
              anon_id: optInAnonId,
              display_name: optInDisplayName,
              email: optInEmail,
              total_calls: data.total_calls,
              total_tokens: data.total_tokens,
              dollar_savings: dollarSavings,
              energy_wh_saved: energySaved,
              flops_saved: flopsSaved,
              token_counting_version: data.token_counting_version ?? 1,
            });
          }
        })
        .catch(() => {});
    refresh();
    const interval = setInterval(refresh, 30000);
    return () => clearInterval(interval);
  }, [optInEnabled, optInDisplayName, optInEmail, optInAnonId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Wait for desktop setup before fetching identity or marking the dialog seen.
  useEffect(() => offerAnalyticsChoice({
    ready: setupDone,
    sharingModalSeen: optInModalSeen,
    open: () => setOptInModalOpen(true),
    markSharingModalSeen: markOptInModalSeen,
  }), [setupDone, optInModalSeen, setOptInModalOpen, markOptInModalSeen]);

  // Fire model_changed when the user switches models. First mount is
  // not a "change" — only emit when both prev and current are real and
  // differ.
  useEffect(() => {
    const prev = prevModelRef.current;
    const curr = selectedModel || '';
    prevModelRef.current = curr;
    if (!prev || !curr || prev === curr) return;
    void (async () => {
      const [fromHash, toHash] = await Promise.all([
        hashId(prev),
        hashId(curr),
      ]);
      track('model_changed', {
        from_model_hash: fromHash,
        to_model_hash: toHash,
      });
    })();
  }, [selectedModel]);

  // app_opened — one-shot per app launch, fires after analytics has had
  // a chance to initialize. platform + version are super-properties
  // registered in analytics.ts initAnalytics, so no per-call props needed.
  useEffect(() => {
    const t = setTimeout(() => {
      track('app_opened', {});
    }, 500);
    return () => clearTimeout(t);
  }, []);

  // Global keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setCommandPaletteOpen(!commandPaletteOpen);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [commandPaletteOpen, setCommandPaletteOpen]);


  if (!setupDone) {
    return <SetupScreen onReady={handleSetupReady} />;
  }

  return (
    <>
      <UpdateChecker />
      <Routes>
        <Route path="login" element={<LoginPage />} />
        <Route element={<AuthenticatedLayout />}>
          <Route index element={<ChatPage />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="get-started" element={<GetStartedPage />} />
          <Route path="data-sources" element={<DataSourcesPage />} />
          <Route path="knowledge" element={<DataSourcesPage />} />
          <Route path="agents" element={<AgentsPage />} />
          <Route path="agents/new" element={<WorkspacePage kind="agent-config" />} />
          <Route path="agents/:agentId/configure" element={<WorkspacePage kind="agent-config" />} />
          <Route path="agents/:agentId" element={<WorkspacePage kind="agent-detail" />} />
          <Route path="projects" element={<WorkspacePage kind="projects" />} />
          <Route path="tasks" element={<WorkspacePage kind="tasks" />} />
          <Route path="conclave" element={<WorkspacePage kind="conclave" />} />
          <Route path="memory" element={<WorkspacePage kind="memory" />} />
          <Route path="integrations" element={<WorkspacePage kind="integrations" />} />
          <Route path="tools" element={<WorkspacePage kind="tools" />} />
          <Route path="api" element={<WorkspacePage kind="api" />} />
          <Route path="notifications" element={<WorkspacePage kind="notifications" />} />
          <Route path="profile" element={<WorkspacePage kind="profile" />} />
          <Route path="logs" element={<LogsPage />} />
        </Route>
      </Routes>
      <Toaster position="bottom-right" />
      {commandPaletteOpen && <CommandPalette />}
      {optInModalOpen && (
        <OptInModal onClose={() => setOptInModalOpen(false)} />
      )}
    </>
  );
}
