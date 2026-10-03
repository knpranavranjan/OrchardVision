import { Plus, Save, Trash2 } from 'lucide-react'
import type { Map as MlMap } from 'maplibre-gl'
import { useCallback, useEffect, useState } from 'react'

import { MapView, useVertexEditor } from '../components/MapView'
import { Badge, Button, Empty, Panel, SelectField, TextField } from '../components/ui'
import { api, type CropProfile, type LatLon, type ModelRow, type Orchard, type OrchardInput } from '../lib/api'
import { fitTo, setPolygon, token, toLngLat } from '../lib/map'
import { useVehicle } from '../lib/store'

const BLANK: OrchardInput = {
  name: '',
  crop: 'papaya',
  boundary: [],
  notes: '',
  tree_model_version: null,
  fruit_model_version: null,
}

const DEFAULT_CENTER: LatLon = { lat: 12.9716, lon: 77.5946 }

export function Orchards() {
  const toast = useVehicle((s) => s.toast)
  const [map, setMap] = useState<MlMap | null>(null)
  const [orchards, setOrchards] = useState<Orchard[]>([])
  const [crops, setCrops] = useState<CropProfile[]>([])
  const [models, setModels] = useState<ModelRow[]>([])
  const [selected, setSelected] = useState<number | 'new' | null>(null)
  const [form, setForm] = useState<OrchardInput>(BLANK)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [o, c, m] = await Promise.all([api.orchards(), api.crops(), api.models()])
      setOrchards(o)
      setCrops(c)
      setModels(m)
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    }
  }, [])
  useEffect(() => {
    void load()
  }, [load])

  const editing = selected !== null
  const pick = (o: Orchard) => {
    setSelected(o.id)
    setForm({
      name: o.name,
      crop: o.crop,
      boundary: o.boundary,
      notes: o.notes,
      tree_model_version: o.tree_model_version,
      fruit_model_version: o.fruit_model_version,
    })
    if (map && o.boundary.length) fitTo(map, o.boundary.map(toLngLat), 80)
  }

  useEffect(() => {
    if (!map) return
    setPolygon(map, 'orchard-boundary', form.boundary.map(toLngLat), { color: token('--brand'), fillOpacity: 0.16 })
  }, [map, form.boundary])

  // The other orchards, faintly, for context.
  useEffect(() => {
    if (!map) return
    orchards.forEach((o) => {
      const ring = o.id === selected ? [] : o.boundary.map(toLngLat)
      setPolygon(map, `orchard-${o.id}`, ring, { color: '#ffffff', fillOpacity: 0.04, width: 1 })
    })
  }, [map, orchards, selected])

  useVertexEditor(map, {
    points: form.boundary,
    onChange: (boundary) => setForm((f) => ({ ...f, boundary })),
    active: editing,
    color: token('--brand') || '#3ddc84',
  })

  const onMapClick = useCallback(
    (at: LatLon) => {
      if (editing) setForm((f) => ({ ...f, boundary: [...f.boundary, at] }))
    },
    [editing],
  )

  const save = async () => {
    setBusy(true)
    try {
      const saved = selected === 'new' ? await api.createOrchard(form) : await api.updateOrchard(selected as number, form)
      await load()
      setSelected(saved.id)
      toast('good', `Saved ${saved.name}: ${saved.area_ha.toFixed(2)} ha`)
    } catch (e) {
      toast('bad', (e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    if (typeof selected !== 'number' || !window.confirm(`Delete the orchard "${form.name}"? Its missions are kept.`)) return
    await api.deleteOrchard(selected)
    setSelected(null)
    setForm(BLANK)
    await load()
  }

  const versions = (kind: 'tree' | 'fruit') => {
    const crop = crops.find((c) => c.crop === form.crop)
    return [
      { value: '', label: `Crop default (${crop?.active[kind] ?? 'none'})` },
      ...models
        .filter((m) => m.crop === form.crop && m.kind === kind)
        .map((m) => ({ value: m.version, label: `${m.version} — ${m.status.replace('_', ' ')}` })),
    ]
  }

  return (
    <div className="grid h-full grid-cols-[360px_1fr]">
      <aside className="scroll flex flex-col gap-3 border-r border-line bg-bg p-3">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-semibold">Orchards</h1>
          <Button
            small
            variant="primary"
            icon={<Plus size={15} />}
            onClick={() => {
              setSelected('new')
              setForm({ ...BLANK, crop: crops[0]?.crop ?? 'papaya' })
            }}
          >
            New orchard
          </Button>
        </div>
        {error && <p role="alert" className="rounded-md border border-danger/50 bg-danger/10 p-2.5 text-[13px]">{error}</p>}

        {editing && (
          <Panel title={selected === 'new' ? 'New orchard' : 'Edit orchard'}>
            <div className="grid gap-3">
              <TextField label="Name" value={form.name} onChange={(name) => setForm((f) => ({ ...f, name }))} placeholder="Papaya Farm 01" />
              <SelectField
                label="Crop"
                value={form.crop}
                onChange={(crop) => setForm((f) => ({ ...f, crop, tree_model_version: null, fruit_model_version: null }))}
                options={crops.map((c) => ({ value: c.crop, label: c.name }))}
                hint="The crop decides which models analyse this orchard and how fine the images must be."
              />
              <SelectField label="Tree model" value={form.tree_model_version ?? ''} options={versions('tree')}
                onChange={(v) => setForm((f) => ({ ...f, tree_model_version: v || null }))} />
              <SelectField label="Fruit model" value={form.fruit_model_version ?? ''} options={versions('fruit')}
                onChange={(v) => setForm((f) => ({ ...f, fruit_model_version: v || null }))} />
              <TextField label="Notes" value={form.notes} onChange={(notes) => setForm((f) => ({ ...f, notes }))} />
              <p className="text-[12px] leading-snug text-muted">
                Boundary: {form.boundary.length} corner{form.boundary.length === 1 ? '' : 's'}. Click the map to add
                corners, drag to move, right-click to remove.
              </p>
              <div className="flex gap-2">
                <Button variant="primary" icon={<Save size={16} />} busy={busy} disabled={!form.name.trim()} onClick={() => void save()}>
                  Save
                </Button>
                <Button variant="ghost" onClick={() => { setSelected(null); setForm(BLANK) }}>
                  Cancel
                </Button>
                {typeof selected === 'number' && (
                  <Button variant="ghost" className="ml-auto" icon={<Trash2 size={15} />} onClick={() => void remove()} aria-label="Delete orchard" />
                )}
              </div>
            </div>
          </Panel>
        )}

        {orchards.length === 0 && !editing ? (
          <Empty title="No orchards yet">
            An orchard records where the trees are and which crop they are. Create one, then draw its boundary on the map.
          </Empty>
        ) : (
          <ul className="grid gap-2">
            {orchards.map((o) => (
              <li key={o.id}>
                <button
                  type="button"
                  onClick={() => pick(o)}
                  className={`w-full rounded-lg border p-3 text-left transition hover:bg-surface-2 ${
                    selected === o.id ? 'border-brand bg-brand/5' : 'border-line bg-surface'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold">{o.name}</span>
                    <Badge tone={o.models_ready ? 'good' : 'bad'}>{o.models_ready ? 'Models ready' : 'Models missing'}</Badge>
                  </div>
                  <div className="num mt-1 text-[12.5px] text-muted">
                    {o.crop} · {o.area_ha.toFixed(2)} ha
                  </div>
                  <div className="mt-0.5 truncate text-[12px] text-muted">{o.models_detail}</div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </aside>
      <MapView center={DEFAULT_CENTER} onReady={setMap} onClick={onMapClick} crosshair={editing} className="h-full" />
    </div>
  )
}
