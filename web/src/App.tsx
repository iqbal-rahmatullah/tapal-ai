import { useQuery } from "@tanstack/react-query"
import LoadingBar from "react-top-loading-bar"
import { Sidebar, TopBar } from "./components/Shell"
import { EmptyState, Toast } from "./components/ui"
import AuditPlan from "./pages/AuditPlan"
import ClaimReview from "./pages/ClaimReview"
import DecisionLog from "./pages/DecisionLog"
import HospitalProfile from "./pages/HospitalProfile"
import IncomingCheck from "./pages/IncomingCheck"
import LineScanner from "./pages/LineScanner"
import Queue from "./pages/Queue"
import PrintableReport from "./pages/PrintableReport"
import Report from "./pages/Report"
import { loadingBar } from "./utils/progress"
import { go, useRoute, type Route } from "./utils/router"
import { useToast } from "./utils/toast"
import type { Queue as QueueData } from "./types"

function Page({ route }: { route: Route }) {
  switch (route.page) {
    case "antrean":
      return <Queue />
    case "rs":
      return <HospitalProfile kode={route.kode} />
    case "klaim":
      return <ClaimReview sep={route.sep} />
    case "cek":
      return <IncomingCheck />
    case "pemindai":
      return <LineScanner />
    case "audit":
      return <AuditPlan />
    case "laporan":
      return <Report />
    case "jejak":
      return <DecisionLog />
    default:
      return (
        <EmptyState icon="file-x" title="Halaman tidak ditemukan">
          Alamat ini tidak ada di TAPAL. Kembali ke <a className="font-semibold text-biru" href="#/antrean">Antrean kerja</a>.
        </EmptyState>
      )
  }
}

function search(text: string) {
  const q = text.trim().toUpperCase()
  if (/^RS-\d+$/.test(q)) go("rs", q)
  else if (q) go("klaim", q)
}

export default function App() {
  const route = useRoute()
  const queue = useQuery<QueueData>({ queryKey: ["/antrean"], enabled: route.page !== "cetak" })
  const toast = useToast()

  if (route.page === "cetak") return <PrintableReport />

  return (
    <>
      <LoadingBar ref={loadingBar} color="#2A78D6" height={3} shadow={false} />
      {toast && <Toast>{toast}</Toast>}
      <div className="flex h-full min-w-360">
        <Sidebar route={route} queueCount={queue.data?.ringkasan.n_ditandai ?? null} />
        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar onSearch={search} />
          <main className="min-h-0 flex-1 overflow-y-auto" key={route.page + JSON.stringify(route)}>
            <Page route={route} />
          </main>
        </div>
      </div>
    </>
  )
}
