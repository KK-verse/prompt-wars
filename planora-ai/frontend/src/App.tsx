import {
  Activity,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  CalendarDays,
  Check,
  CheckCheck,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  Clock3,
  Download,
  FileText,
  Heart,
  Lightbulb,
  LoaderCircle,
  MapPin,
  Menu,
  MessageCircle,
  Pencil,
  Plus,
  Search,
  Send,
  Sparkles,
  Store,
  Utensils,
  WalletCards,
  WandSparkles,
  UsersRound,
  X,
} from 'lucide-react'
import {
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from 'recharts'
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { api, jsonBody, patchBody } from './api'
import type {
  ChatMessage,
  DashboardResponse,
  EventRecord,
  Guest,
  Idea,
  Task,
  Vendor,
} from './types'

type PageId = 'overview' | 'budget' | 'timeline' | 'guests' | 'vendors' | 'ideas' | 'reports'
type AssistantMode = 'local' | 'gemini' | 'gemini-unavailable'
const ephemeralDemo = import.meta.env.VITE_PLANORA_EPHEMERAL_DATA === '1'

const NAVIGATION: Array<{ id: PageId; label: string; icon: typeof Activity }> = [
  { id: 'overview', label: 'Overview', icon: Activity },
  { id: 'budget', label: 'Budget', icon: WalletCards },
  { id: 'timeline', label: 'Timeline', icon: CalendarDays },
  { id: 'guests', label: 'Guests', icon: UsersRound },
  { id: 'vendors', label: 'Vendors', icon: Store },
  { id: 'ideas', label: 'Inspiration', icon: Lightbulb },
  { id: 'reports', label: 'Reports', icon: FileText },
]

const CHART_COLORS = ['#7258d8', '#9c87e8', '#c4b8f3', '#e6b56b', '#6d9b8b', '#e38c72', '#7b95b1', '#d47794', '#90a36a', '#a7a4bb']
const TODAY = new Date().toISOString().slice(0, 10)

function currency(value: number | string | null | undefined) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(Number(value || 0))
}

function shortCurrency(value: number) {
  const amount = Number(value || 0)
  if (amount >= 10_000_000) return `₹${(amount / 10_000_000).toFixed(1)}Cr`
  if (amount >= 100_000) return `₹${(amount / 100_000).toFixed(amount % 100_000 === 0 ? 0 : 1)}L`
  if (amount >= 1_000) return `₹${Math.round(amount / 1_000)}k`
  return currency(amount)
}

function formatDate(value: string | null | undefined, options: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric', year: 'numeric' }) {
  if (!value) return 'Date to be confirmed'
  const date = new Date(`${value}T00:00:00`)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('en-IN', options)
}

function daysUntil(value: string | null | undefined) {
  if (!value) return null
  const date = new Date(`${value}T00:00:00`)
  return Math.ceil((date.getTime() - new Date(`${TODAY}T00:00:00`).getTime()) / 86_400_000)
}

function greeting() {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
}

type ApiError = { message?: string }

function App() {
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null)
  const [activeEventId, setActiveEventId] = useState<string | null>(null)
  const [page, setPage] = useState<PageId>('overview')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [assistantMode, setAssistantMode] = useState<AssistantMode>('local')
  const [assistantBusy, setAssistantBusy] = useState(false)
  const [assistantDraft, setAssistantDraft] = useState('')
  const [pageLoading, setPageLoading] = useState(true)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')
  const [newEventOpen, setNewEventOpen] = useState(false)
  const [eventDetailsOpen, setEventDetailsOpen] = useState(false)
  const [inviteDraft, setInviteDraft] = useState('')
  const [inviteOpen, setInviteOpen] = useState(false)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [selectedVendors, setSelectedVendors] = useState<string[]>([])
  const [vendorComparison, setVendorComparison] = useState<Vendor[] | null>(null)

  const event = dashboard?.event ?? null
  const metrics = dashboard?.metrics
  const events = dashboard?.events ?? []
  const currentTitle = NAVIGATION.find((item) => item.id === page)?.label ?? 'Overview'

  async function refresh(selectedId?: string) {
    const id = selectedId ?? activeEventId
    const path = id ? `/api/dashboard?event_id=${encodeURIComponent(id)}` : '/api/dashboard'
    try {
      const data = await api<DashboardResponse>(path)
      setDashboard(data)
      setActiveEventId(data.event?.id ?? null)
      setMessages(data.event?.messages ?? [])
      setError('')
      if (data.event && !selectedId && !activeEventId) setActiveEventId(data.event.id)
    } catch (caught) {
      const message = (caught as ApiError).message || 'Could not connect to the Planora API.'
      setError(`${message} Start the API server using the steps in README.md.`)
    } finally {
      setPageLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
    // The first request intentionally uses the server's default active event.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(''), 2800)
    return () => window.clearTimeout(timer)
  }, [toast])

  async function selectEvent(id: string) {
    setActiveEventId(id)
    setVendorComparison(null)
    await refresh(id)
  }

  async function sendAssistantMessage(value: string) {
    const content = value.trim()
    if (!content || assistantBusy) return
    setAssistantBusy(true)
    setAssistantDraft('')
    try {
      const result = await api<{
        message: string
        event_id: string | null
        mode?: AssistantMode
        tool_name?: string | null
      }>('/api/assistant/chat', jsonBody({ message: content, event_id: event?.id ?? null }))
      setAssistantMode(result.mode ?? 'local')
      if (result.event_id) {
        setPage('overview')
        setNewEventOpen(false)
        await refresh(result.event_id)
      } else {
        setMessages((current) => [
          ...current,
          { id: `local-user-${Date.now()}`, role: 'user', content, created_at: new Date().toISOString() },
          { id: `local-assistant-${Date.now()}`, role: 'assistant', content: result.message, created_at: new Date().toISOString() },
        ])
      }
      if (result.mode === 'gemini-unavailable') setToast('Gemini is unavailable. Check the event workspace for saved changes.')
    } catch (caught) {
      setToast((caught as ApiError).message || 'The assistant could not complete that request.')
    } finally {
      setAssistantBusy(false)
    }
  }

  async function createEvent(details: Record<string, unknown>, description?: string) {
    try {
      if (description?.trim()) {
        const result = await api<{ event_id: string | null; message: string; mode?: AssistantMode }>(
          '/api/assistant/chat',
          jsonBody({ message: description, event_id: null }),
        )
        setAssistantMode(result.mode ?? 'local')
        if (result.event_id) {
          setPage('overview')
          setNewEventOpen(false)
          await refresh(result.event_id)
          setToast('Your event workspace is ready.')
        } else {
          setMessages([{ id: `welcome-${Date.now()}`, role: 'assistant', content: result.message, created_at: new Date().toISOString() }])
        }
        return
      }
      const created = await api<EventRecord>('/api/events', jsonBody(details))
      setPage('overview')
      setNewEventOpen(false)
      await refresh(created.id)
      setToast('Your event workspace is ready.')
    } catch (caught) {
      setToast((caught as ApiError).message || 'Could not create this event.')
    }
  }

  async function changeEvent(patch: Record<string, unknown>, success = 'Event details updated.') {
    if (!event) return
    try {
      await api(`/api/events/${event.id}`, patchBody(patch))
      await refresh(event.id)
      setToast(success)
    } catch (caught) {
      setToast((caught as ApiError).message || 'Could not update the event.')
    }
  }

  async function updateTask(task: Task, completed: boolean) {
    if (!event) return
    try {
      await api(`/api/events/${event.id}/tasks/${task.id}`, patchBody({ status: completed ? 'completed' : 'pending' }))
      await refresh(event.id)
    } catch (caught) {
      setToast((caught as ApiError).message || 'Could not update this task.')
    }
  }

  async function saveGuest(guest: Record<string, unknown>) {
    if (!event) return
    try {
      await api(`/api/events/${event.id}/guests`, jsonBody(guest))
      await refresh(event.id)
      setToast('Guest added to the list.')
    } catch (caught) {
      setToast((caught as ApiError).message || 'Could not add the guest.')
    }
  }

  async function updateGuest(guestId: string, data: Record<string, unknown>) {
    if (!event) return
    try {
      await api(`/api/events/${event.id}/guests/${guestId}`, patchBody(data))
      await refresh(event.id)
    } catch (caught) {
      setToast((caught as ApiError).message || 'Could not update this guest.')
    }
  }

  async function importGuests(guests: Record<string, unknown>[]) {
    if (!event) return
    try {
      await api(`/api/events/${event.id}/guests/import`, jsonBody(guests))
      await refresh(event.id)
      setToast(`${guests.length} guest records imported.`)
    } catch (caught) {
      setToast((caught as ApiError).message || 'Could not import these guests.')
    }
  }

  async function saveVendor(vendor: Record<string, unknown>) {
    if (!event) return
    try {
      await api(`/api/events/${event.id}/vendors`, jsonBody(vendor))
      await refresh(event.id)
      setToast('Vendor record added. It is marked as user-entered.')
    } catch (caught) {
      setToast((caught as ApiError).message || 'Could not add this vendor record.')
    }
  }

  async function saveActual(category: string, actualCost: number) {
    if (!event) return
    try {
      await api(`/api/events/${event.id}/expenses`, jsonBody({ category, actual_cost: actualCost }))
      await refresh(event.id)
      setToast('Actual spend saved.')
    } catch (caught) {
      setToast((caught as ApiError).message || 'Could not save actual spend.')
    }
  }

  async function regenerateIdeas(theme: string) {
    if (!event) return
    try {
      await api(`/api/events/${event.id}/ideas`, jsonBody({ theme, budget: event.total_budget }))
      await refresh(event.id)
      setToast('Fresh event concepts are ready.')
    } catch (caught) {
      setToast((caught as ApiError).message || 'Could not generate concepts.')
    }
  }

  async function chooseIdea(idea: Idea) {
    await changeEvent({ theme: idea.title, decoration_preferences: idea.decoration.join(', ') }, 'Theme direction saved to your event.')
  }

  async function draftInvitation(tone: string, language: string) {
    if (!event) return
    try {
      const result = await api<{ draft: string }>(`/api/events/${event.id}/invitation`, jsonBody({ tone, language }))
      setInviteDraft(result.draft)
      setInviteOpen(true)
    } catch (caught) {
      setToast((caught as ApiError).message || 'Could not draft the invitation.')
    }
  }

  async function compareSelectedVendors() {
    if (!event || selectedVendors.length < 2) return
    try {
      const result = await api<{ vendors: Vendor[] }>(`/api/events/${event.id}/vendors/compare`, jsonBody({ vendor_ids: selectedVendors }))
      setVendorComparison(result.vendors)
    } catch (caught) {
      setToast((caught as ApiError).message || 'Could not compare these vendor records.')
    }
  }

  async function exportReport() {
    if (!event) return
    try {
      const report = await api<Record<string, unknown>>(`/api/events/${event.id}/report`)
      downloadBlob(JSON.stringify(report, null, 2), `${event.title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}-report.json`, 'application/json')
      setToast('Event report downloaded.')
    } catch (caught) {
      setToast((caught as ApiError).message || 'Could not export the report.')
    }
  }

  const pageProps = {
    event,
    metrics,
    onPage: setPage,
    onNewEvent: () => setNewEventOpen(true),
    onEditEvent: () => setEventDetailsOpen(true),
    onTaskChange: updateTask,
    onEventChange: changeEvent,
    onSaveGuest: saveGuest,
    onUpdateGuest: updateGuest,
    onImportGuests: importGuests,
    onSaveVendor: saveVendor,
    onSaveActual: saveActual,
    onRegenerateIdeas: regenerateIdeas,
    onChooseIdea: chooseIdea,
    onDraftInvitation: draftInvitation,
    onExportReport: exportReport,
    selectedVendors,
    setSelectedVendors,
    vendorComparison,
    onCompareVendors: compareSelectedVendors,
  }

  return (
    <div className="app-shell">
      <Sidebar
        activePage={page}
        open={mobileNavOpen}
        onClose={() => setMobileNavOpen(false)}
        onNavigate={(nextPage) => {
          setPage(nextPage)
          setMobileNavOpen(false)
        }}
        onNewEvent={() => setNewEventOpen(true)}
      />
      <div className="main-shell">
        <Topbar
          title={currentTitle}
          events={events}
          activeEventId={activeEventId}
          onSelectEvent={selectEvent}
          onNewEvent={() => setNewEventOpen(true)}
          onMenu={() => setMobileNavOpen(true)}
        />
        {error && <div className="connection-banner"><span className="connection-dot" />{error}</div>}
        {ephemeralDemo && <div className="prototype-banner">Prototype storage: changes may reset between visits. Use demo data only.</div>}
        <main className="content-wrap">
          {pageLoading && !dashboard ? (
            <div className="loading-state"><LoaderCircle className="spin" size={24} /><span>Opening your workspace…</span></div>
          ) : (
            <div className="workspace-columns">
              <section className="page-column">
                {page === 'overview' && <OverviewPage {...pageProps} greeting={greeting()} />}
                {page === 'budget' && <BudgetPage {...pageProps} />}
                {page === 'timeline' && <TimelinePage {...pageProps} />}
                {page === 'guests' && <GuestsPage {...pageProps} />}
                {page === 'vendors' && <VendorsPage {...pageProps} />}
                {page === 'ideas' && <IdeasPage {...pageProps} />}
                {page === 'reports' && <ReportsPage {...pageProps} />}
              </section>
              <AssistantPanel
                event={event}
                messages={messages}
                mode={assistantMode}
                busy={assistantBusy}
                draft={assistantDraft}
                onDraftChange={setAssistantDraft}
                onSend={sendAssistantMessage}
              />
            </div>
          )}
        </main>
      </div>
      {newEventOpen && <NewEventModal onClose={() => setNewEventOpen(false)} onCreate={createEvent} />}
      {eventDetailsOpen && event && <EventDetailsModal event={event} onClose={() => setEventDetailsOpen(false)} onSave={(updates) => { setEventDetailsOpen(false); void changeEvent(updates, 'Event details updated.') }} />}
      {inviteOpen && <InviteModal draft={inviteDraft} onClose={() => setInviteOpen(false)} onCopy={() => setToast('Invitation draft copied.')} />}
      {toast && <div className="toast"><CheckCircle2 size={17} />{toast}</div>}
    </div>
  )
}

