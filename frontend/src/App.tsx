import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import {
  Activity, ArrowUpRight, BriefcaseBusiness, Bug,
  CheckCircle2, ChevronDown, CircleHelp, Clock3, FileCheck2, FlaskConical,
  LayoutDashboard, ListChecks, Menu, Plus, Search, Settings2, ShieldCheck,
  Sparkles, X,
} from 'lucide-react'
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

type DashboardData = {
  total: number
  passed: number
  failed: number
  blocked: number
  recentExecutions: Array<{ id: string; status: string; createdAt: string; durationMs?: number }>
}

type Job = {
  id: string
  title: string
  company: string
  location: string
  type: string
  description: string
  isDemo: boolean
}

type StudentApplication = {
  id: string
  job: { id: string; title: string; company: string }
  status: string
  createdAt: string
}

type Applicant = {
  id: string
  student: { id: string; name: string; email: string }
  status: string
  createdAt: string
}

type TestCase = {
  id: string
  title: string
  scenario: string
  expectedResult: string
  priority: 'High' | 'Medium' | 'Low'
  approved: boolean
  isExample: boolean
}
type User = { id: string; name: string; email: string; role: 'student' | 'recruiter' }

const API_URL = import.meta.env.VITE_API_URL || ''
const TOKEN_KEY = 'hiretest-token'
const navItems = [
  { id: 'command', label: 'Command Center', icon: LayoutDashboard },
  { id: 'jobs', label: 'HireTest Jobs', icon: BriefcaseBusiness },
  { id: 'cases', label: 'Test cases', icon: ListChecks },
  { id: 'executions', label: 'Executions', icon: Activity },
  { id: 'bugs', label: 'Bug reports', icon: Bug },
] as const

type PageId = typeof navItems[number]['id']

