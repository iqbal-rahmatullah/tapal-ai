import type { IconType } from "react-icons"
import {
  LuArrowDown, LuArrowRight, LuArrowUp, LuBan, LuCalendar, LuChartColumn, LuCheck, LuChevronDown, LuChevronLeft, LuChevronRight, LuCircle,
  LuCircleAlert, LuCircleCheck, LuCircleDashed, LuCircleDot, LuCircleHelp, LuCircleX, LuClipboardCheck, LuClipboardList, LuCode, LuCopy,
  LuCornerDownRight, LuDownload, LuFastForward, LuFile, LuFileCheck, LuFileDown, LuFilePenLine, LuFilePlus, LuFileSearch, LuFileText,
  LuFileX, LuFlaskConical, LuGitBranch, LuHistory, LuHourglass, LuInfo, LuList, LuListChecks, LuLoaderCircle, LuLock, LuMail, LuMapPin,
  LuMessageSquare, LuMinus, LuPencil, LuRefreshCw, LuRotateCcw, LuRotateCw, LuRoute, LuRuler, LuScanSearch, LuSearch, LuSend, LuServer,
  LuShieldCheck, LuShieldX, LuShuffle, LuTextQuote, LuTimer, LuTrendingUp, LuTriangleAlert, LuUserRound, LuUserRoundCheck, LuX, LuZap,
} from "react-icons/lu"

export const ICONS = {
  "arrow-down": LuArrowDown, "arrow-right": LuArrowRight, "arrow-up": LuArrowUp, ban: LuBan, calendar: LuCalendar,
  "chart-column": LuChartColumn, check: LuCheck, "chevron-down": LuChevronDown, "chevron-left": LuChevronLeft,
  "chevron-right": LuChevronRight, circle: LuCircle, "circle-alert": LuCircleAlert, "circle-check": LuCircleCheck,
  "circle-dashed": LuCircleDashed, "circle-dot": LuCircleDot, "circle-question-mark": LuCircleHelp, "circle-x": LuCircleX,
  "clipboard-check": LuClipboardCheck, "clipboard-list": LuClipboardList, code: LuCode, copy: LuCopy, "corner-down-right": LuCornerDownRight,
  download: LuDownload, "fast-forward": LuFastForward, file: LuFile, "file-check": LuFileCheck, "file-down": LuFileDown,
  "file-pen-line": LuFilePenLine, "file-plus": LuFilePlus, "file-search": LuFileSearch, "file-text": LuFileText, "file-x": LuFileX,
  "flask-conical": LuFlaskConical, "git-branch": LuGitBranch, history: LuHistory, hourglass: LuHourglass, info: LuInfo, list: LuList,
  "list-checks": LuListChecks, loader: LuLoaderCircle, lock: LuLock, mail: LuMail, "map-pin": LuMapPin, "message-square": LuMessageSquare,
  minus: LuMinus, pencil: LuPencil, "refresh-cw": LuRefreshCw, "rotate-ccw": LuRotateCcw, "rotate-cw": LuRotateCw, route: LuRoute,
  ruler: LuRuler, "scan-search": LuScanSearch, search: LuSearch, send: LuSend, server: LuServer, "shield-check": LuShieldCheck,
  "shield-x": LuShieldX, shuffle: LuShuffle, "text-quote": LuTextQuote, timer: LuTimer, "trending-up": LuTrendingUp,
  "triangle-alert": LuTriangleAlert, "user-round": LuUserRound, "user-round-check": LuUserRoundCheck, x: LuX, zap: LuZap,
} satisfies Record<string, IconType>

export type IconName = keyof typeof ICONS

export const CHECK_ICON: Record<string, IconName> = { jejak: "history", kemiripan: "copy", jam: "timer" }
