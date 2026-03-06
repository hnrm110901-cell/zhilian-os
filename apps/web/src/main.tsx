import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import 'antd/dist/reset.css'
import './styles/variables.css'
import './styles/global.css'
import { injectTokens } from './design-system/tokens/index.ts'

// 注入智链OS Design System CSS 变量（覆盖动态主题相关变量）
injectTokens()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
