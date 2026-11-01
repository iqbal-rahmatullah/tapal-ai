import "@fontsource/inter/400.css"
import "@fontsource/inter/500.css"
import "@fontsource/inter/600.css"
import "@fontsource/inter/700.css"
import "@fontsource/jetbrains-mono/400.css"
import "@fontsource/jetbrains-mono/500.css"
import "@fontsource/jetbrains-mono/600.css"
import "@fontsource/plus-jakarta-sans/600.css"
import "@fontsource/plus-jakarta-sans/700.css"
import { QueryClientProvider } from "@tanstack/react-query"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { queryClient } from "./utils/api"
import App from "./App"
import "./index.css"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
