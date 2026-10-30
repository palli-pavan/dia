import { useEffect, useRef, useState } from 'react';
import { MapPin, Plus, Pencil, Trash2, X, Users, Building2, Undo2, ArrowRight, Crosshair } from 'lucide-react';
import { MapContainer, TileLayer, CircleMarker, Tooltip, useMapEvents } from 'react-leaflet';

const emptyLocation = () => ({ location_id: 'loc_' + crypto.randomUUID(), name: '', latitude: '', longitude: '',
  population: '', affected_population: '', children_population: 0, elderly_population: 0,
  population_density: '', minor_damage: '', major_damage: '', destroyed_buildings: '', magnitude: '' });
const numberFields = [
  ['population', 'Resident population', 10000000, 1],
  ['affected_population', 'Affected population (optional)', 10000000, 1],
  ['children_population', 'Children', 10000000, 1], ['elderly_population', 'Elderly residents', 10000000, 1],
  ['population_density', 'Population density / km²', 1000000, 'any'],
  ['minor_damage', 'Buildings with minor damage', 10000000, 1],
  ['major_damage', 'Buildings with major damage', 10000000, 1],
  ['destroyed_buildings', 'Destroyed buildings', 10000000, 1],
  ['magnitude', 'Hazard magnitude / intensity', 20, 'any'],
];

function PickCoordinates({ onPick }) {
  useMapEvents({ click: event => onPick(event.latlng) });
  return null;
}

