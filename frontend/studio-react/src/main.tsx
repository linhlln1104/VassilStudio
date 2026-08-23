import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { setNonce } from 'get-nonce'
import App from './app/App'
import './styles/globals.css'

const styleNonce = document
  .querySelector<HTMLMetaElement>('meta[name="csp-style-nonce"]')
  ?.content.trim()
if (styleNonce) setNonce(styleNonce)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
