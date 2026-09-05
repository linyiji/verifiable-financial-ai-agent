import type { RunStatus, TaskStatus } from "../types/domain";

export const RUN_STATUS_META: Record<RunStatus, { label: string; color: string }> = {
  PLANNING: { label: "研究计划中", color: "blue" },
  RESEARCHING: { label: "研究中", color: "blue" },
  REVIEWING: { label: "质量复核中", color: "amber" },
  GENERATING_REPORT: { label: "报告生成中", color: "blue" },
  RESULT_PREPARING: { label: "结果发布准备中", color: "amber" },
  ACTION_REQUIRED: { label: "需要处理", color: "amber" },
  COMPLETED: { label: "已完成", color: "green" },
  FAILED: { label: "失败", color: "red" }
};

export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  WAITING: "等待中", READY: "可执行", RUNNING: "执行中", SELF_CORRECTING: "自我修正中",
  COMPLETED: "已完成", BLOCKED: "已阻塞", FAILED: "失败"
};
