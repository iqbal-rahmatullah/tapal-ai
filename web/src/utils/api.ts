import { QueryClient, type QueryFunctionContext } from "@tanstack/react-query"
import axios, { isAxiosError } from "axios"
import { track } from "./progress"

export const http = axios.create({ baseURL: "/api/v1", timeout: 30_000, headers: { "Content-Type": "application/json" } })

export function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  return track(http.get<T>(path, { signal }).then((r) => r.data))
}

export function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  return track(http.post<T>(path, body, { signal }).then((r) => r.data))
}

function fetchByKey({ queryKey, signal }: QueryFunctionContext): Promise<unknown> {
  return getJson(String(queryKey[0]), signal)
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      queryFn: fetchByKey,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (count, error) => count < 1 && !(isAxiosError(error) && error.response && error.response.status < 500),
    },
  },
})

export function statusOf(error: unknown): number | null {
  return isAxiosError(error) ? (error.response?.status ?? null) : null
}

export function errorText(error: unknown): string {
  const status = statusOf(error)
  if (status === 404) return "Data tidak ditemukan."
  if (status !== null) return `Server menjawab galat ${status}.`
  return "Tidak dapat terhubung ke server TAPAL. Pastikan API berjalan di port 8000."
}
