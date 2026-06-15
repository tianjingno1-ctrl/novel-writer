import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import { FlowCanvas } from '@/components/writing/FlowCanvas'
import { CompletePage } from '@/pages/CompletePage'
import { LibraryPage } from '@/pages/LibraryPage'
import { ManuscriptsPage } from '@/pages/ManuscriptsPage'
import { NewBookPage } from '@/pages/NewBookPage'
import { SettingsPage } from '@/pages/SettingsPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<LibraryPage />} />
          <Route path="library/new" element={<NewBookPage />} />
          <Route path="writing" element={<FlowCanvas />} />
          <Route path="manuscripts" element={<ManuscriptsPage />} />
          <Route path="complete" element={<CompletePage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="review" element={<Navigate to="/manuscripts" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