function App() {
  const [page, setPage] = useState<PageId>('command')
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [jobs, setJobs] = useState<Job[]>([])
  const [myApplications, setMyApplications] = useState<StudentApplication[]>([])
  const [applicants, setApplicants] = useState<Applicant[]>([])
  const [applicantsForJob, setApplicantsForJob] = useState('')
  const [cases, setCases] = useState<TestCase[]>([])
  const [requirement, setRequirement] = useState('')
  const [connection, setConnection] = useState<'checking' | 'connected' | 'offline'>('checking')
  const [loadingJobs, setLoadingJobs] = useState(false)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [jobSearch, setJobSearch] = useState('')
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || '')
  const [user, setUser] = useState<User | null>(null)
  const [authChecking, setAuthChecking] = useState(Boolean(localStorage.getItem(TOKEN_KEY)))

  async function loadDashboard() {
    try {
      const response = await fetch(`${API_URL}/api/dashboard`, { headers: { Authorization: `Bearer ${token}` } })
      const body = await response.json()
      if (!response.ok) throw new Error(body.error || 'Backend unavailable')
      setDashboard(body)
      setConnection('connected')
    } catch {
      setDashboard(null)
      setConnection('offline')
    }
  }

  async function loadJobs(search = jobSearch) {
    setLoadingJobs(true)
    try {
      const query = search.trim() ? `?search=${encodeURIComponent(search.trim())}` : ''
      const response = await fetch(`${API_URL}/api/jobs${query}`)
      const body = await response.json()
      if (!response.ok) throw new Error(body.error || 'Could not load jobs.')
      setJobs(body.jobs)
      setConnection('connected')
      setNotice('')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not load jobs.')
      setConnection('offline')
    } finally {
      setLoadingJobs(false)
    }
  }

  async function loadMyApplications(authToken = token) {
    const response = await fetch(`${API_URL}/api/my-applications`, {
      headers: { Authorization: `Bearer ${authToken}` },
    })
    const body = await response.json()
    if (!response.ok) throw new Error(body.error || 'Could not load your applications.')
    setMyApplications(body.applications)
  }

  async function loadApplicants(jobId: string) {
    setNotice('')
    try {
      const response = await fetch(`${API_URL}/api/jobs/${jobId}/applications`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      const body = await response.json()
      if (!response.ok) throw new Error(body.error || 'Could not load applicants.')
      setApplicants(body.applications)
      setApplicantsForJob(jobId)
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not load applicants.')
    }
  }

  async function updateApplicationStatus(applicationId: string, status: string) {
    setNotice('')
    try {
      const response = await fetch(`${API_URL}/api/applications/${applicationId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ status }),
      })
      const body = await response.json()
      if (!response.ok) throw new Error(body.error || 'Could not update application.')
      setApplicants((current) => current.map((applicant) => (
        applicant.id === applicationId ? { ...applicant, status: body.application.status } : applicant
      )))
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not update application.')
    }
  }

  useEffect(() => {
    if (!token) {
      setAuthChecking(false)
      return
    }
    Promise.all([
      fetch(`${API_URL}/api/auth/me`, { headers: { Authorization: `Bearer ${token}` } }),
      fetch(`${API_URL}/api/test-cases`, { headers: { Authorization: `Bearer ${token}` } }),
    ]).then(async ([meResponse, casesResponse]) => {
      if (!meResponse.ok) throw new Error('Your session has expired. Please sign in again.')
      const meBody = await meResponse.json()
      setUser(meBody.user)
      if (casesResponse.ok) setCases((await casesResponse.json()).testCases)
      if (meBody.user.role === 'student') await loadMyApplications()
      await loadDashboard()
    }).catch((error: unknown) => {
      localStorage.removeItem(TOKEN_KEY)
      setToken('')
      setUser(null)
      setNotice(error instanceof Error ? error.message : 'Could not restore your sign-in.')
      setConnection('offline')
    }).finally(() => setAuthChecking(false))
  }, [])

  useEffect(() => {
    if (page === 'jobs') void loadJobs()
  }, [page])

  async function generateCases(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!requirement.trim()) return
    setBusy(true)
    setNotice('')
    try {
      const response = await fetch(`${API_URL}/api/test-cases/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ requirement }),
      })
      const body = await response.json()
      if (!response.ok) throw new Error(body.error || 'Could not generate test cases.')
      setCases((previous) => [...body.testCases, ...previous])
      setRequirement('')
      setPage('cases')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not generate test cases.')
    } finally {
      setBusy(false)
    }
  }

  async function createDemoJob(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const formData = new FormData(form)
    setBusy(true)
    setNotice('')
    try {
      const response = await fetch(`${API_URL}/api/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          title: formData.get('title'),
          company: formData.get('company'),
          location: formData.get('location'),
          description: formData.get('description'),
          type: 'Full time',
        }),
      })
      const body = await response.json()
      if (!response.ok) throw new Error(body.error || 'Could not create job.')
      form.reset()
      await loadJobs()
      setNotice('Job posted successfully.')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not create job.')
    } finally {
      setBusy(false)
    }
  }

  const passedPercent = dashboard?.total
    ? Math.round((dashboard.passed / dashboard.total) * 100)
    : 0

  async function submitAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const formData = new FormData(event.currentTarget)
    const isRegister = formData.get('mode') === 'register'
    setBusy(true)
    setNotice('')
    try {
      const response = await fetch(`${API_URL}/api/auth/${isRegister ? 'register' : 'login'}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: formData.get('name'),
          email: formData.get('email'),
          password: formData.get('password'),
          role: formData.get('role'),
        }),
      })
      const body = await response.json()
      if (!response.ok) throw new Error(body.error || 'Could not sign in.')
      localStorage.setItem(TOKEN_KEY, body.token)
      setToken(body.token)
      setUser(body.user)
      setDashboard(null)
      const [dashboardResponse, casesResponse] = await Promise.all([
        fetch(`${API_URL}/api/dashboard`, { headers: { Authorization: `Bearer ${body.token}` } }),
        fetch(`${API_URL}/api/test-cases`, { headers: { Authorization: `Bearer ${body.token}` } }),
      ])
      if (dashboardResponse.ok) setDashboard(await dashboardResponse.json())
      if (casesResponse.ok) setCases((await casesResponse.json()).testCases)
      if (body.user.role === 'student') await loadMyApplications(body.token)
      setConnection('connected')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not sign in.')
    } finally {
      setBusy(false)
      setAuthChecking(false)
    }
  }

  async function applyToJob(jobId: string) {
    setNotice('')
    try {
      const response = await fetch(`${API_URL}/api/jobs/${jobId}/applications`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
      const body = await response.json()
      if (!response.ok) throw new Error(body.error || 'Could not submit application.')
      setNotice('Your application was submitted.')
      await loadMyApplications()
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not submit application.')
    }
  }

  function signOut() {
    localStorage.removeItem(TOKEN_KEY)
    setToken('')
    setUser(null)
    setDashboard(null)
    setCases([])
    setNotice('')
  }

  if (authChecking) return <div className="auth-loading">Loading your workspace…</div>
  if (!user) return <AuthPage onSubmit={submitAuth} busy={busy} notice={notice} clearNotice={() => setNotice('')} />

  return (
    <div className="app-shell">
      {sidebarOpen && <button className="mobile-backdrop" aria-label="Close menu" onClick={() => setSidebarOpen(false)} />}
      <aside className={`sidebar ${sidebarOpen ? 'sidebar-open' : ''}`}>
        <div className="brand-row">
          <div className="brand-mark"><ShieldCheck size={19} /></div>
          <span>hiretest<span className="brand-ai">ai</span></span>
          <button className="mobile-close" onClick={() => setSidebarOpen(false)} aria-label="Close navigation"><X size={18} /></button>
        </div>
        <div className="workspace-picker">
          <div className="workspace-avatar">H</div>
          <div className="workspace-copy"><strong>HireTest Workspace</strong><span>Personal workspace</span></div>
          <ChevronDown size={15} />
        </div>
        <p className="nav-caption">WORKSPACE</p>
        <nav className="primary-nav" aria-label="Main navigation">
          {navItems.map(({ id, label, icon: Icon }) => (
            <button key={id} className={`nav-item ${page === id ? 'nav-active' : ''}`} onClick={() => { setPage(id); setSidebarOpen(false) }}>
              <Icon size={18} strokeWidth={1.8} /><span>{label}</span>
              {id === 'bugs' && dashboard?.failed ? <span className="nav-badge">{dashboard.failed}</span> : null}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="help-card">
            <div className="help-icon"><CircleHelp size={17} /></div>
            <strong>Need a hand?</strong>
            <p>Explore your testing workspace and run your first check.</p>
            <button onClick={() => setPage('cases')}>View test cases <span>→</span></button>
          </div>
          <button className="nav-item settings-item" onClick={() => setNotice('Workspace settings are coming in a later development phase.')}><Settings2 size={18} /><span>Settings</span></button>
          <div className="user-profile">
            <div className="user-avatar">{user.name.slice(0, 1).toUpperCase()}</div>
            <div className="workspace-copy"><strong>{user.name}</strong><span>{user.role} account</span></div>
            <button className="more-button" aria-label="Sign out" onClick={signOut}>↗</button>
          </div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumb"><button className="menu-button" aria-label="Open menu" onClick={() => setSidebarOpen(true)}><Menu size={19} /></button><span>Workspace</span><span className="crumb-slash">/</span><strong>{navItems.find((item) => item.id === page)?.label}</strong></div>
          <div className="topbar-right">
            <span className={`connection-pill connection-${connection}`}><i />{connection === 'connected' ? 'Backend connected' : connection === 'checking' ? 'Connecting…' : 'Backend unavailable'}</span>
            <button className="help-button" aria-label="Help" onClick={() => setNotice('HireTest AI is being built phase by phase. Check README for setup details.')}><CircleHelp size={18} /></button>
          </div>
        </header>

        <div className="page-content">
          {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Dismiss message"><X size={16} /></button></div>}
          {page === 'command' && <CommandCenter dashboard={dashboard} passedPercent={passedPercent} onNavigate={setPage} />}
          {page === 'jobs' && <JobsPage jobs={jobs} search={jobSearch} setSearch={setJobSearch} onSearch={() => void loadJobs()} loading={loadingJobs} onCreate={createDemoJob} onApply={applyToJob} busy={busy} user={user} myApplications={myApplications} applicants={applicants} applicantsForJob={applicantsForJob} onViewApplicants={loadApplicants} onUpdateApplication={updateApplicationStatus} />}
          {page === 'cases' && <CasesPage cases={cases} requirement={requirement} setRequirement={setRequirement} onGenerate={generateCases} busy={busy} />}
          {page === 'executions' && <EmptyPage title="Test executions" icon={<Activity size={20} />} description="Execution history will appear here after the Playwright worker is configured." />}
          {page === 'bugs' && <EmptyPage title="Bug reports" icon={<Bug size={20} />} description="Failed assertions will create bug reports in a later phase. No results are fabricated." />}
        </div>
      </main>
    </div>
  )
}

function AuthPage({ onSubmit, busy, notice, clearNotice }: { onSubmit: (event: FormEvent<HTMLFormElement>) => void; busy: boolean; notice: string; clearNotice: () => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('register')
  return (
    <main className="auth-shell">
      <section className="auth-brand-panel">
        <div className="brand-row"><div className="brand-mark"><ShieldCheck size={19} /></div><span>hiretest<span className="brand-ai">ai</span></span></div>
        <div className="auth-brand-copy"><p className="eyebrow">TEST WITH CONFIDENCE</p><h1>Find issues before<br />your users do.</h1><p>Explore the job portal, create test cases, and build confidence with real browser checks.</p></div>
        <span className="auth-brand-foot">AI-POWERED SOFTWARE TESTING PLATFORM</span>
      </section>
      <section className="auth-panel"><div className="auth-box">
        <p className="eyebrow">{mode === 'register' ? 'GET STARTED' : 'WELCOME BACK'}</p>
        <h2>{mode === 'register' ? 'Create your workspace' : 'Sign in to HireTest AI'}</h2>
        <p className="auth-subtitle">Create a tester account to save test cases and executions.</p>
        <div className="auth-tabs"><button className={mode === 'login' ? 'active' : ''} onClick={() => { clearNotice(); setMode('login') }}>Sign in</button><button className={mode === 'register' ? 'active' : ''} onClick={() => { clearNotice(); setMode('register') }}>Create account</button></div>
        <form className="auth-form" onSubmit={onSubmit}>
          <input type="hidden" name="mode" value={mode} />
          {mode === 'register' && <label>Your name<input name="name" autoComplete="name" maxLength={80} placeholder="Alex Morgan" required /></label>}
          <label>Email address<input name="email" type="email" autoComplete="email" maxLength={254} placeholder="you@example.com" required /></label>
          <label>Password<input name="password" type="password" autoComplete={mode === 'register' ? 'new-password' : 'current-password'} minLength={mode === 'register' ? 8 : 1} maxLength={128} placeholder={mode === 'register' ? 'At least 8 characters' : 'Your password'} required /></label>
          {mode === 'register' && <label>Account type<select name="role"><option value="student">Student / Tester</option><option value="recruiter">Recruiter</option></select></label>}
          {notice && <p className="auth-error" role="alert">{notice}</p>}
          <button className="button button-primary auth-submit" disabled={busy}>{busy ? 'Please wait…' : mode === 'register' ? 'Create account' : 'Sign in'} <span>→</span></button>
        </form>
        <p className="auth-privacy">Your password is securely hashed and never stored as plain text.</p>
      </div></section>
    </main>
  )
}

function CommandCenter({ dashboard, passedPercent, onNavigate }: { dashboard: DashboardData | null; passedPercent: number; onNavigate: (page: PageId) => void }) {
  const metrics = [
    { label: 'Test cases', value: dashboard?.total ?? '—', note: dashboard ? 'Saved in workspace' : 'Connect backend', icon: FileCheck2, tone: 'violet', change: 'Actual saved cases' },
    { label: 'Passed', value: dashboard?.passed ?? '—', note: dashboard ? 'From real runs' : 'No run data', icon: CheckCircle2, tone: 'green', change: dashboard?.total ? `${passedPercent}% pass rate` : 'Run tests to measure' },
    { label: 'Failed', value: dashboard?.failed ?? '—', note: dashboard ? 'From real assertions' : 'No run data', icon: Bug, tone: 'red', change: 'Failures only, not errors' },
    { label: 'Blocked / errors', value: dashboard?.blocked ?? '—', note: dashboard ? 'Environment or setup' : 'No run data', icon: Clock3, tone: 'amber', change: 'Not counted as failures' },
  ]
  const history = dashboard?.recentExecutions?.map((execution, index) => ({
    label: new Date(execution.createdAt).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
    value: index + 1,
  })) ?? []

  return (
    <>
      <section className="welcome-row">
        <div><p className="eyebrow">AI TESTING COMMAND CENTER</p><h1>Good afternoon, <em>tester.</em></h1><p className="welcome-subtitle">Plan, run, and understand your software tests from one place.</p></div>
        <button className="button button-primary" onClick={() => onNavigate('cases')}><Plus size={17} /> Generate test cases</button>
      </section>
      <section className="metric-grid" aria-label="Testing metrics">
        {metrics.map(({ label, value, note, icon: Icon, tone, change }) => (
          <article className="metric-card" key={label}>
            <div className={`metric-icon metric-${tone}`}><Icon size={18} /></div>
            <div className="metric-heading"><span>{label}</span><button aria-label={`${label} information`} title={change}><CircleHelp size={15} /></button></div>
            <strong className="metric-value">{value}</strong>
            <div className="metric-foot"><span>{note}</span><span className={tone === 'green' ? 'positive-note' : ''}>{change}</span></div>
          </article>
        ))}
      </section>
      <section className="dashboard-grid">
        <article className="panel trend-panel">
          <div className="panel-heading"><div><h2>Execution activity</h2><p>History is populated from actual test runs.</p></div><button className="text-button" onClick={() => onNavigate('executions')}>View history <span>→</span></button></div>
          {history.length ? (
            <div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><AreaChart data={history} margin={{ top: 10, right: 12, left: -20, bottom: 0 }}><defs><linearGradient id="activityFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#6958e8" stopOpacity={0.22} /><stop offset="95%" stopColor="#6958e8" stopOpacity={0} /></linearGradient></defs><CartesianGrid stroke="#edf0f5" vertical={false} /><XAxis dataKey="label" axisLine={false} tickLine={false} tick={{ fill: '#9299a8', fontSize: 11 }} /><YAxis allowDecimals={false} axisLine={false} tickLine={false} tick={{ fill: '#9299a8', fontSize: 11 }} /><Tooltip /><Area type="monotone" dataKey="value" stroke="#6958e8" strokeWidth={2.5} fill="url(#activityFill)" /></AreaChart></ResponsiveContainer></div>
          ) : <div className="chart-empty"><div className="chart-placeholder"><Activity size={22} /></div><strong>No execution history yet</strong><span>Run a real Playwright suite to populate this chart.</span></div>}
        </article>
        <article className="panel quick-panel">
          <div className="panel-heading"><div><h2>Quick start</h2><p>Build your first end-to-end testing workflow.</p></div><Sparkles size={18} className="sparkle" /></div>
          <div className="quick-steps">
            <button onClick={() => onNavigate('jobs')}><span className="step-num">01</span><span><strong>Explore HireTest Jobs</strong><small>The job portal is the application under test.</small></span><span className="step-arrow">↗</span></button>
            <button onClick={() => onNavigate('cases')}><span className="step-num">02</span><span><strong>Generate test cases</strong><small>Describe a requirement in plain English.</small></span><span className="step-arrow">↗</span></button>
            <button onClick={() => onNavigate('executions')}><span className="step-num">03</span><span><strong>Run browser tests</strong><small>Only actual Playwright results are shown.</small></span><span className="step-arrow">↗</span></button>
          </div>
        </article>
      </section>
      <section className="panel recent-panel">
        <div className="panel-heading"><div><h2>Recent test executions</h2><p>Latest activity recorded by your test runner.</p></div><button className="text-button" onClick={() => onNavigate('executions')}>All executions <span>→</span></button></div>
        {dashboard?.recentExecutions?.length ? <div className="execution-list">{dashboard.recentExecutions.slice(0, 5).map((run) => <div className="execution-row" key={run.id}><span className={`status-dot status-${run.status.toLowerCase()}`} /><strong>{run.id}</strong><span>{run.status}</span><span>{new Date(run.createdAt).toLocaleString()}</span></div>)}</div> : <div className="table-empty"><div className="empty-icon"><FlaskConical size={20} /></div><div><strong>{dashboard ? 'Your test history will show here' : 'Connect the backend to load real test data'}</strong><span>Test counts and results are never pre-filled.</span></div><button className="button button-secondary" onClick={() => onNavigate('cases')}>View test cases</button></div>}
      </section>
    </>
  )
}

function JobsPage({ jobs, search, setSearch, onSearch, loading, onCreate, onApply, busy, user, myApplications, applicants, applicantsForJob, onViewApplicants, onUpdateApplication }: { jobs: Job[]; search: string; setSearch: (value: string) => void; onSearch: () => void; loading: boolean; onCreate: (event: FormEvent<HTMLFormElement>) => void; onApply: (jobId: string) => void; busy: boolean; user: User; myApplications: StudentApplication[]; applicants: Applicant[]; applicantsForJob: string; onViewApplicants: (jobId: string) => void; onUpdateApplication: (applicationId: string, status: string) => void }) {
  return (
    <>
      <section className="welcome-row">
        <div><p className="eyebrow">APPLICATION UNDER TEST</p><h1>HireTest <em>Jobs.</em></h1><p className="welcome-subtitle">Browse listings and explore the job application workflow. Demo listings are fictional and cannot accept applications.</p></div>
        <span className="aut-badge"><span /> LIVE APPLICATION</span>
      </section>
      <section className="jobs-toolbar panel"><div className="search-field"><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') onSearch() }} placeholder="Search role, company, or location" aria-label="Search jobs" /><button onClick={onSearch}>Search</button></div><button className="button button-secondary"><ChevronDown size={15} /> All job types</button></section>
      <div className="jobs-layout">
        <section className="job-results">
          <div className="section-title"><h2>Open roles</h2><span>{jobs.length} listed</span></div>
          {loading ? <div className="panel table-empty">Loading job listings…</div> : jobs.length ? jobs.map((job) => {
            const application = myApplications.find((item) => item.job.id === job.id)
            return <div key={job.id}>
              <article className="panel job-card"><div className="company-mark">{job.company.slice(0, 1).toUpperCase()}</div><div className="job-copy"><div className="job-title-row"><h3>{job.title}</h3><span className="job-type">{job.type}</span>{job.isDemo && <span className="demo-label">DEMO ONLY</span>}</div><p>{job.company} <span>·</span> {job.location}</p><small>{job.description}</small></div>{user.role === 'student' ? <button className="button button-secondary" disabled={Boolean(application) || job.isDemo} title={job.isDemo ? 'Sample listings cannot accept applications.' : undefined} onClick={() => onApply(job.id)}>{job.isDemo ? 'Sample only' : application ? `Applied · ${application.status}` : 'Apply'}</button> : <button className="button button-secondary" disabled={job.isDemo} onClick={() => onViewApplicants(job.id)}>{job.isDemo ? 'Sample only' : 'View applicants'}</button>}</article>
              {user.role === 'recruiter' && applicantsForJob === job.id && <section className="panel applicant-list"><h3>Applicants for {job.title}</h3>{applicants.length ? applicants.map((applicant) => <div className="applicant-row" key={applicant.id}><div><strong>{applicant.student.name}</strong><span>{applicant.student.email}</span></div><select aria-label={`Status for ${applicant.student.name}`} value={applicant.status} onChange={(event) => onUpdateApplication(applicant.id, event.target.value)}><option value="submitted">Submitted</option><option value="reviewing">Reviewing</option><option value="shortlisted">Shortlisted</option><option value="rejected">Rejected</option><option value="hired">Hired</option></select></div>) : <p>No applications have been submitted for this role yet.</p>}</section>}
            </div>
          }) : <div className="panel job-empty"><div className="empty-icon"><BriefcaseBusiness size={20} /></div><strong>No jobs found</strong><span>Job listings come from the configured database. Add a real listing below.</span></div>}
        </section>
        {user.role === 'student' && <section className="panel my-applications"><div className="panel-heading"><div><h2>My applications</h2><p>Current status of your submitted applications.</p></div><span>{myApplications.length}</span></div>{myApplications.length ? myApplications.map((application) => <div className="applicant-row" key={application.id}><div><strong>{application.job.title}</strong><span>{application.job.company}</span></div><span className="job-type">{application.status}</span></div>) : <p>You have not applied to any jobs yet.</p>}</section>}
        <aside className="panel job-create-panel"><div className="panel-heading"><div><h2>Recruiter quick post</h2><p>Job publishing requires a recruiter account.</p></div></div>{user.role === 'recruiter' ? <form className="quick-form" onSubmit={onCreate}><label>Job title<input required name="title" maxLength={120} placeholder="e.g. QA Engineer" /></label><label>Company<input required name="company" maxLength={120} placeholder="Your company" /></label><label>Location<input required name="location" maxLength={120} placeholder="City or remote" /></label><label>Description<textarea required name="description" maxLength={5000} rows={3} placeholder="What will this person do?" /></label><button className="button button-primary" disabled={busy}><Plus size={16} /> {busy ? 'Saving…' : 'Create job posting'}</button></form> : <div className="role-note"><BriefcaseBusiness size={18} /><p>Sign in with a recruiter account to publish job listings. Student applicants can browse listings.</p></div>}</aside>
      </div>
    </>
  )
}

function CasesPage({ cases, requirement, setRequirement, onGenerate, busy }: { cases: TestCase[]; requirement: string; setRequirement: (value: string) => void; onGenerate: (event: React.FormEvent<HTMLFormElement>) => void; busy: boolean }) {
  return (
    <>
      <section className="welcome-row"><div><p className="eyebrow">SAFE TEST DESIGN</p><h1>Test case <em>generator.</em></h1><p className="welcome-subtitle">Turn a plain-English requirement into reviewable test scenarios.</p></div><span className="aut-badge"><Sparkles size={14} /> RULE-BASED FALLBACK</span></section>
      <section className="panel generator-panel"><div className="generator-icon"><Sparkles size={20} /></div><div className="generator-copy"><h2>Describe what should work</h2><p>Test cases are structured data, not executable generated code. AI integration can be configured later.</p><form className="generator-form" onSubmit={onGenerate}><textarea value={requirement} onChange={(event) => setRequirement(event.target.value)} placeholder="Example: Students can sign in using a valid email address and password." rows={3} required /><button className="button button-primary" disabled={busy}><Sparkles size={16} /> {busy ? 'Generating…' : 'Generate test cases'}</button></form></div></section>
      <section className="panel case-list-panel"><div className="panel-heading"><div><h2>Generated test cases</h2><p>{cases.length} in your workspace · review before execution</p></div><button className="button button-secondary" disabled={!cases.length}>Select all</button></div>{cases.length ? <div className="case-list">{cases.map((testCase) => <article className="case-card" key={testCase.id}><div className="case-check"><input type="checkbox" aria-label={`Select ${testCase.title}`} /></div><div className="case-main"><div className="case-meta"><span className="case-id">{testCase.id}</span><span className={`priority-pill priority-${testCase.priority.toLowerCase()}`}>{testCase.priority}</span><span className="case-type">{testCase.isExample ? 'Starter example' : 'Functional'}</span></div><h3>{testCase.title}</h3><p>{testCase.scenario}</p><div className="expected"><strong>Expected result</strong><span>{testCase.expectedResult}</span></div></div><button className={`approval-badge ${testCase.approved ? 'approved' : ''}`}>{testCase.approved ? 'Approved' : 'Review'}</button></article>)}</div> : <div className="job-empty"><div className="empty-icon"><ListChecks size={20} /></div><strong>No test cases yet</strong><span>Starter examples will appear here. Generate more from a requirement above.</span></div>}</section>
    </>
  )
}

function EmptyPage({ title, icon, description }: { title: string; icon: ReactNode; description: string }) {
  return <section className="empty-page panel"><div className="metric-icon metric-violet">{icon}</div><p className="eyebrow">HIRETEST AI</p><h1>{title}</h1><p>{description}</p><div className="phase-label"><ArrowUpRight size={16} /> Under active development</div></section>
}

export default App
