import { useEffect, useState } from 'react';
import { Activity, ArrowRight, CheckCircle2, Download, MapPin, RefreshCw, ShieldCheck, AlertTriangle,
  LayoutDashboard, ChartNoAxesCombined, Truck, SlidersHorizontal, Users, Clock3, Layers,
  Droplets, Package, HeartPulse, Search, BookOpen, ArrowUpRight, LoaderCircle, X, ChevronRight, HeartHandshake } from 'lucide-react';
import { MapContainer, TileLayer, CircleMarker, Popup, Tooltip, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import './review.css';
import LocationEditor from './LocationEditor';
import FundsPanel from './FundsPanel';

const API = import.meta.env.VITE_API_BASE_URL || '';
const DEFAULTS = { disaster_type: 'Wildfire', severity: 'High', duration_hours: 72,
  scenario_name: 'Example disaster response', locations: [],
  food_supply: 40000, water_supply: 40000, med_supply: 2500, minimum_service_fraction: 0.25,
  area_populations: { 'Area A': 1850, 'Area B': 2900, 'Area C': 3300, 'Area D': 4300, 'Area E': 3200, 'Area F': 3800, 'Area G': 2429 } };
const RESOURCES = { Food: ['Food', 'rations'], Water: ['Water', 'litres'], Medical_Kit: ['Medical kits', 'kits'] };
const CUSTOM_DEMO = { ...DEFAULTS, scenario_name: 'Andhra flood — synthetic demo', disaster_type: 'Flood',
  area_populations: {}, food_supply: 15000, water_supply: 15000, med_supply: 900,
  locations: [
    { location_id: 'loc_demo_vijayawada', name: 'Vijayawada', latitude: 16.5062, longitude: 80.648,
      population: 6000, affected_population: 2400, children_population: 1100, elderly_population: 600,
      population_density: 6500, minor_damage: 180, major_damage: 260, destroyed_buildings: 90, magnitude: 7 },
    { location_id: 'loc_demo_guntur', name: 'Guntur', latitude: 16.3067, longitude: 80.4365,
      population: 4500, affected_population: 1500, children_population: 850, elderly_population: 400,
      population_density: 4500, minor_damage: 160, major_damage: 85, destroyed_buildings: 25, magnitude: 5 },
    { location_id: 'loc_demo_tenali', name: 'Tenali', latitude: 16.239, longitude: 80.645,
      population: 3800, affected_population: 1200, children_population: 720, elderly_population: 360,
      population_density: 3800, minor_damage: 140, major_damage: 70, destroyed_buildings: 20, magnitude: 5 },
    { location_id: 'loc_demo_mangalagiri', name: 'Mangalagiri', latitude: 16.4308, longitude: 80.5682,
      population: 4200, affected_population: 1800, children_population: 800, elderly_population: 420,
      population_density: 4200, minor_damage: 170, major_damage: 130, destroyed_buildings: 45, magnitude: 6 },
    { location_id: 'loc_demo_amaravati', name: 'Amaravati', latitude: 16.5745, longitude: 80.3575,
      population: 3200, affected_population: 1400, children_population: 600, elderly_population: 340,
      population_density: 2600, minor_damage: 120, major_damage: 100, destroyed_buildings: 35, magnitude: 6 },
    { location_id: 'loc_demo_machilipatnam', name: 'Machilipatnam', latitude: 16.1875, longitude: 81.1389,
      population: 5000, affected_population: 2100, children_population: 950, elderly_population: 500,
      population_density: 5000, minor_damage: 200, major_damage: 180, destroyed_buildings: 60, magnitude: 7 },
  ] };
const COLORS = { CRITICAL: '#dc2626', HIGH: '#c2410c', MEDIUM: '#946200', LOW: '#087f5b' };
const RESOURCE_ICONS = { Food: Package, Water: Droplets, Medical_Kit: HeartPulse };
const STAGES = ['PLANNED', 'APPROVED', 'DISPATCHED', 'DELIVERED'];
const WORKFLOW = [
  { label: 'Describe', detail: 'Locations & available supplies', icon: LayoutDashboard },
  { label: 'AI analysis', detail: 'Assess risk & resource needs', icon: ChartNoAxesCombined },
  { label: 'Response plan', detail: 'Review & track dispatches', icon: Truck },
  { label: 'What-if & audit', detail: 'Test changes & view records', icon: SlidersHorizontal },
  { label: 'Donations & funds', detail: 'Track support & fund usage', icon: HeartHandshake },
];
const fmt = value => Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 1 });
const canonical = value => JSON.stringify(value, (key, item) => item && typeof item === 'object' && !Array.isArray(item)
  ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b))) : item);
const normalizeConfig = config => ({ ...structuredClone(DEFAULTS), ...config, locations: config.locations || [] });
const missingSampleLocations = config => CUSTOM_DEMO.locations.slice(2).filter(sample =>
  !config.locations.some(location => location.location_id === sample.location_id || location.name.trim().toLowerCase() === sample.name.toLowerCase())
  && !Object.keys(config.area_populations).some(name => name.trim().toLowerCase() === sample.name.toLowerCase()));
