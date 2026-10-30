import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import {
  Activity,
  Bot,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Code2,
  Database,
  FileText,
  FolderKanban,
  FolderOpen,
  KeyRound,
  Lightbulb,
  Link2,
  ListTodo,
  MessageSquare,
  Network,
  Plus,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  UsersRound,
  Wrench,
} from 'lucide-react';
import {
  createAppKey,
  createManagedAgent,
  createWorkspaceConclave,
  createWorkspaceProject,
  createWorkspaceTask,
  fetchWorkspaceConclaves,
  fetchWorkspaceNotifications,
  fetchWorkspaceProjects,
  fetchWorkspaceSettings,
  fetchWorkspaceTasks,
  getCloudKeyStatus,
  listAppKeys,
  revokeAppKey,
  updateManagedAgent,
} from '../lib/api';
import type { AppKeyInfo, AuthUser, WorkspaceConclave, WorkspaceProject, WorkspaceTask, WorkspaceNotification } from '../lib/api';
import { listConnectors } from '../lib/connectors-api';
import { loadMemoryPreferences, useAppStore } from '../lib/store';
import type { ConnectorInfo } from '../types/connectors';

export type WorkspaceKind =
  | 'agent-detail'
  | 'agent-config'
  | 'projects'
  | 'tasks'
  | 'conclave'
  | 'memory'
  | 'integrations'
  | 'tools'
  | 'api'
  | 'notifications'
  | 'profile';

const pageCopy: Record<WorkspaceKind, { title: string; description: string; icon: typeof Bot }> = {
  'agent-detail': { title: 'Detalhes do agente', description: 'Entenda o que o agente faz e execute uma ação controlada.', icon: Bot },
  'agent-config': { title: 'Configurar agente', description: 'Ajuste identidade, instruções, ferramentas e memória do agente.', icon: SlidersHorizontal },
  projects: { title: 'Projetos', description: 'Organize conversas, tarefas e entregas em espaços de trabalho.', icon: FolderKanban },
  tasks: { title: 'Tarefas', description: 'Organize o trabalho e acompanhe o que precisa ser feito.', icon: ListTodo },
  conclave: { title: 'Conclave', description: 'Espaço para decisões, análises e discussões entre agentes.', icon: UsersRound },
  memory: { title: 'Memória', description: 'Gerencie o histórico e o contexto que JARVIS pode recuperar.', icon: Database },
  integrations: { title: 'Integrações', description: 'Conecte serviços externos e veja o estado de cada conexão.', icon: Link2 },
  tools: { title: 'Ferramentas', description: 'Explore as capacidades disponíveis para os agentes.', icon: Wrench },
  api: { title: 'API', description: 'Integre o JARVIS com outros sistemas usando conexões controladas.', icon: Code2 },
  notifications: { title: 'Notificações', description: 'Acompanhe alertas, conclusões e eventos importantes.', icon: Activity },
  profile: { title: 'Perfil', description: 'Preferências do usuário e informações desta instalação.', icon: UsersRound },
};

function EmptyState({ icon: Icon, title, description, action, onAction }: { icon: typeof Bot; title: string; description: string; action?: string; onAction?: () => void }) {
  return <div className="rounded-2xl p-10 text-center" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}><Icon size={32} className="mx-auto mb-3" style={{ color: 'var(--color-accent)' }} /><h3 className="text-sm font-medium" style={{ color: 'var(--color-text)' }}>{title}</h3><p className="max-w-md mx-auto mt-2 text-xs" style={{ color: 'var(--color-text-tertiary)' }}>{description}</p>{action && onAction && <button onClick={onAction} className="inline-flex items-center gap-2 mt-4 rounded-lg px-3 py-2 text-xs font-medium cursor-pointer" style={{ background: 'var(--color-accent)', color: 'var(--color-on-accent)' }}><Plus size={14} />{action}</button>}</div>;
}