function Sidebar({
  activePage,
  open,
  onClose,
  onNavigate,
  onNewEvent,
}: {
  activePage: PageId
  open: boolean
  onClose: () => void
  onNavigate: (id: PageId) => void
  onNewEvent: () => void
}) {
  return (
    <>
      <button className={`mobile-scrim ${open ? 'visible' : ''}`} aria-label="Close navigation" onClick={onClose} />
      <aside className={`sidebar ${open ? 'sidebar-open' : ''}`}>
        <div className="brand-row">
          <div className="brand-mark"><span>p</span><i /></div>
          <div className="brand-type"><strong>planora</strong><span>AI event studio</span></div>
          <button className="icon-button sidebar-close" aria-label="Close navigation" onClick={onClose}><X size={18} /></button>
        </div>

      <div className="workspace-switcher">
          <div className="workspace-icon"><Heart size={16} fill="currentColor" /></div>
          <span><strong>Personal workspace</strong><small>Starter plan</small></span>
          <ChevronDown size={15} />
      </div>

        <div className="sidebar-label">WORKSPACE</div>
        <nav className="main-nav" aria-label="Workspace navigation">
          {NAVIGATION.map((item) => {
            const Icon = item.icon
            return (
              <button key={item.id} className={`nav-item ${activePage === item.id ? 'active' : ''}`} onClick={() => onNavigate(item.id)}>
                <Icon size={17} strokeWidth={activePage === item.id ? 2.1 : 1.8} />
                <span>{item.label}</span>
                {item.id === 'overview' && <span className="nav-live-dot" />}
              </button>
            )
          })}
        </nav>

        <div className="sidebar-events-heading"><span>YOUR EVENTS</span><button className="icon-button tiny" onClick={onNewEvent} aria-label="Add event"><Plus size={15} /></button></div>
        <div className="mini-event">
          <span className="mini-event-dot" />
          <span>Active event</span>
          <ChevronRight size={14} />
        </div>

        <div className="sidebar-spacer" />
        <div className="sidebar-tip">
          <div className="tip-spark"><Sparkles size={15} /></div>
          <strong>A little help goes a long way</strong>
          <p>Ask Planora to adjust a budget, find your next milestone, or shape an idea.</p>
          <button onClick={() => onNavigate('overview')}>Meet your assistant <ArrowRight size={14} /></button>
        </div>
        <div className="profile-row">
          <div className="profile-avatar">K</div>
          <div><strong>Keshav</strong><span>Personal account</span></div>
        </div>
      </aside>
    </>
  )
}

