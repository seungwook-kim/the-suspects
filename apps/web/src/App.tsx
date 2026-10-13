import { useEffect, useState } from 'react'
import type { ClearHistory, CreateOptions, ShareCard } from './api/types'
import { Briefing } from './screens/Briefing'
import { Generating } from './screens/Generating'
import { Finale } from './screens/Finale'
import { History } from './screens/History'
import { Main } from './screens/Main'
import { Result } from './screens/Result'
import { Start } from './screens/Start'
import { useGame } from './state/useGame'
import { getPref, setPref } from './util/saves'

type Screen = 'start' | 'generating' | 'briefing' | 'main' | 'finale' | 'result' | 'history'
type Theme = 'light' | 'dark'

export default function App() {
  const g = useGame()
  const [screen, setScreen] = useState<Screen>('start')
  const [creating, setCreating] = useState(false)
  const [notice, setNotice] = useState<string | null>(null) // 시작 화면에 띄울 안내(거절 사유 등)
  const [job, setJob] = useState<{ text: string; options: CreateOptions; key: number } | null>(null)
  const [result, setResult] = useState<{ history: ClearHistory; card: ShareCard | null } | null>(null)
  const [theme, setTheme] = useState<Theme>(() =>
    getPref<Theme>('theme', window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),
  )

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    setPref('theme', theme)
  }, [theme])

  // 델타가 어긋나면 GET 으로 화면을 다시 맞춘다
  const { needsResync, running } = g.state
  const { resync } = g
  useEffect(() => {
    if (needsResync && !running) void resync()
  }, [needsResync, running, resync])

  const start = async (themeId: string, options: CreateOptions) => {
    setNotice(null)
    setCreating(true)
    setScreen('briefing') // 사건 생성 중에도 빈 로딩 대신 브리핑 장면을 보여 준다
    const ok = await g.startGame(themeId, options)
    setCreating(false)
    if (!ok) setScreen('start')
  }

  const createCase = (text: string, options: CreateOptions) => {
    setNotice(null)
    g.resetAll()
    setJob({ text, options, key: Date.now() })
    setScreen('generating')
  }

  const enter = (view: { phase: string } | null) => {
    if (view) setScreen(view.phase === 'finale' ? 'finale' : view.phase === 'briefing' ? 'briefing' : 'main')
  }
  const openGame = async (gameId: string) => {
    setCreating(true)
    enter(await g.openGame(gameId))
    setCreating(false)
  }
  const loadSlot = async (gameId: string, slotId: string) => {
    setCreating(true)
    enter(await g.load(gameId, slotId))
    setCreating(false)
  }

  const toResult = async () => {
    const r = await g.clearGame()
    if (r) {
      setResult(r)
      setScreen('result')
    }
  }

  const home = () => {
    setNotice(null)
    g.resetAll()
    setResult(null)
    setScreen('start')
  }

  return (
    <>
      <button
        className="theme-toggle"
        onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
        aria-label={theme === 'dark' ? '밝은 테마로' : '어두운 테마로'}
        title="테마 전환"
      >
        {theme === 'dark' ? '☀️' : '🌙'}
      </button>
      {screen === 'start' && (
        <Start
          busy={creating}
          error={notice ?? g.state.error}
          onStart={start}
          onCreateCase={createCase}
          onOpenGame={openGame}
          onLoadSlot={loadSlot}
          onHistory={() => setScreen('history')}
        />
      )}
      {screen === 'generating' && job && (
        <Generating
          key={job.key}
          themeText={job.text}
          options={job.options}
          onReady={(gameId, view) => {
            g.adoptGame(gameId, view)
            enter(view)
          }}
          onRejected={(message) => {
            setNotice(message)
            setScreen('start')
          }}
          onFallback={(themeId) => void start(themeId, job.options)}
          onHome={home}
        />
      )}
      {screen === 'history' && <History onBack={home} />}
      {screen === 'briefing' && <Briefing view={creating ? null : g.state.view} onBegin={() => setScreen('main')} />}
      {screen === 'main' && g.state.view && (
        <Main g={g} onFinale={() => setScreen('finale')} onHome={home} />
      )}
      {screen === 'finale' && g.state.view && (
        <Finale g={g} onBack={() => setScreen('main')} onResult={toResult} />
      )}
      {screen === 'result' && result && (
        <Result h={result.history} card={result.card} onNew={home} onHistory={() => setScreen('history')} />
      )}
    </>
  )
}