function Panel({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <section className={`rounded-2xl p-4 md:p-5 ${className}`} style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>{children}</section>;
}

function Header({ kind, onAction }: { kind: WorkspaceKind; onAction?: () => void }) {
  const copy = pageCopy[kind];
  const Icon = copy.icon;
  return <header className="flex flex-col md:flex-row md:items-center justify-between gap-4"><div className="flex items-start gap-3"><span className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0" style={{ background: 'var(--color-accent-subtle)', color: 'var(--color-accent)' }}><Icon size={20} /></span><div><h1 className="text-xl md:text-2xl font-semibold" style={{ color: 'var(--color-text)', fontFamily: 'var(--font-display)' }}>{copy.title}</h1><p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>{copy.description}</p></div></div>{onAction && <button onClick={onAction} className="inline-flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-medium cursor-pointer self-start" style={{ background: 'var(--color-accent)', color: 'var(--color-on-accent)' }}><Plus size={14} />Novo</button>}</header>;
}

function ProjectsView() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<WorkspaceProject[]>([]);
  const [error, setError] = useState('');
  const refresh = () => { void fetchWorkspaceProjects().then(setProjects).catch((e) => setError(e instanceof Error ? e.message : 'Não foi possível carregar os projetos.')); };
  useEffect(() => { refresh(); }, []);
  const create = async () => { const name = window.prompt('Nome do projeto'); if (!name?.trim()) return; try { await createWorkspaceProject(name); refresh(); } catch (e) { setError(e instanceof Error ? e.message : 'Não foi possível criar o projeto.'); } };
  return <><Header kind="projects" onAction={() => void create()} /><Panel><div className="flex items-center gap-3 mb-4"><Search size={16} style={{ color: 'var(--color-text-tertiary)' }} /><input className="flex-1 bg-transparent outline-none text-sm" placeholder="Buscar projetos..." style={{ color: 'var(--color-text)' }} /></div>{error && <p className="mb-3 text-xs" style={{ color: 'var(--color-error)' }}>{error}</p>}{projects.length === 0 ? <EmptyState icon={FolderKanban} title="Nenhum projeto criado" description="Crie um projeto para agrupar conversas e acompanhar o trabalho em um único lugar." action="Novo projeto" onAction={() => void create()} /> : <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">{projects.map((project) => <button key={project.id} onClick={() => navigate('/')} className="text-left rounded-xl p-4 cursor-pointer" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}><div className="flex items-center justify-between"><FolderOpen size={20} style={{ color: 'var(--color-accent)' }} /><ChevronRight size={16} style={{ color: 'var(--color-text-tertiary)' }} /></div><div className="mt-4 text-sm font-medium" style={{ color: 'var(--color-text)' }}>{project.name}</div><div className="text-xs mt-1" style={{ color: 'var(--color-text-tertiary)' }}>{project.conversation_count} conversas</div></button>)}</div>}</Panel></>;
}

function TasksView() {
  const columns = [['A fazer', Clock3], ['Em andamento', Activity], ['Concluídas', CheckCircle2]] as const;
  const [tasks, setTasks] = useState<WorkspaceTask[]>([]);
  const [error, setError] = useState('');
  const refresh = () => { void fetchWorkspaceTasks().then(setTasks).catch((e) => setError(e instanceof Error ? e.message : 'Não foi possível carregar as tarefas.')); };
  useEffect(() => { refresh(); }, []);
  const create = async () => { const title = window.prompt('Título da tarefa'); if (!title?.trim()) return; try { await createWorkspaceTask({ title }); refresh(); } catch (e) { setError(e instanceof Error ? e.message : 'Não foi possível criar a tarefa.'); } };
  const statusFor = (title: string) => title === 'A fazer' ? 'todo' : title === 'Em andamento' ? 'in_progress' : 'done';
  return <><Header kind="tasks" onAction={() => void create()} />{error && <p className="text-xs" style={{ color: 'var(--color-error)' }}>{error}</p>}<div className="grid grid-cols-1 md:grid-cols-3 gap-4">{columns.map(([title, Icon]) => { const items = tasks.filter((task) => task.status === statusFor(title)); return <Panel key={title}><div className="flex items-center justify-between mb-4"><div className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--color-text)' }}><Icon size={16} style={{ color: 'var(--color-accent)' }} />{title}</div><span className="text-[10px] px-2 py-1 rounded-full" style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text-tertiary)' }}>{items.length}</span></div>{items.length === 0 ? <EmptyState icon={ListTodo} title="Nenhuma tarefa" description="As tarefas criadas aparecerão nesta coluna." /> : <div className="space-y-2">{items.map((task) => <div key={task.id} className="rounded-xl p-3" style={{ background: 'var(--color-bg-secondary)' }}><div className="text-xs font-medium" style={{ color: 'var(--color-text)' }}>{task.title}</div><div className="text-[10px] mt-1" style={{ color: 'var(--color-text-tertiary)' }}>{task.priority}</div></div>)}</div>}</Panel>; })}</div></>;
}

