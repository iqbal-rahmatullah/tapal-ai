import { useQuery } from "@tanstack/react-query"
import { ReportPage } from "../components/ReportPage"
import type { ReportData, Story } from "../types"

export default function PrintableReport() {
  const report = useQuery<ReportData>({ queryKey: ["/laporan"] })
  const story = useQuery<Story>({ queryKey: ["/laporan/narasi"] })
  if (report.error) return <p className="p-8 text-sm text-merah">Data laporan gagal dimuat.</p>
  if (!report.data) return null
  return (
    <div className="bg-white print:bg-white">
      <ReportPage d={report.data} story={story.data ?? null} />
    </div>
  )
}
