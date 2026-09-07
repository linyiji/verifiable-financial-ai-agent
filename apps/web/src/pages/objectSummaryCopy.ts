import type { Phase4ResearchObjectDetail } from "../types/domain";

export function objectReleaseSummary(detail: Phase4ResearchObjectDetail): string {
  if (detail.latestReleasedRunId !== null) return "已有发布结果";
  if (detail.releasedResultAvailability.reasonCode === "RELEASED_RUN_LATEST_UNAVAILABLE") {
    return "已有发布记录，最新发布时间不可用";
  }
  return detail.releasedResultAvailability.reasonCode === "NO_RELEASED_RUN"
    ? "尚未发布" : "发布状态不可用";
}

export function missingObjectActivity(detail: Phase4ResearchObjectDetail): string {
  return detail.runCount === 0 ? "尚无 Run 活动。" : "最近活动时间不可用。";
}
