import { useEffect, useRef, useState } from 'react';
import { HeartHandshake, IndianRupee, Wallet, ReceiptText, Download, RefreshCw, Search,
  ArrowDownLeft, Target, CheckCircle2, AlertTriangle, X, LoaderCircle, CircleSlash } from 'lucide-react';

const CATEGORY = { GENERAL: 'General relief', FOOD: 'Food', WATER: 'Water', MEDICAL: 'Medical care', TRANSPORT: 'Transport', SHELTER: 'Shelter', OTHER: 'Other' };
const METHODS = { CASH: 'Cash', UPI: 'UPI', BANK_TRANSFER: 'Bank transfer', OTHER: 'Other' };
const money = paise => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(paise / 100);
const date = value => new Date(value).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
const emptyEntry = (kind = 'DONATION', planId = '') => ({ request_id: crypto.randomUUID(), kind, amount: '', party: '',
  category: kind === 'EXPENSE' ? 'FOOD' : 'GENERAL', payment_method: 'UPI', reference: '', note: '',
  donation_status: 'RECEIVED', plan_id: planId, area_id: '' });
const stateOf = entry => entry.voided_at ? 'VOIDED' : entry.kind === 'EXPENSE' ? 'EXPENSE' : entry.donation_status;

export default function FundsPanel({ request, apiBase, plans, currentPlan }) {
  const [fund, setFund] = useState(null);
  const [form, setForm] = useState(() => emptyEntry('DONATION', currentPlan?.plan_id || ''));
  const [loadedPlan, setLoadedPlan] = useState(null);
  const [goal, setGoal] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('ALL');
  const [voidTarget, setVoidTarget] = useState(null);
  const [voidReason, setVoidReason] = useState('');
  const voidDialog = useRef(null);
  const areas = !form.plan_id ? [] : form.plan_id === currentPlan?.plan_id ? currentPlan.areas
    : loadedPlan?.plan_id === form.plan_id ? loadedPlan.areas : [];
  const planOptions = [...plans];
  if (currentPlan && !planOptions.some(plan => plan.plan_id === currentPlan.plan_id)) {
    planOptions.unshift({ plan_id: currentPlan.plan_id, scenario_name: currentPlan.inputs.scenario_name, location_count: currentPlan.areas.length });
  }
  const update = (key, value) => setForm(current => ({ ...current, [key]: value, ...(key === 'plan_id' ? { area_id: '' } : {}) }));

  useEffect(() => {
    let active = true;
    request('/funds').then(result => { if (active) { setFund(result); setGoal(String(result.goal_paise / 100)); } })
      .catch(err => active && setError(err.message));
    return () => { active = false; };
  }, [request]);

  useEffect(() => {
    let active = true;
    if (form.plan_id && form.plan_id !== currentPlan?.plan_id)
      request(`/plans/${form.plan_id}`).then(plan => active && setLoadedPlan(plan)).catch(err => active && setError(err.message));
    return () => { active = false; };
  }, [form.plan_id, currentPlan, request]);

  useEffect(() => {
    if (voidTarget && !voidDialog.current.open) voidDialog.current.showModal();
    if (!voidTarget && voidDialog.current.open) voidDialog.current.close();
  }, [voidTarget]);

  async function perform(path, body, message) {
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await request(path, body);
      setFund(result.fund || result); setNotice(message);
      return result;
    } catch (err) { setError(err.message); return false; }
    finally { setBusy(false); }
  }
  async function save(event) {
    event.preventDefault();
    const ok = await perform('/funds/entries', { ...form, plan_id: form.plan_id || null, area_id: form.area_id || null,
      donation_status: form.kind === 'EXPENSE' ? null : form.donation_status },
    form.kind === 'EXPENSE' ? 'Expense saved and the available balance updated.' : form.donation_status === 'PLEDGED' ? 'Pledge saved. It becomes available only when you mark it received.' : 'Donation receipt saved in the local ledger.');
    if (ok) setForm(emptyEntry(form.kind, form.plan_id));
  }

  const entries = fund?.entries.filter(entry => (filter === 'ALL' || stateOf(entry) === filter)
    && [entry.party, entry.reference, entry.note, entry.scenario_name, entry.area_name, CATEGORY[entry.category]].filter(Boolean).join(' ').toLowerCase().includes(query.toLowerCase().trim())) || [];
  const canSpend = fund && fund.totals.available_paise > 0;
  const receivedCount = fund?.entries.filter(entry => !entry.voided_at && entry.kind === 'DONATION' && entry.donation_status === 'RECEIVED').length || 0;

  return <main className="funds-panel">
    <div className="page-intro"><span className="eyebrow">05 / DONATIONS & FUNDS</span><h1>Turn support into relief.</h1><p>Track donations, outstanding pledges and how the shared relief fund is used.</p></div>
    <div className="fund-mode-note"><HeartHandshake size={20} /><div><strong>Local project ledger · INR</strong><p>Record donations received outside the app or commitments made by donors. No payment is collected or transferred here.</p></div><span className="soft-badge">Manual records</span></div>
    {error && !voidTarget && <div className="error-banner" role="alert"><AlertTriangle size={17} /><span>{error}</span><button onClick={() => setError('')}>Dismiss</button></div>}
    {notice && <div className="review-notice" role="status"><CheckCircle2 size={17} /><span>{notice}</span><button className="icon-button" aria-label="Dismiss fund notification" onClick={() => setNotice('')}><X size={15} /></button></div>}
    {!fund ? <section className="glass-panel empty-state">{error ? <><Wallet size={26} /><h3>Fund ledger could not be loaded</h3><button className="btn-secondary" disabled={busy} onClick={async () => { const result = await perform('/funds', undefined, 'Ledger refreshed.'); if (result) setGoal(String(result.goal_paise / 100)); }}>Try again</button></> : <p role="status"><LoaderCircle className="spin" size={18} /> Loading the local fund ledger…</p>}</section> : <>
      <section className="stats-row fund-stats" aria-label="Relief fund summary">{[
        ['Funds received', fund.totals.received_paise, `${receivedCount} received donation ${receivedCount === 1 ? 'record' : 'records'}`, ArrowDownLeft],
        ['Pledges pending', fund.totals.pledged_paise, 'Commitments · not yet spendable', HeartHandshake],
        ['Funds spent', fund.totals.spent_paise, `${fund.totals.expense_count} active expense ${fund.totals.expense_count === 1 ? 'record' : 'records'}`, ReceiptText],
        ['Available balance', fund.totals.available_paise, 'Received funds minus expenses', Wallet],
      ].map(([label, value, hint, Icon], index) => <article className={'stat-card fund-stat-' + index} key={label}><div><span className="stat-label">{label}</span><Icon size={17} /></div><strong className="stat-num">{money(value)}</strong><span className="stat-sub">{hint}</span></article>)}</section>
      <div className="funds-workspace"><section className="glass-panel fund-entry-panel"><div className="section-row"><div><h3><IndianRupee size={18} />Add a fund record</h3><p className="helper">Each entry is saved with a unique record ID and timestamp.</p></div></div>
        <div className="fund-entry-tabs" aria-label="Fund entry type">{[['DONATION', 'Donation', HeartHandshake], ['EXPENSE', 'Expense', ReceiptText]].map(([kind, label, Icon]) => <button key={kind} type="button" aria-pressed={form.kind === kind} disabled={busy} className={form.kind === kind ? 'selected' : ''} onClick={() => { setForm(emptyEntry(kind, form.plan_id)); setError(''); }}><Icon size={16} />{label}</button>)}</div>
        <form onSubmit={save}>
          <div className="fund-form-grid"><label className="field-label">Amount (₹)<input required type="number" min="0.01" max={form.kind === 'EXPENSE' && canSpend ? Math.min(1000000000, fund.totals.available_paise / 100) : 1000000000} step="0.01" placeholder="0.00" value={form.amount} onChange={event => update('amount', event.target.value)} /></label>
            <label className="field-label">{form.kind === 'DONATION' ? 'Donor name (optional)' : 'Paid to (optional)'}<input maxLength="100" placeholder={form.kind === 'DONATION' ? 'Anonymous if left blank' : 'Supplier or relief team'} value={form.party} onChange={event => update('party', event.target.value)} /></label>
            {form.kind === 'DONATION' ? <label className="field-label">Donation status<select value={form.donation_status} onChange={event => update('donation_status', event.target.value)}><option value="RECEIVED">Received · recorded manually</option><option value="PLEDGED">Pledged · awaiting receipt</option></select></label> : <label className="field-label">Expense category<select value={form.category} onChange={event => update('category', event.target.value)}>{Object.entries(CATEGORY).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>}
            <label className="field-label">Payment method (record only)<select value={form.payment_method} onChange={event => update('payment_method', event.target.value)}>{Object.entries(METHODS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
          </div>
          <label className="field-label">Reference (optional)<input maxLength="100" placeholder="Receipt or transaction reference from your own records" value={form.reference} onChange={event => update('reference', event.target.value)} /></label>
          <label className="field-label">{form.kind === 'EXPENSE' ? 'What were the funds used for?' : 'Note (optional)'}<textarea required={form.kind === 'EXPENSE'} minLength={form.kind === 'EXPENSE' ? 3 : undefined} maxLength="500" rows="2" placeholder={form.kind === 'EXPENSE' ? 'e.g. Drinking water supplied to the affected area' : 'Purpose or any details to keep with this entry'} value={form.note} onChange={event => update('note', event.target.value)} /></label>
          <div className="fund-form-grid"><label className="field-label">Saved scenario (optional)<select value={form.plan_id} onChange={event => update('plan_id', event.target.value)}><option value="">Shared relief fund · no scenario link</option>{planOptions.map(plan => <option key={plan.plan_id} value={plan.plan_id}>{plan.scenario_name} · {plan.plan_id.slice(0, 6)}</option>)}</select></label>
            <label className="field-label">Affected area (optional)<select value={form.area_id} disabled={!form.plan_id || !areas.length} onChange={event => update('area_id', event.target.value)}><option value="">All areas / not specified</option>{areas.map(area => <option key={area.area_id} value={area.area_id}>{area.area_name}</option>)}</select></label></div>
          {form.kind === 'EXPENSE' && <p className={'fund-balance-hint ' + (!canSpend ? 'unavailable' : '')}><Wallet size={15} />{canSpend ? `${money(fund.totals.available_paise)} available for expenses.` : 'Record received funds before adding an expense. Pledges are not available to spend.'}</p>}
          <div className="fund-form-actions"><button type="button" className="btn-secondary" disabled={busy} onClick={() => { setForm(emptyEntry(form.kind, form.plan_id)); setError(''); }}>Clear form</button><button className="btn-primary" disabled={busy || (form.kind === 'EXPENSE' && !canSpend)} type="submit">{busy ? <LoaderCircle className="spin" size={16} /> : form.kind === 'DONATION' ? <HeartHandshake size={16} /> : <ReceiptText size={16} />}{form.kind === 'DONATION' ? 'Record donation' : 'Record expense'}</button></div>
        </form>
      </section><div className="fund-side-panels"><section className="glass-panel"><h3><Target size={18} />Fundraising target</h3><div className="fund-goal-values"><strong>{money(fund.totals.received_paise)}</strong><span>{fund.goal_paise ? `of ${money(fund.goal_paise)} target` : 'received so far'}</span></div>
          <div className="fund-goal-track" role="progressbar" aria-label="Fundraising progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow={fund.goal_progress_pct}><span style={{ width: fund.goal_progress_pct + '%' }} /></div><p className="helper">{fund.goal_paise ? `${fund.goal_progress_pct}% of target reached from received donations.` : 'Set a target to follow your fundraising progress.'} Pledges are shown separately.</p>
          <form onSubmit={async event => { event.preventDefault(); await perform('/funds/goal', { amount: goal || '0' }, 'Fundraising target saved.'); }}><label className="field-label">Fundraising target (₹)<input type="number" min="0" max="1000000000" step="0.01" value={goal} onChange={event => setGoal(event.target.value)} /></label><button className="btn-secondary" disabled={busy}>Save target</button></form>
        </section><section className="glass-panel"><h3><ReceiptText size={18} />Where funds are used</h3>{fund.category_spend.length ? <div className="fund-category-bars">{fund.category_spend.map(category => <div key={category.category}><div><span>{CATEGORY[category.category]}</span><strong>{money(category.amount_paise)}</strong></div><div className="bar-track"><div style={{ width: (100 * category.amount_paise / fund.totals.spent_paise) + '%' }} /></div></div>)}</div> : <div className="fund-category-empty"><ReceiptText size={25} /><p>No expenses recorded yet.</p><span>Expense categories appear here as funds are used.</span></div>}</section></div></div>
      <section className="glass-panel fund-ledger"><div className="section-row"><div><h3><ReceiptText size={18} />Donation & expense ledger</h3><p className="helper">The shared fund spans all scenarios. Voided records stay in history and are excluded from balances.</p></div><div className="inline-actions wrap"><button className="btn-secondary" disabled={busy} onClick={() => perform('/funds', undefined, 'Ledger refreshed.')}><RefreshCw size={14} />Refresh</button><a className="btn-secondary" href={`${apiBase}/api/funds/export.csv`}><Download size={14} />Export full ledger CSV</a></div></div>
        <div className="fund-ledger-toolbar"><label className="search-field"><Search size={16} /><input type="search" aria-label="Search fund ledger" placeholder="Search donor, reference, scenario or area…" value={query} onChange={event => setQuery(event.target.value)} /></label><label className="fund-filter-label">Show<select aria-label="Fund ledger filter" value={filter} onChange={event => setFilter(event.target.value)}>{[['ALL', 'All records'], ['RECEIVED', 'Received donations'], ['PLEDGED', 'Pending pledges'], ['EXPENSE', 'Expenses'], ['VOIDED', 'Voided records']].map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><span className="helper">{entries.length} records shown</span></div>
        {entries.length ? <div className="table-scroll"><table className="review-table fund-table"><thead><tr><th>Recorded</th><th>Donor / paid to</th><th>Amount</th><th>Status</th><th>Purpose / linked area</th><th>Reference</th><th>Manage</th></tr></thead><tbody>{entries.map(entry => <tr key={entry.entry_id} className={entry.voided_at ? 'fund-voided-row' : ''}><td>{date(entry.created)}<small>#{entry.entry_id.slice(0, 8)}</small></td><th>{entry.party}<small>{entry.note}{entry.voided_at && <><br />Voided: {entry.void_reason}</>}</small></th><td><strong className={entry.kind === 'EXPENSE' ? 'fund-outgoing' : 'fund-incoming'}>{entry.kind === 'EXPENSE' ? '−' : '+'}{money(entry.amount_paise)}</strong></td><td><span className="fund-tag" data-state={stateOf(entry)}>{stateOf(entry).toLowerCase()}</span><small>{METHODS[entry.payment_method]}</small></td><td>{CATEGORY[entry.category]}<small>{entry.scenario_name || 'Shared relief fund'}{entry.area_name && <><br />{entry.area_name}</>}</small></td><td>{entry.reference || '—'}</td><td>{!entry.voided_at && <div className="inline-actions wrap">{entry.kind === 'DONATION' && entry.donation_status === 'PLEDGED' && <button className="btn-secondary" disabled={busy} onClick={() => perform(`/funds/entries/${entry.entry_id}/receive`, {}, 'Pledge marked received from your confirmation. The available balance is updated.')}>Mark received</button>}<button className="icon-button" aria-label={`Void record ${entry.entry_id.slice(0, 8)}`} title="Void an incorrect record" disabled={busy} onClick={() => { setVoidTarget(entry); setVoidReason(''); setError(''); }}><CircleSlash size={16} /></button></div>}</td></tr>)}</tbody></table></div> : <div className="empty-state fund-ledger-empty"><HeartHandshake size={30} /><h3>{fund.entries.length ? 'No matching fund records' : 'Your relief fund starts here'}</h3><p>{fund.entries.length ? 'Try another search or ledger filter.' : 'Record a received donation or a pledge, then track how funds support relief.'}</p></div>}
      </section>
    </>}
    <dialog ref={voidDialog} className="location-dialog fund-void-dialog" aria-labelledby="void-fund-title" onCancel={() => { setVoidTarget(null); setError(''); }} onClose={() => setVoidTarget(null)}><header className="dialog-header"><div><span className="eyebrow">CORRECT A LOCAL RECORD</span><h2 id="void-fund-title">Void this ledger entry?</h2><p>{voidTarget && `${money(voidTarget.amount_paise)} · ${voidTarget.party}`}</p></div><button className="icon-button" aria-label="Close correction form" onClick={() => { setVoidTarget(null); setError(''); }}><X size={19} /></button></header><form onSubmit={async event => { event.preventDefault(); if (await perform(`/funds/entries/${voidTarget.entry_id}/void`, { reason: voidReason }, 'Record voided. Its history is preserved and balances have been recalculated.')) setVoidTarget(null); }}><div className="dialog-body"><p className="helper">This excludes the entry from fund totals and keeps it in the ledger. It does not reverse a bank transfer or issue a refund.</p><label className="field-label">Reason for correction<input required minLength="3" maxLength="200" value={voidReason} onChange={event => setVoidReason(event.target.value)} placeholder="e.g. Duplicate entry" /></label>{error && <p role="alert" className="location-error">{error}</p>}</div><footer className="dialog-actions"><button className="btn-secondary" type="button" onClick={() => { setVoidTarget(null); setError(''); }}>Keep record</button><button className="btn-primary" disabled={busy} type="submit">Void record</button></footer></form></dialog>
  </main>;
}