function savedDraft() {
  try {
    const draft = JSON.parse(localStorage.getItem('reliefplan-scenario-draft'));
    if (!draft || !Array.isArray(draft.locations) || !draft.area_populations || typeof draft.area_populations !== 'object') return null;
    const config = normalizeConfig(draft);
    const originalDemo = config.scenario_name === CUSTOM_DEMO.scenario_name
      && config.locations.some(location => location.location_id === 'loc_demo_vijayawada')
      && config.locations.some(location => location.location_id === 'loc_demo_guntur');
    if (originalDemo && !localStorage.getItem('reliefplan-six-location-demo-updated')) {
      // Upgrade the original two-place draft once; subsequent removals remain intentional.
      if (config.locations.length === 2) config.locations.push(...structuredClone(missingSampleLocations(config)));
      try {
        localStorage.setItem('reliefplan-scenario-draft', JSON.stringify(config));
        localStorage.setItem('reliefplan-six-location-demo-updated', '1');
      } catch { /* Keep the restored draft available when storage is full. */ }
    }
    return config;
  } catch { return null; }
}

async function request(path, body) {
  const response = await fetch(`${API}/api${path}`, body === undefined ? undefined : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!response.ok) {
    const json = await response.json().catch(() => ({}));
    const labels = { scenario_name: 'Scenario name', name: 'Place name', latitude: 'Latitude', longitude: 'Longitude',
      population: 'Resident population', affected_population: 'Affected population', food_supply: 'Food stock',
      water_supply: 'Water stock', med_supply: 'Medical stock', duration_hours: 'Response duration',
      children_population: 'Children', elderly_population: 'Elderly residents', population_density: 'Population density',
      amount: 'Amount', party: 'Donor / paid to', donation_status: 'Donation status', reference: 'Reference',
      note: 'Note', reason: 'Correction reason', payment_method: 'Payment method', category: 'Category',
      plan_id: 'Saved scenario', area_id: 'Affected area' };
    throw new Error(Array.isArray(json.detail) ? json.detail.map(detail => {
      const path = (detail.loc || []).filter(key => key !== 'body');
      const field = path.at(-1);
      const label = labels[field] || (typeof field === 'string' ? field.replaceAll('_', ' ') : 'Scenario');
      const location = path[0] === 'locations' && Number.isInteger(path[1]) ? `Location ${path[1] + 1} · ` : '';
      return `${location}${label}: ${detail.msg.replace(/^Value error, /, '')}`;
    }).join('; ') : json.detail || `Request failed (${response.status})`);
  }
  return response.json();
}

function MapBounds({ areas, selected }) {
  const map = useMap();
  useEffect(() => {
    if (selected) map.flyTo([selected.latitude, selected.longitude], 12, { duration: 0.5 });
    else if (areas.length) map.fitBounds(areas.map(a => [a.latitude, a.longitude]), { padding: [35, 35], maxZoom: 12 });
  }, [map, areas, selected]);
  return null;
}

function ResourceTable({ data }) {
  return <div className="table-scroll"><table className="review-table"><thead><tr><th>Resource</th><th>Demand</th><th>Available</th><th>Allocated</th><th>Unmet need</th><th>Coverage</th><th>Service floor</th></tr></thead>
    <tbody>{Object.entries(data.resources).map(([key, r]) => <tr key={key}><th>{RESOURCES[key][0]} <small>{RESOURCES[key][1]}</small></th>
      <td>{fmt(r.demand)}</td><td>{fmt(r.supply)}</td><td>{fmt(r.allocated)}</td><td>{fmt(r.shortage)}</td><td>{r.coverage_pct}%</td><td>{r.service_floor_pct}%</td></tr>)}</tbody></table></div>;
}

function CoverageCards({ data }) {
  return <section className="resource-overview" aria-label="Resource coverage">{Object.entries(data.resources).map(([key, resource]) => {
    const Icon = RESOURCE_ICONS[key];
    return <article className={`resource-tile resource-${key}`} key={key}>
      <div className="resource-title"><span className="resource-icon"><Icon size={19} /></span><h3>{RESOURCES[key][0]}</h3><span className="unit-label">{RESOURCES[key][1]}</span></div>
      <div className="resource-tile-body"><div><strong>{fmt(resource.allocated)}</strong><p>of {fmt(resource.demand)} needed</p></div><div className="coverage-ring" style={{ '--coverage': `${Math.min(100, resource.coverage_pct)}%` }}><span>{resource.coverage_pct}%<small>covered</small></span></div></div>
      <div className={`resource-note ${resource.shortage > 0 ? 'needs-stock' : ''}`}>{resource.shortage > 0 ? <AlertTriangle size={13} /> : <CheckCircle2 size={13} />}{resource.shortage > 0 ? `${fmt(resource.shortage)} ${RESOURCES[key][1]} still needed` : 'Demand fully covered'}</div>
    </article>;
  })}</section>;
}

