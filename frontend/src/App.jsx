import Sidebar       from './components/Sidebar'
import ChatPanel     from './components/ChatPanel'
import AgentPanel    from './components/AgentPanel'
import SettingsPanel from './components/SettingsPanel'
import useStore      from './store'
import './App.css'

export default function App() {
  const { mode } = useStore()

  return (
    <div className="app">
      <Sidebar />
      {mode === 'chat'     && <ChatPanel />}
      {mode === 'agent'    && <AgentPanel />}
      {mode === 'settings' && <SettingsPanel />}
    </div>
  )
}