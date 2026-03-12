import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import * as echarts from 'echarts/core'
import App from './App.tsx'
import 'antd/dist/reset.css'
import './styles/variables.css'
import './styles/global.css'
import { injectTokens } from './design-system/tokens/index.ts'
import { registerTxChartTheme } from './design-system/chartTheme'

// 注入屯象OS Design System CSS 变量（覆盖动态主题相关变量）
injectTokens()

// 注册屯象OS ECharts 主题（light + dark）
registerTxChartTheme(echarts, false)
registerTxChartTheme(echarts, true)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