export default function ReviewApp() {
  const [config, setConfig] = useState(() => savedDraft() || structuredClone(DEFAULTS));
  const [hasDraft] = useState(() => Boolean(savedDraft()));
  const [scenarios, setScenarios] = useState([]);
  const [scenarioId, setScenarioId] = useState('');
  const [step, setStep] = useState(1);
  const [data, setData] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [health, setHealth] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [selectedId, setSelectedId] = useState(null);
  const [explanation, setExplanation] = useState(null);
  const [shock, setShock] = useState({ shock_water_pct: -30, shock_pop_pct: 0 });
  const [simulation, setSimulation] = useState(null);
  const [audit, setAudit] = useState([]);
  const [mapOffline, setMapOffline] = useState(false);
  const [actionQuery, setActionQuery] = useState('');
  const [actionFilter, setActionFilter] = useState('ALL');
  const dirty = data && canonical(config) !== canonical(data.inputs);
  const selected = data?.areas.find(a => a.area_id === selectedId);
  const population = Object.values(config.area_populations).reduce((a, b) => a + Number(b || 0), 0) + config.locations.reduce((sum, location) => sum + location.population, 0);
  const locationCount = Object.keys(config.area_populations).length + config.locations.length;
  const getActionStatus = action => data.dispatch_statuses?.[action.action_id] || (data.approved_actions.includes(action.action_id) ? 'APPROVED' : 'PLANNED');
  const filteredActions = data?.actions.filter(action => (actionFilter === 'ALL' || getActionStatus(action) === actionFilter)
    && `${action.area_name} ${RESOURCES[action.resource][0]}`.toLowerCase().includes(actionQuery.toLowerCase().trim())) || [];

  useEffect(() => { window.scrollTo({ top: 0, left: 0 }); }, [step, error]);

  useEffect(() => {
    try { localStorage.setItem('reliefplan-scenario-draft', JSON.stringify(config)); } catch { /* Server-saved plans remain available when browser storage is full. */ }
  }, [config]);

  useEffect(() => {
    let active = true;
    Promise.all([request('/health'), request('/plans/latest'), request('/metrics'), request('/plans')]).then(([status, last, scores, plans]) => {
      if (!active) return;
      setHealth(status); setMetrics(scores);
      setScenarios(plans);
      if (last) { const inputs = normalizeConfig(last.inputs); setData({ ...last, inputs }); if (!hasDraft) setConfig(inputs); }
    }).catch(err => active && setError(`Cannot connect to the project: ${err.message}. Start it with START_PROJECT.cmd.`));
    return () => { active = false; };
  }, [hasDraft]);

  const update = (key, value) => { setConfig(current => ({ ...current, [key]: value })); setNotice(''); };
  const refreshAudit = async () => setAudit(await request('/audit'));
  async function analyze(nextStep = 2) {
    setBusy(true); setError(''); setNotice('');
    try {
      const inputs = { ...config, scenario_name: String(config.scenario_name ?? '').trim() || `${config.disaster_type} response` };
      const result = await request('/analyze', inputs);
      setData(result); setConfig(result.inputs); setSelectedId(null); setExplanation(null); setSimulation(null); setStep(nextStep);
      setActionQuery(''); setActionFilter('ALL');
      setScenarios(await request('/plans'));
      setNotice(`Plan ${result.plan_id.slice(0, 8)} saved. All displayed results use the current inputs.`);
      if (nextStep === 4) await refreshAudit();
      return true;
    } catch (err) { setError(err.message); return false; }
    finally { setBusy(false); }
  }
  async function navigate(next) {
    if (next === 5) { setStep(5); return; }
    if (next === 1) { setStep(1); return; }
    if (!data || dirty) { await analyze(next); return; }
    setStep(next);
    if (next === 4) refreshAudit().catch(err => setError(err.message));
  }
  async function operate(work) {
    setBusy(true); setError(''); setNotice('');
    try { await work(); } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  const bulletin = data ? `Planning exercise: ${data.inputs.disaster_type} response. Estimated residents needing assistance: ${fmt(data.overview.total_affected)}. Water demand coverage: ${data.resources.Water.coverage_pct}%. Locally saved project bulletin; not an official public alert.` : '';

  return <div className="review-app">
    <a href="#main-content" className="skip-link">Skip to workspace</a>
    <aside className="workspace-sidebar"><div className="sidebar-brand"><span className="brand-symbol"><Activity size={24} /></span><div><strong>ReliefPlan<span>AI</span></strong><small>Emergency decision support</small></div></div>
      <p className="nav-caption">RESPONSE WORKFLOW</p><nav className="workflow" aria-label="Project workflow">{WORKFLOW.map(({ label, detail, icon: Icon }, index) =>
        <button key={label} aria-label={`${index + 1} ${label}`} aria-current={step === index + 1 ? 'step' : undefined} disabled={busy} className={`${step === index + 1 ? 'active' : ''} ${data && step > index + 1 ? 'complete' : ''}`} onClick={() => navigate(index + 1)}>
          <span className="workflow-icon"><Icon size={19} /></span><span className="workflow-copy"><strong>{label}</strong><small>{detail}</small></span><span className="workflow-number">{data && step > index + 1 ? <CheckCircle2 size={15} /> : `0${index + 1}`}</span></button>)}</nav>
      <div className="sidebar-scenario"><span className="nav-caption">CURRENT SCENARIO</span><strong>{config.scenario_name || `${config.disaster_type} response`}</strong><p><MapPin size={13} /> {locationCount} locations <span>·</span> {config.duration_hours} hours</p><small><span className="status-dot" />{dirty || !data ? 'Draft · ready to edit' : 'Plan saved locally'}</small></div>
      <div className="sidebar-footer"><ShieldCheck size={18} /><div><strong>Built for informed decisions</strong><p>Synthetic training data.<br />Human review comes first.</p></div></div>
    </aside>
    <div className="workspace-content"><header className="top-nav"><div className="workspace-breadcrumb"><span>Response workspace</span><ChevronRight size={14} /><strong>{WORKFLOW[step - 1].label}</strong></div>
      <div className="header-actions"><span className={`connection ${health?.model_ready ? 'ready' : ''}`}><span className="status-dot" />{health?.model_ready ? 'System ready' : 'Connecting…'}</span>
        <details className="quick-guide"><summary><BookOpen size={16} /><span>Quick guide</span></summary><div><strong>Your relief workspace</strong><ol><li>Add affected places and available supplies, or load the demo.</li><li>Run analysis and inspect risk, coverage and shortages.</li><li>Review allocations and record dispatch stages locally.</li><li>Test a supply shock and revisit saved decisions.</li><li>Track received donations, pledges and expenses in Donations & funds.</li></ol></div></details></div></header>
    <div className="page-body" id="main-content" aria-busy={busy}>
    {error && <div className="error-banner" role="alert"><AlertTriangle size={18} /><span>{error}</span><button onClick={() => setError('')}>Dismiss</button></div>}
    {notice && <div className="review-notice" role="status"><CheckCircle2 size={17} /><span>{notice}</span><button className="icon-button" aria-label="Dismiss notification" onClick={() => setNotice('')}><X size={15} /></button></div>}
    {busy && <p className="busy-message" role="status"><LoaderCircle size={18} className="spin" /> Processing your plan. This may take a moment…</p>}
    {dirty && step !== 1 && step !== 5 && <div className="review-notice">Inputs changed. Run analysis to refresh this plan.<button onClick={() => analyze(step)} disabled={busy}>Refresh plan</button></div>}

    {step === 1 && <main>
      <div className="page-intro"><span className="eyebrow">01 / SCENARIO SETUP</span><h1>Every location. One clear plan.</h1><p>Describe the situation, add affected places, and decide how to use the supplies you have.</p></div>
      <section className="scenario-overview" aria-label="Scenario summary"><div><span className="overview-icon"><MapPin size={20} /></span><p>Locations included<strong>{locationCount}<small>{config.locations.length} custom places</small></strong></p></div><div><span className="overview-icon"><Users size={20} /></span><p>Resident population<strong>{fmt(population)}<small>across selected locations</small></strong></p></div><div><span className="overview-icon"><Clock3 size={20} /></span><p>Planning window<strong>{config.duration_hours}<small>hours of assistance</small></strong></p></div></section>
      <section className="glass-panel scenario-library"><div className="section-row"><div><h3><Layers size={18} /> Your scenario</h3><p className="helper">Start fresh, try the demo, or continue a saved plan.</p></div><span className="soft-badge">Draft autosaved in this browser</span></div><div className="review-grid scenario-controls"><label className="field-label">Scenario name<input maxLength="100" placeholder="Optional — a name is generated if blank" aria-describedby="scenario-name-help" value={config.scenario_name} onChange={e => update('scenario_name', e.target.value)} /></label>
        <label className="field-label">Reopen a saved scenario<select value={scenarioId} onChange={e => setScenarioId(e.target.value)}><option value="">Choose a saved plan</option>{scenarios.map(plan => <option key={plan.plan_id} value={plan.plan_id}>{plan.scenario_name} · {plan.location_count} locations · {new Date(plan.created_at).toLocaleString()}</option>)}</select></label></div>
        <div className="inline-actions wrap"><button className="btn-secondary" disabled={busy || !scenarioId} onClick={() => operate(async () => { const plan = await request(`/plans/${scenarioId}`); const inputs = normalizeConfig(plan.inputs); setData({ ...plan, inputs }); setConfig(inputs); setSelectedId(null); setExplanation(null); setSimulation(null); setNotice('Saved scenario reopened, including custom locations and dispatch records.'); })}>Open saved scenario</button>
        <button className="btn-demo" disabled={busy} onClick={() => { setConfig(structuredClone(CUSTOM_DEMO)); setNotice('Six locations are ready: Vijayawada, Guntur, Tenali, Mangalagiri, Amaravati and Machilipatnam. Observations are synthetic and editable. Run analysis when you are ready.'); }}><Activity size={16} />Load custom-location demo<ArrowUpRight size={15} /></button></div>
        <p className="helper" id="scenario-name-help">Scenario name is optional. Leave it blank to use “{config.disaster_type} response”. Draft inputs are saved in this browser; each successful analysis is saved in the local project database.</p></section>
      <div className="review-grid setup-grid"><section className="glass-panel"><div className="section-row"><h3><SlidersHorizontal size={18} /> Disaster parameters</h3><span className="soft-badge">Planning assumptions</span></div>
        <label className="field-label">Disaster type<select value={config.disaster_type} onChange={e => update('disaster_type', e.target.value)}>{['Flood', 'Earthquake', 'Cyclone', 'Wildfire'].map(v => <option key={v}>{v}</option>)}</select></label>
        <label className="field-label">Planning severity<select value={config.severity} onChange={e => update('severity', e.target.value)}>{['Low', 'Moderate', 'High', 'Extreme'].map(v => <option key={v}>{v}</option>)}</select></label>
        <label className="field-label">Response duration in hours<input type="number" min="1" max="720" value={config.duration_hours} onChange={e => update('duration_hours', Number(e.target.value))} /></label>
        <label className="field-label">Requested minimum service<input type="range" min="0" max="50" step="5" value={config.minimum_service_fraction * 100} onChange={e => update('minimum_service_fraction', Number(e.target.value) / 100)} /><strong>{config.minimum_service_fraction * 100}% of each area's demand</strong></label>
        <p className="helper">Severity scales estimated need; the model still predicts from the observed damage features. If stock cannot support the service floor, the same feasible fraction is reserved for every area.</p>
      </section><section className="glass-panel"><h3><Package size={18} /> Available stock</h3><p className="helper">Enter the total available for this scenario. Zero stock is supported.</p>
        {[['food_supply', 'Food in rations', Package, 'rations'], ['water_supply', 'Water in litres', Droplets, 'litres'], ['med_supply', 'Medical kits', HeartPulse, 'kits']].map(([key, label, Icon, unit]) => <label className="field-label stock-field" key={key}><span><Icon size={15} />{label}</span><div className="input-with-unit"><input type="number" min="0" max="1000000000" value={config[key]} onChange={e => update(key, Number(e.target.value))} /><span aria-hidden="true">{unit}</span></div></label>)}
        <p className="helper">These quantities are used by the optimizer and split across the supplied warehouses. Zero supply is supported.</p>
        <div className="assumption-note"><ShieldCheck size={20} /><p>Use example data or enter observations for your own locations. The prediction model was trained on synthetic data.</p></div>
      </section></div>
      <LocationEditor config={config} update={update} disabled={busy} sampleCount={missingSampleLocations(config).length}
        onAddSamples={() => {
          const additions = missingSampleLocations(config);
          update('locations', [...config.locations, ...structuredClone(additions)]);
          setNotice(`${additions.length} sample locations added. Your existing locations and settings are preserved. Sample observations are synthetic and editable. Run analysis to update the plan.`);
        }} />
      <details className="glass-panel population-panel"><summary><span><MapPin size={17} />Example study areas</span><span className="soft-badge">{Object.keys(config.area_populations).length} included</span></summary><div className="details-body">
        <p className="helper">Remove the Houston examples to create a scenario containing only your own locations.</p>
        <div className="population-grid">{Object.entries(config.area_populations).map(([area, value]) => <div key={area}><label className="field-label">{area}<input type="number" min="0" max="10000000" value={value} onChange={e => update('area_populations', { ...config.area_populations, [area]: Number(e.target.value) })} /></label><button className="btn-secondary" onClick={() => { const areas = { ...config.area_populations }; delete areas[area]; update('area_populations', areas); }}>Remove {area}</button></div>)}</div>
        <div className="inline-actions wrap"><button className="btn-secondary" onClick={() => update('area_populations', {})}>Remove all example areas</button><button className="btn-secondary" onClick={() => update('area_populations', { ...DEFAULTS.area_populations })}>Restore example areas</button></div>
      </div></details>
      <div className="nav-actions-row sticky-actions"><div><strong>{locationCount} locations ready for analysis</strong><p>Your plan will use the inputs above.</p></div><div className="inline-actions"><button className="btn-secondary" disabled={busy} onClick={() => { setConfig(structuredClone(DEFAULTS)); setNotice('Example inputs restored. Run analysis to compute a new plan.'); }}>Reset example inputs</button>
        <button className="btn-primary" disabled={busy} onClick={() => analyze()}>{busy ? <LoaderCircle size={16} className="spin" /> : <Activity size={16} />}{busy ? 'Analyzing…' : 'Run AI analysis'}<ArrowRight size={16} /></button></div></div>
    </main>}

    {step === 2 && data && <main>
      <div className="page-intro"><span className="eyebrow">02 / ASSESSMENT</span><h1>AI risk and resource analysis</h1><p>{data.inputs.scenario_name} · {data.inputs.disaster_type} · {data.inputs.severity} planning severity · {data.inputs.duration_hours} hours · plan {data.plan_id.slice(0, 8)}</p></div>
      <div className="stats-row">{[['Residents needing aid', fmt(data.overview.total_affected), `${fmt(data.overview.total_population)} total residents`], ['Critical / high priority', `${data.overview.critical_areas} / ${data.overview.high_areas}`, `${data.areas.length} study areas`], ['Water coverage', `${data.resources.Water.coverage_pct}%`, `${fmt(data.resources.Water.supply)} litres available`], ['Allocation status', data.overview.solver_status, `${data.overview.execution_time_ms} ms solver time`]].map(([label, value, note]) => <div className="stat-card" key={label}><span className="stat-label">{label}</span><strong className="stat-num">{value}</strong><span className="stat-sub">{note}</span></div>)}</div>
      <CoverageCards data={data} />
      <div className="review-grid map-grid"><section className="glass-panel"><h3><MapPin size={17} /> Geographical risk map</h3><div className="review-map"><MapContainer center={[29.76, -95.36]} zoom={11} style={{ height: 410, width: '100%' }}>
        <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' eventHandlers={{ tileerror: () => setMapOffline(true) }} />
        <MapBounds areas={data.areas} selected={selected} />{data.areas.map(area => <CircleMarker key={area.area_id} center={[area.latitude, area.longitude]} radius={selectedId === area.area_id ? 15 : 11} pathOptions={{ color: COLORS[area.priority_level], fillOpacity: 0.8 }} eventHandlers={{ click: () => { setSelectedId(area.area_id); setExplanation(null); } }}>
          <Tooltip permanent direction="top">{area.area_name}</Tooltip><Popup><strong>{area.area_name}</strong><p>{area.priority_level} priority · {fmt(area.estimated_affected)} needing aid</p><p>Water allocation: {fmt(area.allocation.Water)} L</p></Popup></CircleMarker>)}</MapContainer></div>
        <div className="map-tools"><button className="btn-secondary" onClick={() => setSelectedId(null)}>Show all locations</button><div className="map-legend">{Object.entries(COLORS).map(([level, color]) => <span key={level}><i style={{ background: color }} />{level.toLowerCase()}</span>)}</div></div><p className="helper">{mapOffline ? 'Basemap unavailable: internet is needed for map tiles. Coordinates, area selection and analysis remain available.' : 'Select a marker or ranking row to inspect an area. Basemap tiles require internet.'}</p>
      </section><section className="glass-panel"><h3>Area priority ranking</h3><p className="helper">Select a location to explore its predicted damage and allocation priority.</p><div className="rank-list">{data.areas.map((area, index) => <button key={area.area_id} className={selectedId === area.area_id ? 'selected' : ''} aria-pressed={selectedId === area.area_id} onClick={() => { setSelectedId(area.area_id); setExplanation(null); }}><span className="rank-main"><span className="rank-index">{String(index + 1).padStart(2, '0')}</span><span><strong>{area.area_name}</strong><small>{fmt(area.estimated_affected)} needing aid · damage {area.predicted_severity}</small></span></span><span><b className="priority-badge" data-level={area.priority_level}>{area.priority_level}</b><small>{area.priority_score.toFixed(4)} priority</small></span></button>)}</div>{selected && <button className="btn-secondary inspect-area" onClick={() => document.getElementById('area-explanation')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>Inspect {selected.area_name}<ArrowRight size={14} /></button>}<p className="helper">Priority is relative within this scenario.</p></section></div>
      <section className="glass-panel"><div className="section-row"><h3>Demand, allocation and remaining need</h3><a className="btn-secondary" href={`${API}/api/plans/${data.plan_id}/export.csv`}><Download size={15} /> Export plan CSV</a></div><ResourceTable data={data} />
        <div className="coverage-bars">{Object.entries(data.resources).map(([key, r]) => <div key={key}><span>{RESOURCES[key][0]} <strong>{r.coverage_pct}% covered</strong></span><div className="bar-track"><div style={{ width: `${r.coverage_pct}%` }} /></div></div>)}</div>
      </section>
      <section className="glass-panel"><h3>Location coverage and replenishment alerts</h3><p className="helper">Unmet need is the extra stock required to fully cover the current plan. Rows below the requested service target are highlighted.</p>
        <div className="table-scroll"><table className="review-table"><thead><tr><th>Location</th><th>Source / affected count</th><th>Resource</th><th>Coverage</th><th>Additional stock needed</th><th>Alert</th></tr></thead><tbody>{data.areas.flatMap(area => Object.keys(RESOURCES).map(resource => {
          const coverage = area.demand[resource] ? 100 * area.allocation[resource] / area.demand[resource] : 100;
          const below = coverage + 0.01 < data.inputs.minimum_service_fraction * 100;
          return <tr key={`${area.area_id}-${resource}`} className={below ? 'shortage-alert' : ''}><th>{area.area_name}</th><td>{area.input_source || 'Synthetic example'}<small>{area.affected_source || 'Model-based estimate'}</small></td><td>{RESOURCES[resource][0]}</td><td>{coverage.toFixed(1)}%</td><td>{fmt(area.shortage[resource])} {RESOURCES[resource][1]}</td><td>{below ? 'Below service target' : area.shortage[resource] > 0 ? 'Replenishment needed' : 'Covered'}</td></tr>;
        }))}</tbody></table></div>
      </section>
      {data.strategy_comparison && <details className="glass-panel"><summary><span><ChartNoAxesCombined size={18} />Allocation strategy comparison</span><span className="soft-badge">3 strategies</span></summary><div className="details-body"><p className="helper">All methods use the same stock and demand. The optimizer maximizes priority-weighted satisfaction subject to its service floor. Proportional allocation gives equal percentage coverage; equal quantities redistributes unused shares. Total shortage can be identical while distribution differs.</p>
        <div className="table-scroll"><table className="review-table"><thead><tr><th>Resource</th><th>Strategy</th><th>Allocated</th><th>Unmet need</th><th>Lowest area coverage</th><th>Priority-weighted coverage</th></tr></thead><tbody>{data.strategy_comparison.map(row => <tr key={`${row.resource}-${row.strategy}`}><th>{RESOURCES[row.resource][0]}</th><td>{row.strategy}</td><td>{fmt(row.allocated)}</td><td>{fmt(row.shortage)}</td><td>{row.minimum_coverage_pct}%</td><td>{row.priority_weighted_coverage_pct}%</td></tr>)}</tbody></table></div></div></details>}
      {data.input_warnings?.length > 0 && <section className="glass-panel"><h3>Prediction input checks</h3>{data.input_warnings.map(warning => <p key={warning.area_id}><strong>{warning.area_name}:</strong> {warning.message}<br /><span className="helper">Outside range: {warning.features.join(', ')}</span></p>)}</section>}
      {selected && <section className="glass-panel" id="area-explanation"><div className="section-row"><div><h3>{selected.area_name} explanation</h3><p>Predicted damage: <strong>{selected.predicted_severity}</strong> · model confidence {(selected.prediction_confidence * 100).toFixed(1)}%</p></div>
        <button disabled={busy} className="btn-secondary" onClick={() => operate(async () => setExplanation(await request(`/explain/${data.plan_id}/${selected.area_id}`)))}>Explain prediction</button></div>
        <p className="helper">Priority combines normalized impact, demand, shortage proxy, vulnerable population and road obstruction. It is separate from predicted damage.</p>
        <p className="helper">Priority components are relative to this scenario. Custom locations have no surveyed road network, so no road obstruction penalty is assumed.</p>
        <div className="priority-components">{Object.entries(selected.priority_components).map(([key, value]) => <span key={key}>{key.replaceAll('_', ' ')} <strong>{value.toFixed(4)}</strong></span>)}</div>
        {explanation && <><div className="table-scroll"><table className="review-table"><thead><tr><th>Feature</th><th>Observed value</th><th>SHAP contribution</th><th>Effect on predicted class</th></tr></thead><tbody>{explanation.contributions.map(c => <tr key={c.feature}><td>{c.feature}</td><td>{fmt(c.feature_value)}</td><td>{c.shap_value.toFixed(4)}</td><td>{c.effect}</td></tr>)}</tbody></table></div><p className="helper">{explanation.disclaimer}</p></>}
      </section>}
      {metrics && <details className="glass-panel"><summary><span><ShieldCheck size={18} />Saved model evaluation</span><span className="soft-badge">{metrics.metadata.best_model_name}</span></summary><div className="details-body"><p className="helper">{metrics.metadata.training_samples_total} synthetic examples · {metrics.metadata.test_set_size} held-out test records · selected model {metrics.metadata.best_model_name}. These are saved evaluation results, not live accuracy measurements.</p>
        <div className="table-scroll"><table className="review-table"><thead><tr><th>Model</th><th>Test accuracy</th><th>Test macro F1</th><th>5-fold macro F1</th></tr></thead><tbody>{Object.entries(metrics.models).map(([name, m]) => <tr key={name}><th>{name.replaceAll('_', ' ')}</th><td>{(m.accuracy * 100).toFixed(2)}%</td><td>{m.f1_macro.toFixed(4)}</td><td>{m.cv_5fold_f1_macro_mean.toFixed(4)}</td></tr>)}</tbody></table></div></div></details>}
      <div className="nav-actions-row"><button className="btn-secondary" onClick={() => navigate(1)}>Edit scenario</button><button className="btn-primary" onClick={() => navigate(3)}>Review response plan <ArrowRight size={16} /></button></div>
    </main>}

    {step === 3 && data && <main><div className="page-intro"><span className="eyebrow">03 / RESPONSE</span><h1>Review the resource plan</h1><p>Find a recommendation, review its allocation, and record dispatch progress locally.</p></div>
      <details className="glass-panel"><summary><span><ShieldCheck size={18} />Allocation policy & stock summary</span><span className="soft-badge">{data.inputs.minimum_service_fraction * 100}% requested floor</span></summary><div className="details-body"><p>A shared service fraction is reserved first; remaining stock maximizes priority-weighted demand satisfaction. Requested floor: {data.inputs.minimum_service_fraction * 100}%. Feasible floors are shown per resource.</p><ResourceTable data={data} /><p className="helper">Track Planned → Approved → Dispatched → Delivered using local operator confirmations. This records your inputs; it does not contact vehicles or verify delivery. Stock is a scenario assumption, not a shared warehouse inventory.</p></div></details>
      <div className="dispatch-overview">{STAGES.map(status => <button key={status} aria-pressed={actionFilter === status} className={actionFilter === status ? 'selected' : ''} onClick={() => setActionFilter(current => current === status ? 'ALL' : status)}><span className={`stage-dot stage-${status}`} /><span>{status.toLowerCase()}<strong>{data.actions.filter(action => getActionStatus(action) === status).length}</strong></span></button>)}</div>
      <div className="response-toolbar"><label className="search-field"><Search size={17} /><input type="search" aria-label="Search response cards" placeholder="Search by location or resource…" value={actionQuery} onChange={event => setActionQuery(event.target.value)} /></label><button className="btn-secondary" onClick={() => { setActionFilter('ALL'); setActionQuery(''); }}>Show all dispatches</button><span className="helper">{filteredActions.length} of {data.actions.length} recommendations</span></div>
      <div className="review-actions">{filteredActions.map(action => {
        const status = getActionStatus(action);
        const Icon = RESOURCE_ICONS[action.resource];
        const next = { PLANNED: 'APPROVED', APPROVED: 'DISPATCHED', DISPATCHED: 'DELIVERED' }[status];
        const label = { PLANNED: `Approve ${action.area_name} ${RESOURCES[action.resource][0]}`, APPROVED: `Mark dispatched: ${action.area_name} ${RESOURCES[action.resource][0]}`, DISPATCHED: `Confirm delivered: ${action.area_name} ${RESOURCES[action.resource][0]}`, DELIVERED: 'Delivery recorded' }[status];
        return <article className={`glass-panel dispatch-card resource-${action.resource}`} key={action.action_id}><div className="section-row"><h3>{action.area_name}</h3><b className="priority-badge" data-level={action.priority_level}>{action.priority_level}</b></div><span className="dispatch-state" data-status={status}>{status.toLowerCase()}</span>
        <div className="dispatch-quantity"><span className="resource-icon"><Icon size={21} /></span><p className="action-quantity">{fmt(action.quantity)} <span>{RESOURCES[action.resource][1]} · {RESOURCES[action.resource][0]}</span></p></div>
        <ol className="dispatch-progress" aria-label="Dispatch progress">{STAGES.map((stage, index) => <li key={stage} className={index <= STAGES.indexOf(status) ? 'reached' : ''}><span />{['Plan', 'Approve', 'Dispatch', 'Deliver'][index]}</li>)}</ol>
        <details className="action-reason"><summary>Why this allocation?</summary><p>{action.reason}</p><p className="helper">{action.expected_effect}</p></details>
        <button className={next ? 'btn-primary' : 'btn-secondary'} disabled={busy || !next} onClick={() => operate(async () => { const result = await request(`/plans/${data.plan_id}/dispatch${status === 'PLANNED' ? '' : '/status'}`, { action_id: action.action_id, ...(status === 'PLANNED' ? {} : { status: next }) }); const plan = await request(`/plans/${data.plan_id}`); setData({ ...plan, inputs: normalizeConfig(plan.inputs) }); setNotice(result.message); })}>{label}</button>
      </article>; })}</div>{data.actions.length > 0 && !filteredActions.length && <section className="glass-panel empty-state"><Search size={26} /><h3>No matching recommendations</h3><p>Try another location, resource, or dispatch stage.</p><button className="btn-secondary" onClick={() => { setActionFilter('ALL'); setActionQuery(''); }}>Clear filters</button></section>}{!data.actions.length && <section className="glass-panel empty-state"><Package size={28} /><h3>No dispatchable stock</h3><p>Review unmet need and increase available supplies before approving resource movements.</p></section>}
      {data.warnings.length > 0 && <section className="glass-panel"><h3>Operational constraints</h3><div className="warning-list">{data.warnings.map((warning, index) => <p key={`${warning.category}-${index}`}><strong>{warning.title}</strong><br />{warning.message}</p>)}</div></section>}
      <div className="nav-actions-row"><button className="btn-secondary" onClick={() => navigate(2)}>Back to analysis</button><button className="btn-primary" onClick={() => navigate(4)}>Test a supply shock <ArrowRight size={16} /></button></div>
    </main>}

    {step === 4 && data && <main><div className="page-intro"><span className="eyebrow">04 / SIMULATION & RECORDS</span><h1>Compare a supply shock</h1><p>Test a change before changing your plan. Your saved scenario remains the baseline.</p></div>
      <div className="review-grid"><section className="glass-panel"><h3>What-if inputs</h3>
        <label className="field-label">Water stock change: {shock.shock_water_pct}%<input type="range" min="-100" max="100" step="5" value={shock.shock_water_pct} onChange={e => setShock(current => ({ ...current, shock_water_pct: Number(e.target.value) }))} /></label>
        <label className="field-label">Population change: {shock.shock_pop_pct}%<input type="range" min="-50" max="100" step="5" value={shock.shock_pop_pct} onChange={e => setShock(current => ({ ...current, shock_pop_pct: Number(e.target.value) }))} /></label>
        <button disabled={busy} className="btn-primary" onClick={() => operate(async () => { setSimulation(await request('/simulate', { plan_id: data.plan_id, ...shock })); await refreshAudit(); })}>Run stress test</button>
      </section><section className="glass-panel"><h3>Local planning bulletin</h3><p>{bulletin}</p><button className="btn-secondary" disabled={busy || data.bulletin_saved} onClick={() => operate(async () => { const result = await request(`/plans/${data.plan_id}/bulletin`, {}); setData(current => ({ ...current, bulletin_saved: true })); setNotice(result.message); await refreshAudit(); })}>{data.bulletin_saved ? 'Bulletin saved locally' : 'Save local bulletin'}</button><p className="helper">Saved to the project audit history. This does not broadcast a public alert.</p></section></div>
      {simulation && <section className="glass-panel"><h3>Before and after</h3><p>Estimated residents needing aid: {fmt(simulation.affected_before)} → {fmt(simulation.affected_after)}. Water supply change: {simulation.shock_water_pct}%.</p><div className="simulation-summary">{simulation.comparison.map(resource => <article key={resource.resource} className={`resource-${resource.resource}`}><span>{RESOURCES[resource.resource][0]} coverage</span><div><strong>{resource.coverage_before}%</strong><ArrowRight size={18} /><strong className={resource.coverage_after < resource.coverage_before ? 'coverage-decreased' : ''}>{resource.coverage_after}%</strong></div><div className="comparison-track"><i style={{ width: `${resource.coverage_before}%` }} /><b style={{ width: `${resource.coverage_after}%` }} /></div><small>{resource.shortage_delta > 0 ? `${fmt(resource.shortage_delta)} more ${RESOURCES[resource.resource][1]} needed` : resource.shortage_delta < 0 ? `${fmt(-resource.shortage_delta)} fewer ${RESOURCES[resource.resource][1]} needed` : 'Unmet need unchanged'}</small></article>)}</div><div className="table-scroll"><table className="review-table"><thead><tr><th>Resource</th><th>Coverage before</th><th>Coverage after</th><th>Shortage before</th><th>Shortage after</th><th>Shortage change</th></tr></thead><tbody>{simulation.comparison.map(r => <tr key={r.resource}><th>{RESOURCES[r.resource][0]}</th><td>{r.coverage_before}%</td><td>{r.coverage_after}%</td><td>{fmt(r.shortage_before)}</td><td>{fmt(r.shortage_after)}</td><td>{fmt(r.shortage_delta)}</td></tr>)}</tbody></table></div></section>}
      <section className="glass-panel"><div className="section-row"><h3>Decision audit history</h3><div className="inline-actions"><button className="btn-secondary" disabled={busy} onClick={() => operate(refreshAudit)}><RefreshCw size={14} /> Refresh</button><a className="btn-secondary" href={`${API}/api/audit/export.csv`}><Download size={14} /> Export audit CSV</a></div></div>
        <div className="table-scroll"><table className="review-table"><thead><tr><th>Time in UTC</th><th>Event</th><th>Plan</th><th>Details</th></tr></thead><tbody>{audit.map(event => <tr key={event.event_id}><td>{event.created}</td><td>{event.kind.replaceAll('_', ' ')}</td><td>{event.plan_id.slice(0, 8)}</td><td>{event.payload.scenario_name || (event.payload.area_name ? `${event.payload.area_name} · ${event.payload.resource.replaceAll('_', ' ')}` : event.payload.action_id) || (event.kind === 'SIMULATION' ? `Water ${event.payload.shock_water_pct}%, population ${event.payload.shock_pop_pct}%` : event.payload.message || event.item_id)}</td></tr>)}</tbody></table></div>{!audit.length && <p>No recorded decisions yet. Run an analysis to create one.</p>}
      </section><button className="btn-secondary" onClick={() => navigate(3)}>Back to response plan</button>
    </main>}
    {step === 5 && <FundsPanel request={request} apiBase={API} plans={scenarios} currentPlan={data} />}
    <footer className="footer-disclaimer"><p>Decision support with synthetic examples and user-entered observations. Model training data, resource rates, severity multipliers and service floors are planning assumptions.</p><p>Palli Pavan Kumar · Duddu Satya Sai Vishnu Vardhan · Darisi Rithvik · G Taruni</p><a href="https://github.com/palli-pavan/dia" target="_blank" rel="noreferrer">Project repository</a></footer>
    </div></div>
  </div>;
}