function IntegrationsView() {
  const [connectors, setConnectors] = useState<ConnectorInfo[]>([]);
  useEffect(() => { void listConnectors().then(setConnectors).catch(() => setConnectors([])); }, []);
  return <><Header kind="integrations" onAction={() => window.alert('Selecione uma fonte de dados para iniciar a conexão.')} /><Panel><div className="flex items-center gap-3 mb-4"><Search size={16} style={{ color: 'var(--color-text-tertiary)' }} /><input className="flex-1 bg-transparent outline-none text-sm" placeholder="Buscar integrações..." style={{ color: 'var(--color-text)' }} /></div>{connectors.length === 0 ? <EmptyState icon={Link2} title="Nenhuma integração conectada" description="Conecte uma fonte de dados para disponibilizá-la aos agentes e ao Deep Research." /> : <div className="grid grid-cols-1 md:grid-cols-2 gap-3">{connectors.map((connector) => <div key={connector.connector_id} className="flex items-center gap-3 rounded-xl p-4" style={{ background: 'var(--color-bg-secondary)' }}><Link2 size={20} style={{ color: 'var(--color-accent)' }} /><div className="flex-1"><div className="text-sm font-medium" style={{ color: 'var(--color-text)' }}>{connector.display_name}</div><div className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>{connector.chunks} itens indexados</div></div><span className="text-[10px]" style={{ color: connector.connected ? 'var(--color-success)' : 'var(--color-error)' }}>{connector.connected ? 'Conectada' : 'Desconectada'}</span></div>)}</div>}</Panel></>;
}

function MemoryView() {
  const [memory, setMemory] = useState<Record<string, unknown>>(() => loadMemoryPreferences() as unknown as Record<string, unknown>);
  useEffect(() => { void fetchWorkspaceSettings().then((settings) => { if (settings.memory && typeof settings.memory === 'object') setMemory(settings.memory as Record<string, unknown>); }).catch(() => {}); }, []);
  return <><Header kind="memory" /><div className="grid grid-cols-1 lg:grid-cols-[1.2fr_.8fr] gap-4"><Panel><div className="flex items-center gap-3 mb-5"><span className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'var(--color-accent-subtle)', color: 'var(--color-accent)' }}><Database size={20} /></span><div><h2 className="text-sm font-medium" style={{ color: 'var(--color-text)' }}>Contexto de conversas</h2><p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>Recupere informações relevantes quando o chat precisar.</p></div></div><EmptyState icon={Search} title="Nenhuma memória pesquisada" description="As memórias recuperadas aparecerão aqui quando o backend de memória estiver ativo." /></Panel><Panel><h2 className="text-sm font-medium mb-4" style={{ color: 'var(--color-text)' }}>Configuração atual</h2><div className="space-y-3 text-xs" style={{ color: 'var(--color-text-secondary)' }}><div className="flex justify-between"><span>Uso de memória</span><span style={{ color: 'var(--color-text)' }}>{memory.enabled !== false ? 'Ativo' : 'Desativado'}</span></div><div className="flex justify-between"><span>Backend</span><span style={{ color: 'var(--color-text)' }}>{String(memory.backend || 'sqlite')}</span></div></div></Panel></div></>;
}

function ToolsView() {
  const tools = [['Pesquisa web', 'Consulte fontes externas com transparência.', Search], ['Análise de dados', 'Trabalhe com documentos e fontes conectadas.', Database], ['Automação', 'Execute fluxos com agentes controlados.', Wrench], ['Código', 'Apoie tarefas técnicas e revisão de código.', Code2], ['Conhecimento', 'Recupere contexto antes de responder.', Sparkles], ['Segurança', 'Aplique políticas e controle de capacidades.', ShieldCheck]] as const;
  return <><Header kind="tools" /><div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">{tools.map(([title, description, Icon]) => <Panel key={title}><Icon size={21} style={{ color: 'var(--color-accent)' }} /><h2 className="text-sm font-medium mt-4" style={{ color: 'var(--color-text)' }}>{title}</h2><p className="text-xs mt-1" style={{ color: 'var(--color-text-tertiary)' }}>{description}</p><div className="mt-4 text-[10px]" style={{ color: 'var(--color-success)' }}>Disponível para configuração</div></Panel>)}</div></>;
}

