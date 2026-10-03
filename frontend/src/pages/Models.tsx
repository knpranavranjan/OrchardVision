import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { Badge, Panel } from '../components/ui'
import { api, type CropProfile, type ModelRow, type Orchard } from '../lib/api'
import { words } from '../lib/format'

export function Models() {
  const [crops, setCrops] = useState<CropProfile[]>([])
  const [models, setModels] = useState<ModelRow[]>([])
  const [orchards, setOrchards] = useState<Orchard[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([api.crops(), api.models(), api.orchards().catch(() => [] as Orchard[])])
      .then(([c, m, o]) => {
        setCrops(c)
        setModels(m)
        setOrchards(o)
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  return (
    <div className="scroll h-full p-5">
      <div className="mx-auto grid max-w-5xl gap-4">
        <header>
          <h1 className="text-xl font-semibold">Models</h1>
          <p className="mt-1 max-w-[72ch] text-[13.5px] text-muted">
            Each crop has a profile and a set of model versions. An orchard uses its crop's active versions unless a
            specific version is pinned for it. Weights are checked against their recorded checksum before use, and the
            pre-flight checklist fails if an orchard's models are missing.
          </p>
        </header>
        {error && <p role="alert" className="rounded-md border border-danger/50 bg-danger/10 p-2.5 text-[13px]">{error}</p>}

        <Panel title="Crop profiles">
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead className="text-left text-[11px] uppercase tracking-wider text-muted">
                <tr>
                  <th className="pb-2">Crop</th><th>Plant shape</th><th>Spacing</th><th>Coarsest image detail</th>
                  <th>Active tree model</th><th>Active fruit model</th><th>Fruit-pass geometry</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line/60">
                {crops.map((c) => (
                  <tr key={c.crop}>
                    <td className="py-2 font-semibold">{c.name}</td>
                    <td>{words(c.plant_architecture)}</td>
                    <td className="num">{c.tree_spacing_m} m</td>
                    <td className="num">{c.min_gsd_cm.tree} cm/px</td>
                    <td className="num">{c.active.tree}</td>
                    <td className="num">{c.active.fruit}</td>
                    <td>
                      {words(c.viewpoint_template.pass_type)}
                      {c.viewpoint_template.provisional && <Badge tone="warn" className="ml-2">provisional</Badge>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="Model versions">
          <table className="w-full text-[13px]">
            <thead className="text-left text-[11px] uppercase tracking-wider text-muted">
              <tr><th className="pb-2">Crop</th><th>Kind</th><th>Version</th><th>Framework</th><th>Status</th><th>Checksum</th><th>Notes</th></tr>
            </thead>
            <tbody className="divide-y divide-line/60">
              {models.map((m) => (
                <tr key={`${m.crop}/${m.kind}/${m.version}`}>
                  <td className="py-2">{m.crop}</td>
                  <td>{m.kind}</td>
                  <td className="num">{m.version}</td>
                  <td>{m.framework}</td>
                  <td>
                    <Badge tone={m.status === 'active' ? 'good' : m.status === 'available' ? 'info' : 'bad'}>{words(m.status)}</Badge>
                  </td>
                  <td className="num text-muted">{m.sha256.slice(0, 10)}…</td>
                  <td className="text-muted">{m.notes}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-[12.5px] text-muted">
            The current versions are placeholders that detect nothing. Real papaya models are registered here in the
            model-training stage; nothing else in the ground station changes when they are.
          </p>
        </Panel>

        <Panel title="Which orchard uses which model">
          {orchards.length === 0 ? (
            <p className="text-[13px] text-muted">
              No orchards yet. <Link to="/orchards" className="text-info underline">Create one</Link> to choose its crop and models.
            </p>
          ) : (
            <table className="w-full text-[13px]">
              <thead className="text-left text-[11px] uppercase tracking-wider text-muted">
                <tr><th className="pb-2">Orchard</th><th>Crop</th><th>Tree model</th><th>Fruit model</th><th>Status</th></tr>
              </thead>
              <tbody className="divide-y divide-line/60">
                {orchards.map((o) => (
                  <tr key={o.id}>
                    <td className="py-2 font-semibold">{o.name}</td>
                    <td>{o.crop}</td>
                    <td className="num">{o.tree_model_version ?? 'crop default'}</td>
                    <td className="num">{o.fruit_model_version ?? 'crop default'}</td>
                    <td><Badge tone={o.models_ready ? 'good' : 'bad'}>{o.models_ready ? 'ready' : 'not ready'}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      </div>
    </div>
  )
}
