import { createRef } from "react"
import type { LoadingBarRef } from "react-top-loading-bar"

export const loadingBar = createRef<LoadingBarRef>()

let pending = 0

export async function track<T>(action: Promise<T>): Promise<T> {
  if (pending++ === 0) loadingBar.current?.start()
  try {
    return await action
  } finally {
    if (--pending === 0) loadingBar.current?.complete()
  }
}