function ApiView() {
  const [keys, setKeys] = useState<Record<string, boolean>>({});
  const [appKeys, setAppKeys] = useState<AppKeyInfo[]>([]);
  const [name, setName] = useState('Minha integração');
  const [secret, setSecret] = useState('');
  const [error, setError] = useState('');
  const refresh = () => { void Promise.all([getCloudKeyStatus().catch(() => ({})), listAppKeys().catch(() => [])]).then(([providerKeys, clientKeys]) => { setKeys(providerKeys); setAppKeys(clientKeys); }); };
  useEffect(() => { refresh(); }, []);
  const create = async () => { setError(''); try { const result = await createAppKey(name, ['chat']); setSecret(result.secret); refresh(); } catch (e) { setError(e instanceof Error ? e.message : 'Não foi possível criar a chave.'); } };
  const revoke = async (id: string) => { try { await revokeAppKey(id); refresh(); } catch (e) { setError(e instanceof Error ? e.message : 'Não foi possível revogar a chave.'); } };
  return <><Header kind="api" /><div className="grid grid-cols-1 lg:grid-cols-[1fr_.8fr] gap-4"><Panel><div className="flex items-center justify-between mb-4"><div><h2 className="text-sm font-medium" style={{ color: 'var(--color-text)' }}>Chaves de aplicação</h2><p className="text-xs mt-1" style={{ color: 'var(--color-text-tertiary)' }}>Para outros sistemas chamarem o JARVIS. Exibida apenas uma vez.</p></div><KeyRound size={18} style={{ color: 'var(--color-accent)' }} /></div><div className="flex flex-col sm:flex-row gap-2 mb-4"><input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nome da integração" className="flex-1 rounded-lg px-3 py-2 text-xs outline-none" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', color: 'var(--color-text)' }} /><button onClick={() => void create()} className="rounded-lg px-3 py-2 text-xs font-medium" style={{ background: 'var(--color-accent)', color: 'var(--color-on-accent)' }}>Nova chave</button></div>{secret && <div className="mb-4 rounded-lg p-3 text-xs" style={{ background: 'var(--color-accent-subtle)', color: 'var(--color-text)' }}><div className="font-medium">Copie agora; ela não será exibida novamente.</div><code className="block mt-2 break-all">{secret}</code></div>}{error && <p className="mb-3 text-xs" style={{ color: 'var(--color-error)' }}>{error}</p>}{appKeys.length === 0 ? <EmptyState icon={KeyRound} title="Nenhuma chave criada" description="Crie uma chave independente para uma aplicação externa." /> : <div className="space-y-2">{appKeys.map((appKey) => <div key={appKey.id} className="flex items-center gap-3 rounded-xl p-3" style={{ background: 'var(--color-bg-secondary)' }}><KeyRound size={16} style={{ color: appKey.revoked ? 'var(--color-error)' : 'var(--color-success)' }} /><div className="flex-1 min-w-0"><div className="text-xs font-medium truncate" style={{ color: 'var(--color-text)' }}>{appKey.name}</div><code className="text-[10px]" style={{ color: 'var(--color-text-tertiary)' }}>{appKey.key_prefix}...</code></div>{appKey.revoked ? <span className="text-[10px]" style={{ color: 'var(--color-error)' }}>Revogada</span> : <button onClick={() => void revoke(appKey.id)} className="text-[10px]" style={{ color: 'var(--color-error)' }}>Revogar</button>}</div>)}</div>}</Panel><Panel><h2 className="text-sm font-medium mb-4" style={{ color: 'var(--color-text)' }}>Providers configurados</h2><p className="text-xs mb-3" style={{ color: 'var(--color-text-tertiary)' }}>Estas são as credenciais usadas pelo JARVIS. Elas nunca são expostas como chaves de aplicação.</p><div className="space-y-2">{['OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GEMINI_API_KEY', 'OPENROUTER_API_KEY', 'ATLASCLOUD_API_KEY'].map((key) => <div key={key} className="flex items-center gap-2 text-xs" style={{ color: 'var(--color-text-secondary)' }}><span className="w-2 h-2 rounded-full" style={{ background: keys[key] ? 'var(--color-success)' : 'var(--color-text-tertiary)' }} />{key}<span className="ml-auto">{keys[key] ? 'configurada' : 'não configurada'}</span></div>)}</div></Panel></div></>;
}

