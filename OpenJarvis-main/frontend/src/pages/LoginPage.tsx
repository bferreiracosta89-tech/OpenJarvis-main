import { FormEvent, useEffect, useState } from 'react';
import { ArrowRight, Eye, EyeOff, Fingerprint, Loader2, Sparkles } from 'lucide-react';
import { useNavigate } from 'react-router';
import { fetchAuthBootstrap, loginWithPasskey, loginWithPassword, registerAccount, registerPasskey } from '../lib/api';

/** Login surface for the local account and passkey authentication flow. */
export function LoginPage() {
  const navigate = useNavigate();
  const [configured, setConfigured] = useState(true);
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [showPassword, setShowPassword] = useState(false);
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchAuthBootstrap().then((result) => {
      setConfigured(result.configured);
      if (!result.configured) setMode('register');
    }).catch((error) => setMessage(error instanceof Error ? error.message : 'Servidor indisponível.'));
  }, []);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setMessage('');
    try {
      if (mode === 'register') await registerAccount(email, password, displayName);
      else await loginWithPassword(email, password);
      navigate('/');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Não foi possível autenticar.');
    } finally {
      setBusy(false);
    }
  };

  const handlePasskey = async () => {
    setBusy(true);
    setMessage('Aguardando Windows Hello ou a biometria do dispositivo...');
    try {
      if (mode === 'register') {
        if (!email || !password) throw new Error('Crie a conta com e-mail e senha antes de cadastrar a biometria.');
        await registerAccount(email, password, displayName);
        await registerPasskey();
      } else {
        await loginWithPasskey();
      }
      navigate('/');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Não foi possível usar a biometria.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="min-h-screen p-4 sm:p-8" style={{ background: 'var(--color-bg)', color: 'var(--color-text-primary)' }}>
      <div className="mx-auto grid min-h-[calc(100vh-2rem)] max-w-6xl overflow-hidden rounded-3xl" style={{ border: '1px solid var(--color-border)', background: 'var(--color-surface)', boxShadow: 'var(--shadow-lg)' }}>
        <section className="relative hidden overflow-hidden p-10 lg:flex lg:flex-col lg:justify-between" style={{ background: 'linear-gradient(145deg, #061327 0%, #0b1f3c 55%, #083b64 100%)' }}>
          <div className="absolute -right-24 -top-24 h-72 w-72 rounded-full blur-3xl" style={{ background: 'rgba(34, 211, 238, .22)' }} />
          <div className="absolute -bottom-28 -left-24 h-80 w-80 rounded-full blur-3xl" style={{ background: 'rgba(22, 104, 255, .24)' }} />
          <div className="relative flex items-center gap-3">
            <img src="/pwa-192x192.png" alt="JARVIS" className="h-12 w-12 rounded-2xl" />
            <div>
              <p className="text-2xl font-semibold tracking-[.22em] text-white">JARVIS</p>
              <p className="text-xs uppercase tracking-[.18em]" style={{ color: '#9bc5e9' }}>Seu assistente inteligente</p>
            </div>
          </div>
          <div className="relative flex flex-col items-center text-center">
            <div className="relative mb-8 flex h-64 w-64 items-center justify-center rounded-full" style={{ border: '1px solid rgba(79, 209, 255, .55)', boxShadow: '0 0 90px rgba(22, 104, 255, .3), inset 0 0 45px rgba(79, 209, 255, .15)' }}>
              <div className="absolute h-48 w-48 rounded-full" style={{ border: '2px solid #4fd1ff', boxShadow: '0 0 28px #168cff' }} />
              <Sparkles size={62} style={{ color: '#d7f5ff' }} />
            </div>
            <h1 className="max-w-md text-3xl font-semibold text-white">Seu espaço para pensar, criar e executar.</h1>
            <p className="mt-4 max-w-md text-sm leading-6" style={{ color: '#aac6e0' }}>Organize conversas, projetos, agentes e ferramentas em uma única experiência.</p>
          </div>
          <p className="relative text-xs" style={{ color: '#7fa4c7' }}>OpenJarvis · Intelligence on Personal Devices</p>
        </section>

        <section className="flex items-center justify-center p-6 sm:p-10">
          <div className="w-full max-w-md">
            <div className="mb-8 lg:hidden">
              <div className="flex items-center gap-3">
                <img src="/pwa-192x192.png" alt="JARVIS" className="h-11 w-11 rounded-2xl" />
                <div>
                  <p className="text-xl font-semibold tracking-[.18em]">JARVIS</p>
                  <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>Seu assistente inteligente</p>
                </div>
              </div>
            </div>
            <p className="mb-2 text-sm font-medium" style={{ color: 'var(--color-accent)' }}>{mode === 'register' ? 'Primeiro acesso' : 'Bem-vindo de volta'}</p>
            <h2 className="text-3xl font-semibold tracking-tight">{mode === 'register' ? 'Crie seu espaço' : 'Acesse seu espaço'}</h2>
            <p className="mt-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}>Use Windows Hello, a biometria do telefone ou e-mail e senha.</p>

            <button type="button" disabled={busy} onClick={() => void handlePasskey()} className="mt-7 flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 font-medium disabled:opacity-60" style={{ background: 'var(--color-accent)', color: 'var(--color-on-accent)' }}><Fingerprint size={18} />{busy ? <Loader2 size={17} className="animate-spin" /> : mode === 'register' ? 'Cadastrar biometria' : 'Entrar com biometria'}</button>
            <div className="my-6 flex items-center gap-3 text-xs" style={{ color: 'var(--color-text-tertiary)' }}><span className="h-px flex-1" style={{ background: 'var(--color-border)' }} />ou e-mail e senha<span className="h-px flex-1" style={{ background: 'var(--color-border)' }} /></div>

            <form className="space-y-5" onSubmit={(event) => void handleSubmit(event)}>
              {mode === 'register' && <label className="block text-sm font-medium">Nome de exibição<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} type="text" autoComplete="name" placeholder="Como o JARVIS deve chamar você?" className="mt-2 w-full rounded-xl px-4 py-3 outline-none" style={{ border: '1px solid var(--color-border)', background: 'var(--color-surface-raised)', color: 'var(--color-text-primary)' }} /></label>}
              <label className="block text-sm font-medium">
                E-mail
                <input value={email} onChange={(event) => setEmail(event.target.value)} required type="email" autoComplete="email" placeholder="seu@email.com" className="mt-2 w-full rounded-xl px-4 py-3 outline-none" style={{ border: '1px solid var(--color-border)', background: 'var(--color-surface-raised)', color: 'var(--color-text-primary)' }} />
              </label>
              <label className="block text-sm font-medium">
                Senha
                <div className="relative mt-2">
                  <input value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} type={showPassword ? 'text' : 'password'} autoComplete={mode === 'register' ? 'new-password' : 'current-password'} placeholder="Mínimo de 8 caracteres" className="w-full rounded-xl px-4 py-3 pr-12 outline-none" style={{ border: '1px solid var(--color-border)', background: 'var(--color-surface-raised)', color: 'var(--color-text-primary)' }} />
                  <button type="button" aria-label={showPassword ? 'Ocultar senha' : 'Mostrar senha'} onClick={() => setShowPassword((current) => !current)} className="absolute right-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--color-text-tertiary)' }}>
                    {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                  </button>
                </div>
              </label>
              <button type="submit" disabled={busy} className="flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 font-medium disabled:opacity-60" style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)' }}>
                {busy ? <Loader2 size={17} className="animate-spin" /> : <>{mode === 'register' ? 'Criar conta' : 'Entrar'} <ArrowRight size={17} /></>}
              </button>
            </form>
            {configured && <button type="button" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setMessage(''); }} className="mt-5 w-full text-xs" style={{ color: 'var(--color-accent)' }}>{mode === 'login' ? 'Criar uma conta local' : 'Já tenho uma conta'}</button>}
            {message && <p role="status" className="mt-4 rounded-lg px-3 py-2 text-xs" style={{ background: 'color-mix(in srgb, var(--color-warning) 12%, transparent)', color: 'var(--color-warning)' }}>{message}</p>}
            <p className="mt-8 text-center text-xs" style={{ color: 'var(--color-text-tertiary)' }}>A biometria nunca é enviada ao JARVIS; apenas a prova criptográfica é validada.</p>
          </div>
        </section>
      </div>
    </main>
  );
}
