/**
 * MapLibre runs its tile work in a web worker loaded from its own file. A
 * bundler moves the library but not that file, so we serve the worker (and the
 * chunk it imports) from public/maplibre and point the library at it in
 * src/lib/map.ts. Runs before `dev` and `build`.
 */
import { copyFileSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const from = resolve(root, 'node_modules/maplibre-gl/dist')
const to = resolve(root, 'public/maplibre')

mkdirSync(to, { recursive: true })
for (const file of ['maplibre-gl-worker.mjs', 'maplibre-gl-shared.mjs']) {
  copyFileSync(resolve(from, file), resolve(to, file))
}