function AgentDetailView() {
  const navigate = useNavigate();
  const { agentId } = useParams();
  const agents = useAppStore((s) => s.managedAgents);
  const agent = agents.find((item) => item.id === agentId) || agents[0];
  if (!agent) return <><Header kind="agent-detail" /><Panel><EmptyState icon={Bot} title="Nenhum agente selecionado" description="Crie ou selecione um agente para visualizar seus detalhes." action="Ir para agentes" onAction={() => navigate('/agents')} /></Panel></>;
  return <><Header kind="agent-detail" /><Panel><div className="flex flex-col lg:flex-row lg:items-center gap-4"><div className="w-14 h-14 rounded-2xl flex items-center justify-center" style={{ background: 'var(--color-accent-subtle)', color: 'var(--color-accent)' }}><Bot size={28} /></div><div className="flex-1"><div className="flex items-center gap-2"><h2 className="text-lg font-semibold" style={{ color: 'var(--color-text)' }}>{agent.name}</h2><span className="text-[10px] rounded-full px-2 py-1" style={{ color: 'var(--color-success)', background: 'color-mix(in srgb, var(--color-success) 12%, transparent)' }}>{agent.status}</span></div><p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>{agent.agent_type}</p></div><div className="flex gap-2"><button onClick={() => navigate(`/agents/${agent.id}/configure`)} className="rounded-lg px-3 py-2 text-xs cursor-pointer" style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text)' }}>Editar agente</button><button onClick={() => navigate('/')} className="rounded-lg px-3 py-2 text-xs cursor-pointer" style={{ background: 'var(--color-accent)', color: 'var(--color-on-accent)' }}>Testar agente</button></div></div></Panel><div className="grid grid-cols-1 lg:grid-cols-[1.1fr_.9fr] gap-4"><Panel><h2 className="text-sm font-medium mb-4" style={{ color: 'var(--color-text)' }}>Visão geral</h2><div className="grid grid-cols-2 gap-3"><Metric label="Status" value={agent.status} /><Metric label="Tipo" value={agent.agent_type} /><Metric label="Criado em" value={new Date(agent.created_at).toLocaleDateString()} /><Metric label="Atualizado" value={new Date(agent.updated_at).toLocaleDateString()} /></div></Panel><Panel><h2 className="text-sm font-medium mb-4" style={{ color: 'var(--color-text)' }}>Responsabilidades</h2><p className="text-sm leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>{agent.summary_memory || 'Nenhuma descrição cadastrada para este agente.'}</p></Panel></div></>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl p-3" style={{ background: 'var(--color-bg-secondary)' }}><div className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--color-text-tertiary)' }}>{label}</div><div className="text-sm mt-1 truncate" style={{ color: 'var(--color-text)' }}>{value}</div></div>;
}

