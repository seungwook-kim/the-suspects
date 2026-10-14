import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// 글꼴은 앱에 포함한다(SIL OFL 1.1). 한글 본문 IBM Plex Sans KR, 숫자·시각은 Nanum Gothic Coding(영문·숫자판)
import '@fontsource/ibm-plex-sans-kr/400.css'
import '@fontsource/ibm-plex-sans-kr/700.css'
import '@fontsource/nanum-gothic-coding/latin-400.css'
import '@fontsource/nanum-gothic-coding/latin-700.css'
import './index.css'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
