import { useEffect } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'

import { Shell } from './components/Shell'
import { startLiveChannel } from './lib/store'
import { Flights } from './pages/Flights'
import { Fly } from './pages/Fly'
import { Models } from './pages/Models'
import { Orchards } from './pages/Orchards'
import { Plan } from './pages/Plan'
import { Settings } from './pages/Settings'
import { Simulation } from './pages/Simulation'

export default function App() {
  useEffect(() => {
    startLiveChannel()
  }, [])

  return (
    <BrowserRouter>
      <Shell>
        <Routes>
          <Route path="/" element={<Fly />} />
          <Route path="/plan" element={<Plan />} />
          <Route path="/orchards" element={<Orchards />} />
          <Route path="/flights" element={<Flights />} />
          <Route path="/simulation" element={<Simulation />} />
          <Route path="/models" element={<Models />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </Shell>
    </BrowserRouter>
  )
}