export default function LocationEditor({ config, update, disabled, sampleCount = 0, onAddSamples }) {
  const [draft, setDraft] = useState(emptyLocation);
  const [editing, setEditing] = useState(false);
  const [showMap, setShowMap] = useState(false);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(false);
  const [removed, setRemoved] = useState(null);
  const dialogRef = useRef(null);
  const locations = config.locations || [];
  const canUndo = removed && !locations.some(location => location.location_id === removed.location.location_id
    || location.name.toLowerCase() === removed.location.name.toLowerCase());
  const change = (key, value) => setDraft(current => ({ ...current, [key]: value }));
  const coordinatesValid = draft.latitude !== '' && draft.longitude !== '' && Number.isFinite(Number(draft.latitude))
    && Number.isFinite(Number(draft.longitude)) && Math.abs(Number(draft.latitude)) <= 90 && Math.abs(Number(draft.longitude)) <= 180;
  useEffect(() => {
    const dialog = dialogRef.current;
    if (open && !dialog.open) { dialog.showModal(); dialog.querySelector('input')?.focus(); }
    if (!open && dialog.open) dialog.close();
  }, [open]);
  function startEdit(location) {
    setDraft(location ? { ...location, affected_population: location.affected_population ?? '' } : emptyLocation());
    setEditing(Boolean(location)); setShowMap(false); setError(''); setOpen(true);
  }
  function numberField(key) {
    const [, label, max, step] = numberFields.find(field => field[0] === key);
    return <label key={key} className="field-label">{label}<input required={key !== 'affected_population'} type="number" min="0" max={max} step={step} value={draft[key]} onChange={event => change(key, event.target.value)} placeholder={key === 'affected_population' ? 'Leave blank to estimate' : 'Enter count'} /></label>;
  }
  function save(event) {
    event.preventDefault(); setError('');
    const location = { ...draft, name: draft.name.trim() };
    for (const [key] of numberFields) location[key] = key === 'affected_population' && draft[key] === '' ? null : Number(draft[key]);
    location.latitude = Number(draft.latitude); location.longitude = Number(draft.longitude);
    if (!location.name) { setError('Enter a location name.'); return; }
    if (locations.some(other => other.location_id !== location.location_id && other.name.trim().toLowerCase() === location.name.toLowerCase()) || Object.keys(config.area_populations).some(name => name.toLowerCase() === location.name.toLowerCase())) {
      setError('Use a unique location name.'); return;
    }
    if (location.affected_population !== null && location.affected_population > location.population) { setError('Affected population cannot exceed resident population.'); return; }
    if (location.children_population + location.elderly_population > location.population) { setError('Children and elderly counts combined cannot exceed resident population.'); return; }
    if (!editing && locations.length >= 100) { setError('A scenario supports up to 100 custom locations.'); return; }
    update('locations', editing ? locations.map(item => item.location_id === location.location_id ? location : item) : [...locations, location]);
    setDraft(emptyLocation()); setEditing(false); setShowMap(false); setOpen(false); setRemoved(null);
  }
  return <section className="glass-panel locations-panel">
    <div className="section-row"><div><h3><MapPin size={18} />Custom affected locations<span className="count-badge">{locations.length}</span></h3><p className="helper">Any place, anywhere. Add the observations your plan should use.</p></div><div className="inline-actions wrap">{onAddSamples && sampleCount > 0 && <button className="btn-secondary" type="button" disabled={disabled || locations.length + sampleCount > 100} onClick={onAddSamples}><Plus size={17} />Add {sampleCount} sample locations</button>}<button className="btn-primary" type="button" disabled={disabled} onClick={() => startEdit(null)}><Plus size={17} />Add location</button></div></div>
    {canUndo && <div className="undo-notice" role="status"><span>{removed.location.name} removed.</span><button type="button" onClick={() => { const restored = [...locations]; restored.splice(Math.min(removed.index, restored.length), 0, removed.location); update('locations', restored); setRemoved(null); }}><Undo2 size={14} />Undo</button></div>}
    {locations.length > 0 ? <div className="location-cards">{locations.map((location, index) => <article className="location-card" key={location.location_id}>
      <div className="location-card-heading"><span className="location-pin"><MapPin size={19} /></span><div><h4>{location.name}</h4><p>{location.latitude.toFixed(4)}, {location.longitude.toFixed(4)}</p></div><div className="inline-actions">
        <button type="button" className="icon-button" aria-label={'Edit ' + location.name} title={'Edit ' + location.name} disabled={disabled} onClick={() => startEdit(location)}><Pencil size={15} /></button>
        <button type="button" className="icon-button remove-location" aria-label={'Remove ' + location.name} title={'Remove ' + location.name} disabled={disabled} onClick={() => { update('locations', locations.filter(item => item.location_id !== location.location_id)); setRemoved({ location, index }); }}><Trash2 size={15} /></button>
      </div></div><div className="location-card-stats"><span>Residents<strong>{location.population.toLocaleString()}</strong></span><span>Needing aid<strong>{location.affected_population === null ? 'Auto estimate' : location.affected_population.toLocaleString()}</strong></span><span>Damage reports<strong>{(location.minor_damage + location.major_damage + location.destroyed_buildings).toLocaleString()} buildings</strong></span></div>
    </article>)}</div> : <div className="location-empty"><span className="location-pin"><MapPin size={24} /></span><div><h4>Bring your own location into the plan</h4><p>Add a village, ward, city, or affected zone. You can also start with the demo above.</p></div><ArrowRight size={20} /></div>}
    <dialog className="location-dialog" ref={dialogRef} aria-labelledby="location-dialog-title" onCancel={() => setOpen(false)} onClose={() => setOpen(false)}>
      <header className="dialog-header"><div><span className="eyebrow">LOCATION OBSERVATIONS</span><h2 id="location-dialog-title">{editing ? 'Edit affected location' : 'Add an affected location'}</h2><p>Three short sections. Your observations drive the analysis.</p></div><button type="button" className="icon-button" aria-label="Close location form" onClick={() => setOpen(false)}><X size={20} /></button></header>
      <form onSubmit={save} className="location-form"><div className="dialog-body">
      <fieldset><legend><span>01</span><MapPin size={17} />Location details</legend><p className="helper">Enter coordinates directly, or pick a point on the map.</p>
        <label className="field-label">Place name<input required maxLength="100" value={draft.name} onChange={event => change('name', event.target.value)} placeholder="e.g. Vijayawada, Ward 12" /></label>
        <div className="location-grid"><label className="field-label">Latitude<input required type="number" min="-90" max="90" step="any" value={draft.latitude} onChange={event => change('latitude', event.target.value)} placeholder="e.g. 16.5062" /></label>
        <label className="field-label">Longitude<input required type="number" min="-180" max="180" step="any" value={draft.longitude} onChange={event => change('longitude', event.target.value)} placeholder="e.g. 80.6480" /></label></div>
        <button type="button" className="btn-secondary" aria-expanded={showMap} onClick={() => setShowMap(value => !value)}><Crosshair size={16} />{showMap ? 'Hide coordinate picker' : 'Pick coordinates on map'}</button>
      {showMap && <div className="coordinate-picker"><p className="helper">Click to fill latitude and longitude. Map tiles need internet.</p>
        <MapContainer center={coordinatesValid ? [Number(draft.latitude), Number(draft.longitude)] : [20.59, 78.96]} zoom={5} style={{ height: 270 }}>
          <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OpenStreetMap contributors" />
          <PickCoordinates onPick={({ lat, lng }) => setDraft(current => ({ ...current, latitude: Number(lat.toFixed(6)), longitude: Number(lng.toFixed(6)) }))} />
          {coordinatesValid && <CircleMarker center={[Number(draft.latitude), Number(draft.longitude)]}><Tooltip>Selected location</Tooltip></CircleMarker>}
        </MapContainer></div>}</fieldset>
      <fieldset><legend><span>02</span><Users size={17} />People & vulnerability</legend><p className="helper">Affected population is optional. Leave it blank for an estimate; an entered count takes precedence.</p><div className="location-grid">{['population', 'affected_population', 'children_population', 'elderly_population', 'population_density'].map(numberField)}</div></fieldset>
      <fieldset><legend><span>03</span><Building2 size={17} />Observed damage</legend><p className="helper">Count separate buildings in each category. Use 0 where there is no reported damage.</p><div className="location-grid">{['minor_damage', 'major_damage', 'destroyed_buildings', 'magnitude'].map(numberField)}</div><p className="helper">Magnitude scale: earthquake magnitude, flood depth in feet, cyclone category (1–5), or wildfire intensity index. These follow the synthetic training assumptions.</p></fieldset>
      {error && <p role="alert" className="location-error">{error}</p>}
      </div><footer className="dialog-actions"><p>Locations are included when you run analysis.</p><button type="button" className="btn-secondary" onClick={() => setOpen(false)}>Cancel</button><button className="btn-primary" disabled={disabled} type="submit">{editing ? 'Save location changes' : 'Add affected location'}<ArrowRight size={16} /></button></footer></form>
    </dialog>
  </section>;
}