function AgentConfigView() {
  const navigate = useNavigate();
  const { agentId } = useParams();
  const agents = useAppStore((s) => s.managedAgents);
  const existing = agents.find((agent) => agent.id === agentId);
  const [name, setName] = useState(existing?.name || 'Novo agente');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('Análise de dados');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const sections = ['Identificação', 'Modelo', 'Instruções', 'Ferramentas', 'Ações', 'Memória', 'Segurança', 'Testes'];
  const save = async () => { setBusy(true); setError(''); try { const config = { description, category }; if (existing) await updateManagedAgent(existing.id, { name, config }); else await createManagedAgent({ name, agent_type: category, config }); navigate('/agents'); } catch (e) { setError(e instanceof Error ? e.message : 'Não foi possível salvar o agente.'); } finally { setBusy(false); } };
  return <><Header kind="agent-config" /><div className="grid grid-cols-1 lg:grid-cols-[210px_1fr] gap-4"><Panel className="p-2"><div className="space-y-1">{sections.map((section, index) => <button key={section} className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-left cursor-pointer" style={{ background: index === 0 ? 'var(--color-accent-subtle)' : 'transparent', color: index === 0 ? 'var(--color-accent)' : 'var(--color-text-secondary)' }}>{index + 1}. {section}</button>)}</div></Panel><Panel><div className="flex items-center justify-between mb-5"><div><h2 className="text-sm font-medium" style={{ color: 'var(--color-text)' }}>Identificação do agente</h2><p className="text-xs mt-1" style={{ color: 'var(--color-text-tertiary)' }}>Defina como o agente aparece no ecossistema.</p></div><div className="flex gap-2"><button onClick={() => navigate('/agents')} className="rounded-lg px-3 py-2 text-xs cursor-pointer" style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text)' }}>Cancelar</button><button disabled={busy} onClick={() => void save()} className="rounded-lg px-3 py-2 text-xs cursor-pointer disabled:opacity-60" style={{ background: 'var(--color-accent)', color: 'var(--color-on-accent)' }}>{busy ? 'Salvando...' : 'Salvar'}</button></div></div>{error && <p className="mb-3 text-xs" style={{ color: 'var(--color-error)' }}>{error}</p>}<div className="grid grid-cols-1 md:grid-cols-2 gap-4"><label className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>Nome<input value={name} onChange={(event) => setName(event.target.value)} className="mt-2 w-full rounded-lg px-3 py-2 text-sm outline-none" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', color: 'var(--color-text)' }} /></label><label className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>Categoria<select value={category} onChange={(event) => setCategory(event.target.value)} className="mt-2 w-full rounded-lg px-3 py-2 text-sm outline-none" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', color: 'var(--color-text)' }}><option>Análise de dados</option><option>Pesquisa</option><option>Automação</option><option>Conteúdo</option></select></label><label className="text-xs md:col-span-2" style={{ color: 'var(--color-text-secondary)' }}>Descrição<textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={4} placeholder="Explique o que este agente faz..." className="mt-2 w-full rounded-lg px-3 py-2 text-sm outline-none resize-none" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', color: 'var(--color-text)' }} /></label></div></Panel></div></>;
}

function ConclaveView() {
  const [conclaves, setConclaves] = useState<WorkspaceConclave[]>([]);
  const refresh = () => { void fetchWorkspaceConclaves().then(setConclaves).catch(() => setConclaves([])); };
  useEffect(() => { refresh(); }, []);
  const create = async () => { const title = window.prompt('Nome do Conclave'); if (!title?.trim()) return; await createWorkspaceConclave(title).then(refresh).catch(() => {}); };
  return <><Header kind="conclave" onAction={() => void create()} /><div className="grid grid-cols-1 lg:grid-cols-[1.1fr_.9fr] gap-4"><Panel><div className="flex items-center gap-2 border-b pb-3 mb-4" style={{ borderColor: 'var(--color-border)' }}><button className="text-xs px-3 py-1.5 rounded-lg" style={{ background: 'var(--color-accent-subtle)', color: 'var(--color-accent)' }}>Ativos</button><button className="text-xs px-3 py-1.5 rounded-lg" style={{ color: 'var(--color-text-tertiary)' }}>Arquivados</button></div>{conclaves.length === 0 ? <EmptyState icon={UsersRound} title="Nenhuma sessão ativa" description="Reúna agentes para comparar propostas, analisar alternativas e registrar uma decisão." action="Novo Conclave" onAction={() => void create()} /> : <div className="space-y-2">{conclaves.map((item) => <div key={item.id} className="rounded-xl p-3" style={{ background: 'var(--color-bg-secondary)' }}><div className="text-sm font-medium" style={{ color: 'var(--color-text)' }}>{item.title}</div><div className="text-xs mt-1" style={{ color: 'var(--color-text-tertiary)' }}>{item.objective || 'Sem objetivo definido'}</div></div>)}</div>}</Panel><Panel><h2 className="text-sm font-medium mb-4" style={{ color: 'var(--color-text)' }}>Última discussão</h2><EmptyState icon={MessageSquare} title="Sem discussões recentes" description="As conversas e decisões do Conclave aparecerão aqui." /></Panel></div></>;
}

function NotificationsView() {
  const [items, setItems] = useState<WorkspaceNotification[]>([]);
  useEffect(() => { void fetchWorkspaceNotifications().then(setItems).catch(() => setItems([])); }, []);
  return <><Header kind="notifications" /><Panel><div className="flex items-center gap-2 mb-4"><button className="text-xs px-3 py-1.5 rounded-lg" style={{ background: 'var(--color-accent-subtle)', color: 'var(--color-accent)' }}>Todas</button><button className="text-xs px-3 py-1.5 rounded-lg" style={{ color: 'var(--color-text-tertiary)' }}>Não lidas</button></div>{items.length === 0 ? <EmptyState icon={Activity} title="Nenhuma notificação" description="Quando um agente concluir uma tarefa ou houver um alerta importante, ele aparecerá aqui." /> : <div className="space-y-2">{items.map((item) => <div key={item.id} className="rounded-xl p-3" style={{ background: 'var(--color-bg-secondary)' }}><div className="text-sm" style={{ color: 'var(--color-text)' }}>{item.title}</div><div className="text-xs mt-1" style={{ color: 'var(--color-text-tertiary)' }}>{item.body}</div></div>)}</div>}</Panel></>;
}

function ProfileView() {
  const settings = useAppStore((s) => s.settings);
  const [user, setUser] = useState<AuthUser | null>(null);
  useEffect(() => { void import('../lib/api').then(({ fetchCurrentUser }) => fetchCurrentUser().then((result) => setUser(result.user)).catch(() => {})); }, []);
  return <><Header kind="profile" /><div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-4"><Panel><div className="w-16 h-16 rounded-full mx-auto flex items-center justify-center text-xl font-semibold" style={{ background: 'var(--color-accent)', color: 'var(--color-on-accent)' }}>{(user?.display_name || 'J').slice(0, 1).toUpperCase()}</div><h2 className="text-center text-sm font-medium mt-3" style={{ color: 'var(--color-text)' }}>{user?.display_name || 'Operador local'}</h2><p className="text-center text-xs mt-1" style={{ color: 'var(--color-text-tertiary)' }}>{user?.email || 'Instalação pessoal'}</p></Panel><Panel><h2 className="text-sm font-medium mb-4" style={{ color: 'var(--color-text)' }}>Preferências</h2><div className="space-y-3 text-xs" style={{ color: 'var(--color-text-secondary)' }}><div className="flex justify-between"><span>Tema</span><span style={{ color: 'var(--color-text)' }}>{settings.theme}</span></div><div className="flex justify-between"><span>Fonte</span><span style={{ color: 'var(--color-text)' }}>{settings.fontSize}</span></div><div className="flex justify-between"><span>API local</span><span className="max-w-[260px] truncate" style={{ color: 'var(--color-text)' }}>{settings.apiUrl || 'Servidor atual'}</span></div></div></Panel></div></>;
}

function SimpleView({ kind }: { kind: WorkspaceKind }) {
  const copy = pageCopy[kind];
  const Icon = copy.icon;
  const details = kind === 'conclave' ? 'Crie uma sessão para reunir agentes e registrar uma decisão.' : kind === 'notifications' ? 'Você verá aqui conclusões, alertas e eventos do sistema.' : kind === 'profile' ? 'O perfil local ainda não possui autenticação conectada.' : 'Selecione um agente para visualizar detalhes e configurações.';
  return <><Header kind={kind} onAction={kind === 'agent-config' ? undefined : () => window.alert('Esta ação será conectada ao fluxo correspondente.')} /><Panel><EmptyState icon={Icon} title={kind === 'profile' ? 'Perfil local' : 'Nenhum item disponível'} description={details} action={kind === 'agent-detail' ? 'Abrir agentes' : undefined} /></Panel></>;
}

export function WorkspacePage({ kind }: { kind: WorkspaceKind }) {
  return <div className="flex-1 overflow-y-auto px-4 py-5 md:px-6 md:py-7" style={{ background: 'radial-gradient(circle at 18% 0%, color-mix(in srgb, var(--color-accent) 8%, transparent), transparent 32%), var(--color-bg)' }}><div className="max-w-[1440px] mx-auto space-y-4">{kind === 'projects' ? <ProjectsView /> : kind === 'tasks' ? <TasksView /> : kind === 'integrations' ? <IntegrationsView /> : kind === 'memory' ? <MemoryView /> : kind === 'tools' ? <ToolsView /> : kind === 'api' ? <ApiView /> : kind === 'agent-detail' ? <AgentDetailView /> : kind === 'agent-config' ? <AgentConfigView /> : kind === 'conclave' ? <ConclaveView /> : kind === 'notifications' ? <NotificationsView /> : kind === 'profile' ? <ProfileView /> : <SimpleView kind={kind} />}</div></div>;
}