function Topbar({
  title,
  events,
  activeEventId,
  onSelectEvent,
  onNewEvent,
  onMenu,
}: {
  title: string
  events: DashboardResponse['events']
  activeEventId: string | null
  onSelectEvent: (id: string) => void
  onNewEvent: () => void
  onMenu: () => void
}) {
  return (
    <header className="topbar">
      <div className="topbar-left">
        <button className="icon-button mobile-menu" aria-label="Open navigation" onClick={onMenu}><Menu size={20} /></button>
        <div className="breadcrumb"><span>Workspace</span><ChevronRight size={14} /><strong>{title}</strong></div>
      </div>
      <div className="topbar-actions">
        <label className="event-picker">
          <CalendarDays size={15} />
          <select value={activeEventId ?? ''} onChange={(event) => event.target.value && onSelectEvent(event.target.value)} aria-label="Select active event">
            {events.length === 0 && <option value="">No events yet</option>}
            {events.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
          </select>
          <ChevronDown size={14} />
        </label>
        <button className="topbar-add" onClick={onNewEvent}><Plus size={16} /><span>New event</span></button>
      </div>
    </header>
  )
}

function PageIntro({
  eyebrow,
  title,
  text,
  action,
}: {
  eyebrow?: string
  title: string
  text?: string
  action?: ReactNode
}) {
  return (
    <div className="page-intro">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {text && <p>{text}</p>}
      </div>
      {action && <div className="page-intro-action">{action}</div>}
    </div>
  )
}

function MetricCard({
  label,
  value,
  note,
  icon: Icon,
  accent,
  trend,
}: {
  label: string
  value: string
  note: string
  icon: typeof Activity
  accent: string
  trend?: 'up' | 'down'
}) {
  return (
    <article className="metric-card">
      <div className={`metric-icon ${accent}`}><Icon size={18} /></div>
      <div className="metric-copy"><span>{label}</span><strong>{value}</strong><small>{trend === 'up' ? <ArrowUpRight size={13} /> : trend === 'down' ? <ArrowDownRight size={13} /> : null}{note}</small></div>
    </article>
  )
}

function OverviewPage({
  event,
  metrics,
  greeting: hello,
  onPage,
  onNewEvent,
  onEditEvent,
  onTaskChange,
}: {
  event: EventRecord | null
  metrics?: DashboardResponse['metrics']
  greeting: string
  onPage: (page: PageId) => void
  onNewEvent: () => void
  onEditEvent: () => void
  onTaskChange: (task: Task, completed: boolean) => void
}) {
  if (!event) return <EmptyWorkspace onNewEvent={onNewEvent} />
  const days = daysUntil(event.event_date)
  const nextTasks = event.tasks.filter((task) => task.status !== 'completed').slice(0, 4)
  const completed = event.tasks.filter((task) => task.status === 'completed').length
  const progress = event.tasks.length ? Math.round((completed / event.tasks.length) * 100) : 0
  const totalEstimated = event.expenses.reduce((sum, item) => sum + item.estimated_cost, 0)

  return (
    <>
      <PageIntro
        eyebrow={`${hello}, Keshav`}
        title="A beautiful day, thoughtfully planned."
        text="Your event details, next steps, and budget are all coming together."
        action={<button className="button button-primary" onClick={onNewEvent}><Plus size={16} />Plan a new event</button>}
      />
      <section className="event-banner">
        <div className="event-banner-art"><div className="banner-orbit orbit-one" /><div className="banner-orbit orbit-two" /><div className="banner-sun" /><div className="banner-leaf leaf-one" /><div className="banner-leaf leaf-two" /><span className="banner-bloom">✳</span></div>
        <div className="event-banner-copy">
          <div className="banner-kicker"><span className="status-pill"><i /> PLANNING IN PROGRESS</span>{event.is_demo && <span className="demo-pill">DEMO WORKSPACE</span>}</div>
          <h2>{event.title}</h2>
          <div className="event-meta-row"><span><MapPin size={14} />{event.location || 'Location to be confirmed'}</span><span><CalendarDays size={14} />{formatDate(event.event_date, { month: 'short', day: 'numeric', year: 'numeric' })}</span><span><UsersRound size={14} />{event.guest_count || '—'} guests</span></div>
        </div>
        <div className="event-countdown">
          <span>{days === null ? 'DATE TBD' : days < 0 ? 'PAST EVENT' : 'COUNTING DOWN'}</span>
          <strong>{days === null ? '—' : Math.max(0, days)}</strong>
          <small>{days === null ? 'add a date' : 'days to go'}</small>
          <button onClick={onEditEvent}>Event details <ArrowRight size={14} /></button>
        </div>
        <div className="event-progress"><div className="progress-label"><span>Planning progress</span><strong>{progress}%</strong></div><div className="progress-track"><i style={{ width: `${progress}%` }} /></div><small>{completed} of {event.tasks.length} milestones complete</small></div>
      </section>

      <div className="metrics-grid">
        <MetricCard label="Planned budget" value={shortCurrency(event.total_budget)} note="Your total target" icon={WalletCards} accent="violet" />
        <MetricCard label="Actual spend" value={shortCurrency(metrics?.actual_spend ?? 0)} note={`${metrics?.remaining_budget ? shortCurrency(metrics.remaining_budget) : '₹0'} remaining`} icon={Activity} accent="peach" trend="down" />
        <MetricCard label="Tasks to go" value={String(metrics?.pending_tasks ?? nextTasks.length)} note={metrics?.overdue_tasks ? `${metrics.overdue_tasks} need attention` : 'You’re on track'} icon={CheckCheck} accent="mint" />
        <MetricCard label="Guests invited" value={`${event.guests.length} / ${event.guest_count || '—'}`} note={`${event.guests.filter((guest) => guest.rsvp_status === 'confirmed').length} confirmed so far`} icon={UsersRound} accent="blue" />
      </div>

      <div className="overview-grid">
        <BudgetOverview event={event} onViewBudget={() => onPage('budget')} totalEstimated={totalEstimated} />
        <TimelinePreview tasks={nextTasks} onViewTimeline={() => onPage('timeline')} onTaskChange={onTaskChange} />
      </div>

      <div className="bottom-overview-grid">
        <article className="card details-card">
          <div className="card-heading"><div><div className="eyebrow">THE DETAILS</div><h3>Your event, your way</h3></div><button className="text-link" onClick={() => onPage('ideas')}>Explore ideas <ArrowRight size={14} /></button></div>
          <div className="detail-chips">
            {event.theme && <span className="detail-chip"><Sparkles size={14} />{event.theme}</span>}
            {event.food_preferences && <span className="detail-chip"><Utensils size={14} />{event.food_preferences}</span>}
            {event.duration_days > 1 && <span className="detail-chip"><CalendarDays size={14} />{event.duration_days} days</span>}
            {event.accommodation_required && <span className="detail-chip"><span className="bed-icon">⌂</span>{event.accommodation_count} guests staying</span>}
            {!event.theme && !event.food_preferences && <span className="muted-copy">Add a theme and preferences to make the plan feel like yours.</span>}
          </div>
        </article>
        <article className="card recommendation-card">
          <div className="recommendation-icon"><WandSparkles size={17} /></div>
          <div><div className="eyebrow">A THOUGHTFUL NEXT STEP</div><strong>{nextTasks[0]?.title ?? 'Your event plan is taking shape'}</strong><p>{nextTasks[0]?.description ?? 'Ask Planora for ideas or review your latest planning report.'}</p></div>
          <button className="circle-arrow" onClick={() => onPage('timeline')} aria-label="Open timeline"><ArrowRight size={16} /></button>
        </article>
      </div>
    </>
  )
}

function BudgetOverview({ event, onViewBudget, totalEstimated }: { event: EventRecord; onViewBudget: () => void; totalEstimated: number }) {
  const entries = event.expenses.filter((item) => item.estimated_cost > 0)
  const actual = event.expenses.reduce((sum, item) => sum + item.actual_cost, 0)
  const remaining = event.total_budget - actual
  return (
    <article className="card budget-overview-card">
      <div className="card-heading"><div><div className="eyebrow">BUDGET OVERVIEW</div><h3>Plan with peace of mind</h3></div><button className="text-link" onClick={onViewBudget}>See breakdown <ArrowRight size={14} /></button></div>
      <div className="budget-overview-content">
        <div className="donut-wrap">
          <ResponsiveContainer width="100%" height={178}>
            <PieChart>
              <Pie data={entries} dataKey="estimated_cost" nameKey="category" innerRadius={58} outerRadius={79} paddingAngle={3} stroke="none">
                {entries.map((item, index) => <Cell key={item.id} fill={CHART_COLORS[index % CHART_COLORS.length]} />)}
              </Pie>
              <Tooltip formatter={(value) => [currency(Number(value)), 'Estimate']} contentStyle={{ border: '1px solid #eeeaf7', borderRadius: 12, fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
          <div className="donut-center"><strong>{shortCurrency(event.total_budget)}</strong><span>total budget</span></div>
        </div>
        <div className="budget-quick-stats">
          <div><span className="stat-dot planned" /><span>Allocated estimates</span><strong>{shortCurrency(totalEstimated)}</strong></div>
          <div><span className="stat-dot actual" /><span>Actual spend</span><strong>{shortCurrency(actual)}</strong></div>
          <div><span className="stat-dot remaining" /><span>Still available</span><strong>{shortCurrency(remaining)}</strong></div>
          <div className="budget-note"><span><Sparkles size={13} /></span>Estimates help you plan. Confirm prices directly with vendors.</div>
        </div>
      </div>
    </article>
  )
}

function TimelinePreview({ tasks, onViewTimeline, onTaskChange }: { tasks: Task[]; onViewTimeline: () => void; onTaskChange: (task: Task, completed: boolean) => void }) {
  return (
    <article className="card timeline-preview-card">
      <div className="card-heading"><div><div className="eyebrow">UP NEXT</div><h3>Milestones to keep you moving</h3></div><button className="icon-button tiny" onClick={onViewTimeline} aria-label="Open timeline"><ArrowRight size={15} /></button></div>
      {tasks.length === 0 ? <div className="empty-inline">You’re all caught up. <button className="text-link" onClick={onViewTimeline}>View timeline</button></div> : <div className="timeline-preview-list">{tasks.map((task, index) => <button className="preview-task" key={task.id} onClick={() => onTaskChange(task, true)}><span className={`timeline-node node-${index}`}><Circle size={12} /></span><span className="preview-task-copy"><strong>{task.title}</strong><small>{task.description}</small></span><span className={`deadline-badge ${task.deadline && task.deadline < TODAY ? 'late' : ''}`}>{task.deadline ? formatDate(task.deadline, { month: 'short', day: 'numeric' }) : 'No date'}</span></button>)}</div>}
      <button className="button button-subtle full-width" onClick={onViewTimeline}>Open full timeline <ArrowRight size={15} /></button>
    </article>
  )
}

function BudgetPage({ event, onEventChange, onSaveActual }: { event: EventRecord | null; onEventChange: (patch: Record<string, unknown>, success?: string) => void; onSaveActual: (category: string, value: number) => Promise<void> }) {
  const [editingBudget, setEditingBudget] = useState(false)
  const [budgetValue, setBudgetValue] = useState('')
  const [editingCategory, setEditingCategory] = useState<string | null>(null)
  const [actualValue, setActualValue] = useState('')
  if (!event) return <EmptyWorkspace />
  const totalActual = event.expenses.reduce((sum, item) => sum + item.actual_cost, 0)
  const totalAllocated = event.expenses.reduce((sum, item) => sum + item.estimated_cost, 0)
  const remaining = event.total_budget - totalActual
  const consume = event.total_budget > 0 ? Math.min(100, totalActual / event.total_budget * 100) : 0
  return (
    <>
      <PageIntro eyebrow="FINANCIAL CLARITY" title="A budget that feels balanced." text="Keep the big picture in view while tracking each moving piece." action={<button className="button button-secondary" onClick={() => { setBudgetValue(String(event.total_budget)); setEditingBudget(!editingBudget) }}><WalletCards size={16} />Adjust total</button>} />
      <div className="budget-summary-grid">
        <SummaryCard label="Total budget" value={currency(event.total_budget)} detail="Your planning target" icon={WalletCards} tone="violet" />
        <SummaryCard label="Estimated allocation" value={currency(totalAllocated)} detail="Category-by-category plan" icon={Activity} tone="blue" />
        <SummaryCard label="Actual expenditure" value={currency(totalActual)} detail={`${consume.toFixed(1)}% of total budget`} icon={ArrowUpRight} tone="peach" />
        <SummaryCard label="Remaining" value={currency(remaining)} detail={remaining < 0 ? 'Over your current budget' : 'Available to plan with'} icon={CheckCircle2} tone={remaining < 0 ? 'peach' : 'mint'} />
      </div>
      {editingBudget && <form className="inline-edit-card" onSubmit={(eventSubmit) => { eventSubmit.preventDefault(); onEventChange({ total_budget: Number(budgetValue) }, 'Budget updated and estimates rebalanced.'); setEditingBudget(false) }}><div><strong>Set a new total budget</strong><span>Category estimates will be rebalanced proportionally. Actual spend stays unchanged.</span></div><div className="inline-edit-controls"><div className="money-input"><span>₹</span><input type="number" min="0" value={budgetValue} onChange={(eventInput) => setBudgetValue(eventInput.target.value)} required /></div><button className="button button-primary" type="submit">Save budget</button><button className="icon-button" type="button" onClick={() => setEditingBudget(false)} aria-label="Cancel"><X size={17} /></button></div></form>}
      <div className="card budget-detail-card">
        <div className="card-heading"><div><div className="eyebrow">CATEGORY ALLOCATION</div><h3>Where your budget is going</h3><p>Estimates are guidance for planning, not verified quotations.</p></div><span className="estimate-tag"><Sparkles size={13} />PLANORA ESTIMATES</span></div>
        <div className="budget-table-head"><span>CATEGORY</span><span>ESTIMATED</span><span>ACTUAL SPEND</span><span>REMAINING</span><span /></div>
        <div className="budget-table-body">{event.expenses.map((expense, index) => {
          const over = expense.actual_cost > expense.estimated_cost
          const ratio = expense.estimated_cost > 0 ? Math.min(100, expense.actual_cost / expense.estimated_cost * 100) : 0
          return <div className="budget-row" key={expense.id}><div className="category-name"><i style={{ background: CHART_COLORS[index % CHART_COLORS.length] }} /><span><strong>{expense.category}</strong><small>{Math.round(event.total_budget ? expense.estimated_cost / event.total_budget * 100 : 0)}% of total</small></span></div><div className="budget-amount">{currency(expense.estimated_cost)}</div><div className="budget-actual"><span>{currency(expense.actual_cost)}</span><div className="mini-progress"><i className={over ? 'over' : ''} style={{ width: `${ratio}%` }} /></div></div><div className={`budget-remaining ${over ? 'negative' : ''}`}>{currency(expense.estimated_cost - expense.actual_cost)}</div><div className="budget-row-action">{editingCategory === expense.category ? <form className="actual-inline-form" onSubmit={async (eventSubmit) => { eventSubmit.preventDefault(); await onSaveActual(expense.category, Number(actualValue)); setEditingCategory(null) }}><input autoFocus type="number" min="0" value={actualValue} onChange={(eventInput) => setActualValue(eventInput.target.value)} aria-label={`Actual cost for ${expense.category}`} /><button aria-label="Save actual cost"><Check size={15} /></button><button type="button" aria-label="Cancel" onClick={() => setEditingCategory(null)}><X size={15} /></button></form> : <button className="icon-button tiny" onClick={() => { setEditingCategory(expense.category); setActualValue(String(expense.actual_cost)) }} aria-label={`Edit actual cost for ${expense.category}`}><Plus size={15} /></button>}</div></div>
        })}</div>
        <div className="budget-table-footer"><span>Total</span><strong>{currency(totalAllocated)}</strong><strong>{currency(totalActual)}</strong><strong className={remaining < 0 ? 'negative' : ''}>{currency(remaining)}</strong><span /></div>
      </div>
      <div className="card budget-guidance"><div className="guidance-icon"><Lightbulb size={17} /></div><div><strong>Protect a little breathing room.</strong><p>Your contingency category is set aside for small surprises. If you need to trim costs, compare optional upgrades before cutting accessibility or dietary requirements.</p></div><button className="text-link" onClick={() => onEventChange({ special_instructions: `${event.special_instructions || ''} Budget guidance reviewed.`.trim() }, 'Budget note added to your event.')}>Save note <ArrowRight size={14} /></button></div>
    </>
  )
}

function SummaryCard({ label, value, detail, icon: Icon, tone }: { label: string; value: string; detail: string; icon: typeof Activity; tone: string }) {
  return <article className="summary-card"><div className={`summary-icon ${tone}`}><Icon size={17} /></div><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>
}

function TimelinePage({ event, onTaskChange }: { event: EventRecord | null; onTaskChange: (task: Task, completed: boolean) => void }) {
  if (!event) return <EmptyWorkspace />
  const sortedTasks = [...event.tasks].sort((a, b) => (a.deadline || '').localeCompare(b.deadline || ''))
  const completedCount = sortedTasks.filter((task) => task.status === 'completed').length
  const overdueCount = sortedTasks.filter((task) => task.status !== 'completed' && task.deadline && task.deadline < TODAY).length
  const groups = [
    { id: 'overdue', title: 'Needs attention', tasks: sortedTasks.filter((task) => task.status !== 'completed' && task.deadline && task.deadline < TODAY) },
    { id: 'upcoming', title: 'Coming up', tasks: sortedTasks.filter((task) => task.status !== 'completed' && (!task.deadline || task.deadline >= TODAY)) },
    { id: 'completed', title: 'Completed', tasks: sortedTasks.filter((task) => task.status === 'completed') },
  ]
  return (
    <>
      <PageIntro eyebrow="YOUR PLAN, STEP BY STEP" title="Every detail has its moment." text={`${event.title} · ${formatDate(event.event_date)}`} action={<div className="timeline-counter"><strong>{completedCount}<small> / {sortedTasks.length}</small></strong><span>milestones complete</span></div>} />
      <div className="timeline-progress-card"><div className="timeline-progress-heading"><div><span className="eyebrow">PLANNING PROGRESS</span><strong>{Math.round(completedCount * 100 / Math.max(1, sortedTasks.length))}%</strong></div><span className={overdueCount ? 'attention-note' : 'calm-note'}>{overdueCount ? `${overdueCount} deadline${overdueCount > 1 ? 's' : ''} need attention` : 'You’re right on track'}</span></div><div className="progress-track large"><i style={{ width: `${completedCount * 100 / Math.max(1, sortedTasks.length)}%` }} /></div></div>
      {groups.map((group) => <section className="timeline-group" key={group.id}><div className="group-heading"><h3>{group.title}</h3><span>{group.tasks.length}</span></div>{group.tasks.length ? <div className="task-list">{group.tasks.map((task) => <TaskRow key={task.id} task={task} onChange={onTaskChange} />)}</div> : <div className="empty-inline">{group.id === 'overdue' ? 'Nothing overdue. Lovely.' : group.id === 'upcoming' ? 'No open milestones right now.' : 'No completed milestones yet.'}</div>}</section>)}
      <div className="timeline-footnote"><Sparkles size={15} /><span>Deadlines are planned around your event date. Changing the date shifts open milestones with it.</span></div>
    </>
  )
}

function TaskRow({ task, onChange }: { task: Task; onChange: (task: Task, completed: boolean) => void }) {
  const overdue = task.status !== 'completed' && Boolean(task.deadline && task.deadline < TODAY)
  return (
    <article className={`task-row ${task.status === 'completed' ? 'task-complete' : ''}`}>
      <button className={`task-check ${task.status === 'completed' ? 'checked' : ''}`} onClick={() => onChange(task, task.status !== 'completed')} aria-label={task.status === 'completed' ? 'Mark as pending' : 'Mark complete'}>{task.status === 'completed' ? <Check size={14} /> : null}</button>
      <div className="task-row-copy"><strong>{task.title}</strong><p>{task.description}</p>{task.dependencies.length > 0 && <small>Depends on {task.dependencies.join(', ')}</small>}</div>
      <div className="task-row-meta"><span className={`priority-chip priority-${task.priority}`}>{task.priority} priority</span><span className={`task-deadline ${overdue ? 'late' : ''}`}><CalendarDays size={13} />{formatDate(task.deadline, { month: 'short', day: 'numeric' })}{overdue && <em>overdue</em>}</span></div>
    </article>
  )
}

function GuestsPage({
  event,
  onSaveGuest,
  onUpdateGuest,
  onImportGuests,
  onDraftInvitation,
}: {
  event: EventRecord | null
  onSaveGuest: (guest: Record<string, unknown>) => Promise<void>
  onUpdateGuest: (id: string, data: Record<string, unknown>) => Promise<void>
  onImportGuests: (guests: Record<string, unknown>[]) => Promise<void>
  onDraftInvitation: (tone: string, language: string) => Promise<void>
}) {
  const [showForm, setShowForm] = useState(false)
  const [formBusy, setFormBusy] = useState(false)
  const [editingGuest, setEditingGuest] = useState<Guest | null>(null)
  const [guestForm, setGuestForm] = useState({ name: '', contact: '', group_category: 'Family', meal_preference: '', dietary_restrictions: '', accommodation_required: false })
  if (!event) return <EmptyWorkspace />
  const confirmed = event.guests.filter((guest) => guest.rsvp_status === 'confirmed').length
  const pending = event.guests.filter((guest) => guest.rsvp_status === 'pending').length
  const accommodation = event.guests.filter((guest) => guest.accommodation_required).length

  async function submitGuest(eventSubmit: FormEvent) {
    eventSubmit.preventDefault()
    setFormBusy(true)
    try {
      await onSaveGuest(guestForm)
      setGuestForm({ name: '', contact: '', group_category: 'Family', meal_preference: '', dietary_restrictions: '', accommodation_required: false })
      setShowForm(false)
    } finally {
      setFormBusy(false)
    }
  }

  async function importCsv(input: HTMLInputElement) {
    const file = input.files?.[0]
    if (!file) return
    const rows = parseGuestCsv(await file.text())
    input.value = ''
    if (rows.length) await onImportGuests(rows)
  }

  return (
    <>
      <PageIntro eyebrow="THE PEOPLE WHO MAKE IT SPECIAL" title="Your guest list, all together." text="Keep invitations, RSVPs, meals, and stay details in one place." action={<div className="button-stack"><label className="button button-secondary csv-import"><Plus size={15} />Import CSV<input type="file" accept=".csv,text/csv" onChange={(input) => void importCsv(input.currentTarget)} /></label><a className="button button-secondary" href={`/api/events/${event.id}/guests.csv`} download><Download size={15} />Export CSV</a><button className="button button-primary" onClick={() => setShowForm(true)}><Plus size={16} />Add guest</button></div>} />
      <div className="guest-stats-grid"><SummaryCard label="Expected guests" value={String(event.guest_count || '—')} detail="Your current event count" icon={UsersRound} tone="violet" /><SummaryCard label="Confirmed" value={String(confirmed)} detail={`${event.guests.length} records tracked`} icon={CheckCircle2} tone="mint" /><SummaryCard label="Awaiting reply" value={String(pending)} detail="RSVP follow-ups" icon={Clock3} tone="peach" /><SummaryCard label="Need a stay" value={String(accommodation)} detail={`${event.accommodation_count || 0} spaces planned`} icon={Heart} tone="blue" /></div>
      <div className="card guest-list-card">
        <div className="card-heading"><div><div className="eyebrow">GUEST MANAGEMENT</div><h3>Everyone invited</h3><p>Guest details stay in your local Planora workspace.</p></div><button className="button button-subtle" onClick={() => void onDraftInvitation('warm', 'English')}><MessageCircle size={15} />Draft invitation</button></div>
        {showForm && <form className="guest-add-form" onSubmit={submitGuest}><div className="form-row"><label>Guest name<input value={guestForm.name} required onChange={(input) => setGuestForm({ ...guestForm, name: input.target.value })} placeholder="e.g. Priya Sharma" /></label><label>Contact (optional)<input value={guestForm.contact} onChange={(input) => setGuestForm({ ...guestForm, contact: input.target.value })} placeholder="Email or phone" /></label><label>Group<select value={guestForm.group_category} onChange={(input) => setGuestForm({ ...guestForm, group_category: input.target.value })}><option>Family</option><option>Friends</option><option>Colleagues</option><option>Other</option></select></label></div><div className="form-row"><label>Meal preference<input value={guestForm.meal_preference} onChange={(input) => setGuestForm({ ...guestForm, meal_preference: input.target.value })} placeholder="Vegetarian, vegan…" /></label><label>Dietary notes<input value={guestForm.dietary_restrictions} onChange={(input) => setGuestForm({ ...guestForm, dietary_restrictions: input.target.value })} placeholder="Allergies or other needs" /></label><label className="check-label"><input type="checkbox" checked={guestForm.accommodation_required} onChange={(input) => setGuestForm({ ...guestForm, accommodation_required: input.target.checked })} />Needs accommodation</label></div><div className="form-actions"><button type="button" className="button button-quiet" onClick={() => setShowForm(false)}>Cancel</button><button className="button button-primary" disabled={formBusy}>{formBusy ? <LoaderCircle className="spin" size={15} /> : <Plus size={15} />}Save guest</button></div></form>}
        {event.guests.length === 0 ? <EmptyPanel icon={UsersRound} title="Your list starts here" text="Add a guest to track their RSVP, meal preference, and stay needs." action={<button className="button button-secondary" onClick={() => setShowForm(true)}><Plus size={15} />Add your first guest</button>} /> : <div className="table-scroll"><table className="data-table"><thead><tr><th>GUEST</th><th>GROUP</th><th>MEAL</th><th>STAY</th><th>RSVP</th><th /></tr></thead><tbody>{event.guests.map((guest) => <GuestRow guest={guest} key={guest.id} onUpdate={onUpdateGuest} onEdit={() => setEditingGuest(guest)} />)}</tbody></table></div>}
        <div className="privacy-note"><span className="privacy-icon">✳</span><span>Personal details are stored in your local Planora database. Only include information you need for event planning.</span></div>
      </div>
      {editingGuest && <GuestEditModal guest={editingGuest} onClose={() => setEditingGuest(null)} onSave={async (updates) => { await onUpdateGuest(editingGuest.id, updates); setEditingGuest(null) }} />}
    </>
  )
}

function GuestRow({ guest, onUpdate, onEdit }: { guest: Guest; onUpdate: (id: string, data: Record<string, unknown>) => Promise<void>; onEdit: () => void }) {
  return <tr><td><div className="guest-name"><span className="guest-avatar">{guest.name.slice(0, 1).toUpperCase()}</span><span><strong>{guest.name}</strong><small>{guest.contact || guest.dietary_restrictions || 'Guest record'}</small></span></div></td><td><span className="group-pill">{guest.group_category}</span></td><td>{guest.meal_preference || <span className="muted-copy">Not set</span>}</td><td>{guest.accommodation_required ? <span className="stay-pill">Requested</span> : <span className="muted-copy">—</span>}</td><td><select className={`rsvp-select rsvp-${guest.rsvp_status}`} value={guest.rsvp_status} onChange={(input) => void onUpdate(guest.id, { rsvp_status: input.target.value })} aria-label={`RSVP status for ${guest.name}`}><option value="pending">Awaiting reply</option><option value="confirmed">Confirmed</option><option value="declined">Declined</option></select></td><td><button className="icon-button tiny" onClick={onEdit} aria-label={`Edit ${guest.name}`}><Pencil size={13} /></button></td></tr>
}

function GuestEditModal({ guest, onClose, onSave }: { guest: Guest; onClose: () => void; onSave: (updates: Record<string, unknown>) => Promise<void> }) {
  const [form, setForm] = useState({ name: guest.name, contact: guest.contact, group_category: guest.group_category, meal_preference: guest.meal_preference, dietary_restrictions: guest.dietary_restrictions, accommodation_required: guest.accommodation_required, table_name: guest.table_name })
  const [saving, setSaving] = useState(false)
  async function submit(eventSubmit: FormEvent) {
    eventSubmit.preventDefault()
    setSaving(true)
    try { await onSave(form) } finally { setSaving(false) }
  }
  return <Modal title="Edit guest details" subtitle="Keep only the information you need for planning." onClose={onClose}><form className="guest-edit-form" onSubmit={submit}><div className="form-row"><label>Name<input required value={form.name} onChange={(input) => setForm({ ...form, name: input.target.value })} /></label><label>Contact<input value={form.contact} onChange={(input) => setForm({ ...form, contact: input.target.value })} /></label></div><div className="form-row"><label>Group<select value={form.group_category} onChange={(input) => setForm({ ...form, group_category: input.target.value })}><option>Family</option><option>Friends</option><option>Colleagues</option><option>Other</option></select></label><label>Meal preference<input value={form.meal_preference} onChange={(input) => setForm({ ...form, meal_preference: input.target.value })} /></label></div><div className="form-row"><label>Dietary notes<input value={form.dietary_restrictions} onChange={(input) => setForm({ ...form, dietary_restrictions: input.target.value })} /></label><label>Table or group<input value={form.table_name} onChange={(input) => setForm({ ...form, table_name: input.target.value })} /></label></div><label className="check-label"><input type="checkbox" checked={form.accommodation_required} onChange={(input) => setForm({ ...form, accommodation_required: input.target.checked })} />Needs accommodation</label><div className="modal-actions"><button type="button" className="button button-quiet" onClick={onClose}>Cancel</button><button className="button button-primary" disabled={saving}>{saving ? <LoaderCircle className="spin" size={15} /> : <Check size={15} />}Save changes</button></div></form></Modal>
}

function VendorsPage({
  event,
  onSaveVendor,
  selectedVendors,
  setSelectedVendors,
  vendorComparison,
  onCompareVendors,
}: {
  event: EventRecord | null
  onSaveVendor: (vendor: Record<string, unknown>) => Promise<void>
  selectedVendors: string[]
  setSelectedVendors: (ids: string[]) => void
  vendorComparison: Vendor[] | null
  onCompareVendors: () => void
}) {
  const [showForm, setShowForm] = useState(false)
  const [filter, setFilter] = useState('all')
  const [form, setForm] = useState({ name: '', category: 'Venue', location: '', contact: '', price_min: '', price_max: '', rating: '', services: '', notes: '' })
  const [search, setSearch] = useState('')
  if (!event) return <EmptyWorkspace />
  const vendors = event.vendors.filter((vendor) => (filter === 'all' || vendor.category.toLowerCase().includes(filter)) && `${vendor.name} ${vendor.category} ${vendor.location} ${vendor.services}`.toLowerCase().includes(search.toLowerCase()))

  async function submitVendor(eventSubmit: FormEvent) {
    eventSubmit.preventDefault()
    await onSaveVendor({ ...form, price_min: Number(form.price_min || 0), price_max: Number(form.price_max || form.price_min || 0), rating: form.rating ? Number(form.rating) : null })
    setForm({ name: '', category: 'Venue', location: '', contact: '', price_min: '', price_max: '', rating: '', services: '', notes: '' })
    setShowForm(false)
  }

  return (
    <>
      <PageIntro eyebrow="YOUR PEOPLE, YOUR PARTNERS" title="Find the right fit for your day." text="Build a shortlist from records you add. Planora never invents vendor listings or availability." action={<button className="button button-primary" onClick={() => setShowForm(true)}><Plus size={16} />Add vendor</button>} />
      <div className="vendor-source-note"><Store size={16} /><span><strong>Workspace records only</strong> · Vendor details and ratings are user-entered and are not independently verified.</span></div>
      <div className="vendor-toolbar"><div className="vendor-filter-row"><label className="search-field"><Search size={15} /><input value={search} onChange={(input) => setSearch(input.target.value)} placeholder="Search your vendors" /></label><select value={filter} onChange={(input) => setFilter(input.target.value)} aria-label="Filter vendor category"><option value="all">All categories</option><option value="venue">Venues</option><option value="cater">Catering</option><option value="decor">Decorators</option><option value="photo">Photography</option><option value="music">Music & DJs</option></select></div>{selectedVendors.length > 1 && <button className="button button-secondary" onClick={onCompareVendors}>Compare {selectedVendors.length} <ArrowRight size={14} /></button>}</div>
      {showForm && <form className="card vendor-form" onSubmit={submitVendor}><div className="card-heading"><div><div className="eyebrow">ADD A SHORTLIST RECORD</div><h3>Vendor details</h3></div><button type="button" className="icon-button" onClick={() => setShowForm(false)} aria-label="Close form"><X size={17} /></button></div><div className="form-row"><label>Business or contact name<input required value={form.name} onChange={(input) => setForm({ ...form, name: input.target.value })} /></label><label>Category<select value={form.category} onChange={(input) => setForm({ ...form, category: input.target.value })}><option>Venue</option><option>Catering</option><option>Decoration</option><option>Photography</option><option>Videography</option><option>Entertainment</option><option>Makeup</option><option>Transportation</option><option>Accommodation</option><option>Event manager</option></select></label><label>Location<input value={form.location} onChange={(input) => setForm({ ...form, location: input.target.value })} placeholder={event.location} /></label></div><div className="form-row"><label>Price range · from<input type="number" min="0" value={form.price_min} onChange={(input) => setForm({ ...form, price_min: input.target.value })} placeholder="₹" /></label><label>Price range · to<input type="number" min="0" value={form.price_max} onChange={(input) => setForm({ ...form, price_max: input.target.value })} placeholder="₹" /></label><label>Rating, if known<input type="number" min="0" max="5" step="0.1" value={form.rating} onChange={(input) => setForm({ ...form, rating: input.target.value })} placeholder="Optional" /></label><label>Contact detail<input value={form.contact} onChange={(input) => setForm({ ...form, contact: input.target.value })} placeholder="Optional" /></label></div><div className="form-row"><label>Services<input value={form.services} onChange={(input) => setForm({ ...form, services: input.target.value })} placeholder="What they offer" /></label><label>Notes<input value={form.notes} onChange={(input) => setForm({ ...form, notes: input.target.value })} placeholder="Your notes, source, or follow-up" /></label></div><div className="form-actions"><span className="muted-copy">Saved as user-entered, not verified.</span><button type="button" className="button button-quiet" onClick={() => setShowForm(false)}>Cancel</button><button className="button button-primary"><Plus size={15} />Save vendor</button></div></form>}
      {vendorComparison && <div className="card compare-card"><div className="card-heading"><div><div className="eyebrow">SIDE-BY-SIDE</div><h3>Vendor comparison</h3></div><button className="icon-button" onClick={() => setSelectedVendors([])} aria-label="Clear selection"><X size={17} /></button></div><div className="compare-grid">{vendorComparison.map((vendor) => <div key={vendor.id}><strong>{vendor.name}</strong><span>{vendor.category}</span><b>{vendor.price_min || vendor.price_max ? `${currency(vendor.price_min)}–${currency(vendor.price_max)}` : 'No price added'}</b><small>{vendor.rating ? `User-entered rating · ${vendor.rating}/5` : 'No rating entered'}</small></div>)}</div></div>}
      {vendors.length === 0 ? <EmptyPanel icon={Store} title="Your shortlist starts here" text="Add a venue, caterer, or another vendor you’ve found. Planora can then filter and compare those records." action={<button className="button button-secondary" onClick={() => setShowForm(true)}><Plus size={15} />Add a vendor</button>} /> : <div className="vendor-grid">{vendors.map((vendor) => <VendorCard key={vendor.id} vendor={vendor} selected={selectedVendors.includes(vendor.id)} onSelect={(selected) => setSelectedVendors(selected ? [...selectedVendors, vendor.id] : selectedVendors.filter((id) => id !== vendor.id))} />)}</div>}
    </>
  )
}

function VendorCard({ vendor, selected, onSelect }: { vendor: Vendor; selected: boolean; onSelect: (selected: boolean) => void }) {
  return <article className={`card vendor-card ${selected ? 'vendor-selected' : ''}`}><div className="vendor-card-top"><div className="vendor-initial">{vendor.name.slice(0, 1).toUpperCase()}</div><label className="select-vendor"><input type="checkbox" checked={selected} onChange={(input) => onSelect(input.target.checked)} /><span>Compare</span></label></div><div className="vendor-category">{vendor.category}</div><h3>{vendor.name}</h3><div className="vendor-location"><MapPin size={13} />{vendor.location || 'Location not added'}</div><p>{vendor.services || vendor.notes || 'No service notes added yet.'}</p><div className="vendor-card-bottom"><strong>{vendor.price_min || vendor.price_max ? `${currency(vendor.price_min)} – ${currency(vendor.price_max)}` : 'Price not added'}</strong>{vendor.rating ? <span>{vendor.rating} <small>user noted</small></span> : <span className="vendor-unrated">No rating entered</span>}</div><div className="user-entered-label">USER-ENTERED · NOT VERIFIED</div></article>
}

function IdeasPage({ event, onRegenerateIdeas, onChooseIdea }: { event: EventRecord | null; onRegenerateIdeas: (theme: string) => Promise<void>; onChooseIdea: (idea: Idea) => Promise<void> }) {
  const [theme, setTheme] = useState('')
  const [busy, setBusy] = useState(false)
  if (!event) return <EmptyWorkspace />
  const currentEvent = event
  async function regenerate() {
    setBusy(true)
    try { await onRegenerateIdeas(theme || currentEvent.theme) } finally { setBusy(false) }
  }
  return (
    <>
      <PageIntro eyebrow="A LITTLE CREATIVE SPARK" title="Ideas that feel like you." text={`A few creative directions for ${currentEvent.title}, shaped around your preferences and budget.`} action={<button className="button button-secondary" onClick={() => void regenerate()} disabled={busy}>{busy ? <LoaderCircle className="spin" size={15} /> : <WandSparkles size={16} />}Refresh ideas</button>} />
      <div className="ideas-context-card"><div className="ideas-context-icon"><Sparkles size={18} /></div><div><strong>{currentEvent.theme || 'A fresh start'}</strong><span>{currentEvent.guest_count} guests · {currency(currentEvent.total_budget)} budget · {currentEvent.food_preferences || 'food preference not set'}</span></div><label className="search-field idea-theme-input"><Search size={14} /><input value={theme} onChange={(input) => setTheme(input.target.value)} placeholder="Add a mood or theme" onKeyDown={(key) => key.key === 'Enter' && void regenerate()} /></label></div>
      <div className="idea-card-grid">{currentEvent.ideas.map((idea, index) => <IdeaCard key={idea.id} idea={idea} index={index} onChoose={() => void onChooseIdea(idea)} />)}</div>
      <div className="estimate-footnote"><Sparkles size={14} />Concept budgets are directional estimates based on your total budget. Vendor quotations may differ.</div>
    </>
  )
}

function IdeaCard({ idea, index, onChoose }: { idea: Idea; index: number; onChoose: () => void }) {
  return <article className={`card idea-card idea-${index}`}><div className="idea-art"><div className="idea-art-circle" /><span className="idea-spark">✳</span><div className="palette-swatch-row">{idea.palette.map((color) => <i key={color} style={{ backgroundColor: color }} />)}</div><span className="idea-number">0{index + 1}</span></div><div className="idea-card-content"><div className="idea-card-meta"><span>CONCEPT {index + 1}</span><span className="fit-tag">{idea.budget_fit}</span></div><h3>{idea.title}</h3><p>{idea.summary}</p><div className="idea-estimate"><span>Estimated concept cost</span><strong>{currency(idea.estimated_cost)}</strong></div><div className="idea-details"><div><strong>Atmosphere</strong><span>{idea.decoration.slice(0, 2).join(' · ')}</span></div><div><strong>Guest experience</strong><span>{idea.experience.slice(0, 2).join(' · ')}</span></div></div><button className="button button-subtle full-width" onClick={onChoose}>Use this direction <ArrowRight size={14} /></button></div></article>
}

function ReportsPage({ event, onExportReport }: { event: EventRecord | null; onExportReport: () => Promise<void> }) {
  if (!event) return <EmptyWorkspace />
  const actual = event.expenses.reduce((sum, item) => sum + item.actual_cost, 0)
  const progress = event.tasks.length ? Math.round(event.tasks.filter((task) => task.status === 'completed').length / event.tasks.length * 100) : 0
  return <>
    <PageIntro eyebrow="A CLEAR PICTURE, WHEN YOU NEED IT" title="Your event at a glance." text="Shareable summaries help everyone stay aligned as plans come together." action={<button className="button button-primary" onClick={() => void onExportReport()}><Download size={15} />Download report</button>} />
    <div className="report-cover card"><div className="report-cover-copy"><span className="report-label"><FileText size={14} /> EVENT REPORT</span><h2>{event.title}</h2><p>{event.event_type} · {event.location || 'Location to be confirmed'} · {formatDate(event.event_date)}</p><span className="report-generated">Generated just now · Local workspace data</span></div><div className="report-cover-art"><div className="report-arch" /><div className="report-flower">✳</div></div></div>
    <div className="report-stat-grid"><SummaryCard label="Total budget" value={currency(event.total_budget)} detail="Current planning target" icon={WalletCards} tone="violet" /><SummaryCard label="Actual spend" value={currency(actual)} detail="Across tracked categories" icon={Activity} tone="peach" /><SummaryCard label="Planning progress" value={`${progress}%`} detail={`${event.tasks.filter((task) => task.status === 'completed').length} milestones completed`} icon={CheckCheck} tone="mint" /><SummaryCard label="Guest list" value={`${event.guests.length} tracked`} detail={`${event.guest_count} expected guests`} icon={UsersRound} tone="blue" /></div>
    <div className="report-lower-grid"><article className="card report-list-card"><div className="card-heading"><div><div className="eyebrow">BUDGET SNAPSHOT</div><h3>Planned categories</h3></div></div>{event.expenses.slice(0, 6).map((expense, index) => <div className="report-category-row" key={expense.id}><span><i style={{ background: CHART_COLORS[index % CHART_COLORS.length] }} />{expense.category}</span><strong>{currency(expense.estimated_cost)}</strong></div>)}</article><article className="card report-list-card"><div className="card-heading"><div><div className="eyebrow">UPCOMING MILESTONES</div><h3>What’s next</h3></div></div>{event.tasks.filter((task) => task.status !== 'completed').slice(0, 5).map((task) => <div className="report-task-row" key={task.id}><span><Clock3 size={14} />{task.title}</span><strong>{formatDate(task.deadline, { month: 'short', day: 'numeric' })}</strong></div>)}</article></div>
    <div className="privacy-note report-privacy"><span className="privacy-icon">✳</span><span>This report includes local planning estimates and user-entered records. It does not contain verified vendor quotations.</span></div>
  </>
}

function AssistantPanel({
  event,
  messages,
  mode,
  busy,
  draft,
  onDraftChange,
  onSend,
}: {
  event: EventRecord | null
  messages: ChatMessage[]
  mode: AssistantMode
  busy: boolean
  draft: string
  onDraftChange: (value: string) => void
  onSend: (value: string) => void
}) {
  const scrollRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [messages, busy])

  function submitMessage(eventSubmit: FormEvent) {
    eventSubmit.preventDefault()
    onSend(draft)
  }

  const prompts = event
    ? ['What should I do next?', 'Show me three theme ideas', 'How much budget is left?']
    : ['Plan a wedding in Jaipur', 'Plan a birthday for 50 guests', 'Create a corporate event']

  return (
    <aside className="assistant-panel">
      <div className="assistant-header"><div className="assistant-heading"><div className="assistant-avatar"><Sparkles size={17} /></div><div><strong>Planora assistant</strong><span>{event ? `Planning · ${event.event_type}` : 'Ready when you are'}</span></div></div><span className={`assistant-mode ${mode === 'gemini' ? 'connected' : mode === 'gemini-unavailable' ? 'unavailable' : ''}`}><i />{mode === 'gemini' ? 'GEMINI' : mode === 'gemini-unavailable' ? 'RECONNECT' : 'LOCAL MODE'}</span></div>
      <div className="assistant-event-context">{event ? <><span className="context-icon"><CalendarDays size={14} /></span><span><small>WORKING ON</small><strong>{event.title}</strong></span><ChevronDown size={14} /></> : <><span className="context-icon"><Sparkles size={14} /></span><span><small>START WITH A DESCRIPTION</small><strong>I’ll build your first draft.</strong></span></>}</div>
      <div className="chat-scroller" ref={scrollRef}>
        {messages.length === 0 && <div className="assistant-welcome"><div className="welcome-spark"><Sparkles size={20} /></div><p className="welcome-label">YOUR PLANNING PARTNER</p><h3>Hi Keshav,<br />where shall we start?</h3><p>Tell me what you’re planning. I’ll turn the details into a plan, budget, and next steps.</p></div>}
        {messages.slice(-12).map((message) => <div className={`chat-message ${message.role}`} key={message.id}>{message.role === 'assistant' && <div className="chat-avatar"><Sparkles size={12} /></div>}<div className="chat-bubble"><div className="message-content">{message.content}</div>{message.role === 'assistant' && Boolean(message.tool_data?.tool_name) && <div className="tool-status"><CheckCircle2 size={12} />Updated workspace</div>}</div></div>)}
        {busy && <div className="chat-message assistant"><div className="chat-avatar"><Sparkles size={12} /></div><div className="chat-bubble typing-bubble"><i /><i /><i /></div></div>}
      </div>
      {messages.length < 2 && <div className="prompt-suggestions"><span>TRY ASKING</span>{prompts.map((prompt) => <button key={prompt} onClick={() => onSend(prompt)} disabled={busy}>{prompt}<ArrowRight size={12} /></button>)}</div>}
      <form className="assistant-composer" onSubmit={submitMessage}><textarea value={draft} onChange={(input) => onDraftChange(input.target.value)} placeholder={event ? 'Ask me to adjust your plan…' : 'Describe the event you have in mind…'} rows={2} disabled={busy} onKeyDown={(key) => { if (key.key === 'Enter' && !key.shiftKey) { key.preventDefault(); if (draft.trim()) onSend(draft) } }} /><div className="composer-footer"><span><Sparkles size={12} />{mode === 'local' ? 'Local planner · add a Gemini key for AI chat' : 'Thoughtful plans, one step at a time'}</span><button className="send-button" type="submit" disabled={!draft.trim() || busy} aria-label="Send message">{busy ? <LoaderCircle className="spin" size={16} /> : <Send size={15} />}</button></div></form>
      <div className="assistant-safety"><span className="shield-check">✓</span>Nothing is booked or sent without your say-so.</div>
    </aside>
  )
}

function NewEventModal({ onClose, onCreate }: { onClose: () => void; onCreate: (details: Record<string, unknown>, description?: string) => Promise<void> }) {
  const [description, setDescription] = useState('')
  const [form, setForm] = useState({ title: '', event_type: 'Wedding', location: '', event_date: '', duration_days: '1', guest_count: '', total_budget: '', theme: '', food_preferences: '', accommodation_count: '' })
  const [saving, setSaving] = useState(false)
  async function submit(eventSubmit: FormEvent) {
    eventSubmit.preventDefault()
    setSaving(true)
    try {
      const details = {
        ...form,
        title: form.title || undefined,
        duration_days: Number(form.duration_days || 1),
        guest_count: Number(form.guest_count || 0),
        total_budget: Number(form.total_budget || 0),
        accommodation_count: Number(form.accommodation_count || 0),
        accommodation_required: Number(form.accommodation_count || 0) > 0,
      }
      await onCreate(details, description.trim() ? description : undefined)
    } finally {
      setSaving(false)
    }
  }
  return <Modal title="Let’s make this event yours" subtitle="Start with a quick description or add the details you already know." onClose={onClose} wide><form onSubmit={submit} className="new-event-form"><label className="description-field"><span>DESCRIBE YOUR EVENT</span><textarea value={description} onChange={(input) => setDescription(input.target.value)} placeholder="I’m planning a two-day wedding in Jaipur for 300 guests, with a ₹15 lakh budget and vegetarian catering…" rows={3} /></label><div className="form-divider"><span>OR ADD THE DETAILS</span></div><div className="form-row"><label>Event type<select value={form.event_type} onChange={(input) => setForm({ ...form, event_type: input.target.value })}><option>Wedding</option><option>Engagement</option><option>Birthday</option><option>Anniversary</option><option>College festival</option><option>Hackathon</option><option>Corporate event</option><option>Community gathering</option><option>Cultural celebration</option><option>Religious celebration</option><option>Custom event</option></select></label><label>Event name<input value={form.title} onChange={(input) => setForm({ ...form, title: input.target.value })} placeholder="Optional — Planora can name it" /></label><label>Location<input value={form.location} onChange={(input) => setForm({ ...form, location: input.target.value })} placeholder="City or venue" /></label></div><div className="form-row"><label>Event date<input type="date" value={form.event_date} onChange={(input) => setForm({ ...form, event_date: input.target.value })} /></label><label>Guests<input type="number" min="0" value={form.guest_count} onChange={(input) => setForm({ ...form, guest_count: input.target.value })} placeholder="0" /></label><label>Total budget<input type="number" min="0" value={form.total_budget} onChange={(input) => setForm({ ...form, total_budget: input.target.value })} placeholder="₹" /></label><label>Duration<select value={form.duration_days} onChange={(input) => setForm({ ...form, duration_days: input.target.value })}>{[1, 2, 3, 4, 5].map((days) => <option key={days} value={days}>{days} {days === 1 ? 'day' : 'days'}</option>)}</select></label></div><div className="form-row"><label>Theme or mood<input value={form.theme} onChange={(input) => setForm({ ...form, theme: input.target.value })} placeholder="e.g. Royal Rajasthani" /></label><label>Food preferences<input value={form.food_preferences} onChange={(input) => setForm({ ...form, food_preferences: input.target.value })} placeholder="e.g. Vegetarian" /></label><label>Guests needing a stay<input type="number" min="0" value={form.accommodation_count} onChange={(input) => setForm({ ...form, accommodation_count: input.target.value })} placeholder="Optional" /></label></div><div className="modal-actions"><button type="button" className="button button-quiet" onClick={onClose}>Cancel</button><button className="button button-primary" disabled={saving}>{saving ? <LoaderCircle className="spin" size={15} /> : <Sparkles size={15} />}{description.trim() ? 'Build my first draft' : 'Create event workspace'}</button></div></form></Modal>
}

function EventDetailsModal({ event, onClose, onSave }: { event: EventRecord; onClose: () => void; onSave: (updates: Record<string, unknown>) => void }) {
  const [form, setForm] = useState({ title: event.title, event_type: event.event_type, location: event.location, event_date: event.event_date || '', duration_days: String(event.duration_days), guest_count: String(event.guest_count), total_budget: String(event.total_budget), theme: event.theme, food_preferences: event.food_preferences, accommodation_count: String(event.accommodation_count) })
  function submit(eventSubmit: FormEvent) {
    eventSubmit.preventDefault()
    onSave({ ...form, event_date: form.event_date || null, duration_days: Number(form.duration_days || 1), guest_count: Number(form.guest_count || 0), total_budget: Number(form.total_budget || 0), accommodation_count: Number(form.accommodation_count || 0), accommodation_required: Number(form.accommodation_count || 0) > 0 })
  }
  return <Modal title="Event details" subtitle="Change a requirement and Planora will refresh the affected parts of your plan." onClose={onClose} wide><form className="new-event-form" onSubmit={submit}><div className="form-row"><label>Event name<input value={form.title} onChange={(input) => setForm({ ...form, title: input.target.value })} /></label><label>Event type<select value={form.event_type} onChange={(input) => setForm({ ...form, event_type: input.target.value })}>{['Wedding', 'Engagement', 'Birthday', 'Anniversary', 'College festival', 'Hackathon', 'Corporate event', 'Community gathering', 'Cultural celebration', 'Religious celebration', 'Custom event'].map((item) => <option key={item}>{item}</option>)}</select></label><label>Location<input value={form.location} onChange={(input) => setForm({ ...form, location: input.target.value })} /></label></div><div className="form-row"><label>Event date<input type="date" value={form.event_date} onChange={(input) => setForm({ ...form, event_date: input.target.value })} /></label><label>Duration<select value={form.duration_days} onChange={(input) => setForm({ ...form, duration_days: input.target.value })}>{[1, 2, 3, 4, 5].map((days) => <option key={days} value={days}>{days} {days === 1 ? 'day' : 'days'}</option>)}</select></label><label>Guests<input type="number" min="0" value={form.guest_count} onChange={(input) => setForm({ ...form, guest_count: input.target.value })} /></label><label>Total budget<input type="number" min="0" value={form.total_budget} onChange={(input) => setForm({ ...form, total_budget: input.target.value })} /></label></div><div className="form-row"><label>Theme<input value={form.theme} onChange={(input) => setForm({ ...form, theme: input.target.value })} /></label><label>Food preferences<input value={form.food_preferences} onChange={(input) => setForm({ ...form, food_preferences: input.target.value })} /></label><label>Guests needing accommodation<input type="number" min="0" value={form.accommodation_count} onChange={(input) => setForm({ ...form, accommodation_count: input.target.value })} /></label></div><div className="modal-actions"><button type="button" className="button button-quiet" onClick={onClose}>Cancel</button><button className="button button-primary"><Check size={15} />Save event details</button></div></form></Modal>
}

function InviteModal({ draft, onClose, onCopy }: { draft: string; onClose: () => void; onCopy: () => void }) {
  async function copyDraft() {
    await navigator.clipboard?.writeText(draft)
    onCopy()
  }
  return <Modal title="Your invitation draft" subtitle="It’s yours to edit and share when you’re ready. Planora hasn’t sent it." onClose={onClose}><div className="invitation-draft">{draft}</div><div className="modal-actions"><button className="button button-quiet" onClick={onClose}>Close</button><button className="button button-primary" onClick={() => void copyDraft()}><Check size={15} />Copy draft</button></div></Modal>
}

function Modal({ title, subtitle, children, onClose, wide = false }: { title: string; subtitle?: string; children: ReactNode; onClose: () => void; wide?: boolean }) {
  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [onClose])
  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><section className={`modal-card ${wide ? 'modal-wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}><div className="modal-heading"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div><button className="icon-button" onClick={onClose} aria-label="Close dialog"><X size={19} /></button></div>{children}</section></div>
}

function EmptyWorkspace({ onNewEvent }: { onNewEvent?: () => void }) {
  return <div className="empty-workspace"><div className="empty-workspace-art"><div className="empty-sun" /><span>✳</span></div><div className="eyebrow">A FRESH START</div><h1>Your next big day starts here.</h1><p>Create an event and let Planora turn your first ideas into a clear plan, budget, and timeline.</p>{onNewEvent && <button className="button button-primary" onClick={onNewEvent}><Plus size={16} />Create your first event</button>}</div>
}

function EmptyPanel({ icon: Icon, title, text, action }: { icon: typeof Activity; title: string; text: string; action?: ReactNode }) {
  return <div className="empty-panel"><div className="empty-panel-icon"><Icon size={21} /></div><h3>{title}</h3><p>{text}</p>{action}</div>
}

function parseGuestCsv(text: string): Record<string, unknown>[] {
  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let quoted = false
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index]
    if (character === '"' && quoted && text[index + 1] === '"') { field += '"'; index += 1 }
    else if (character === '"') quoted = !quoted
    else if (character === ',' && !quoted) { row.push(field.trim()); field = '' }
    else if ((character === '\n' || character === '\r') && !quoted) {
      if (character === '\r' && text[index + 1] === '\n') index += 1
      row.push(field.trim())
      if (row.some(Boolean)) rows.push(row)
      row = []
      field = ''
    } else field += character
  }
  row.push(field.trim())
  if (row.some(Boolean)) rows.push(row)
  if (rows.length === 0) return []
  const normalize = (value: string) => value.trim().toLowerCase().replace(/[^a-z0-9]/g, '')
  const headerKeys = rows[0].map(normalize)
  const hasHeader = headerKeys.some((value) => ['name', 'guestname', 'contact', 'rsvp', 'group'].includes(value))
  const headers = hasHeader ? headerKeys : ['name', 'contact', 'group', 'rsvp', 'mealpreference', 'dietaryrestrictions', 'accommodationrequired', 'table']
  const dataRows = hasHeader ? rows.slice(1) : rows
  return dataRows.map((cells) => {
    const values = Object.fromEntries(headers.map((header, index) => [header, cells[index] ?? '']))
    const get = (...keys: string[]) => keys.map((key) => values[key]).find((value) => value !== undefined) ?? ''
    const accommodation = String(get('accommodation', 'accommodationrequired', 'stay')).toLowerCase()
    return {
      name: get('name', 'guestname'),
      contact: get('contact', 'email', 'phone'),
      group_category: get('group', 'groupcategory', 'category') || 'Friends',
      rsvp_status: get('rsvp', 'rsvpstatus') || 'pending',
      meal_preference: get('meal', 'mealpreference', 'foodpreference'),
      dietary_restrictions: get('dietaryrestrictions', 'dietarynotes'),
      accommodation_required: ['yes', 'true', '1', 'required'].includes(accommodation),
      table_name: get('table', 'tablename'),
    }
  }).filter((guest) => String(guest.name).trim().length > 0)
}

function downloadBlob(text: string, filename: string, mimeType: string) {
  const url = URL.createObjectURL(new Blob([text], { type: mimeType }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export default App
