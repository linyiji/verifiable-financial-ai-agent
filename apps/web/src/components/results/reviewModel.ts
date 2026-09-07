import type {
  FinancialReviewCheckV1,
  FinancialReviewSurfaceV1,
  ReviewCheckSelectorV1,
  RunProjection
} from "../../types/domain";

export type FinancialReviewGroupKey = "CALCULATION" | "CLAIM_OUTPUT" | "JUDGMENT" | "PROOF_RELEASE" | "GENERAL";

export interface FinancialReviewGroup {
  readonly groupKey: FinancialReviewGroupKey;
  readonly groupTitle: string;
  readonly groupDescription: string;
  readonly checks: readonly FinancialReviewCheckV1[];
  readonly passCount: number;
  readonly reviewCount: number;
  readonly blockCount: number;
}

type CheckPresentation = Readonly<{
  label: string;
  logic: string;
  groupKey: FinancialReviewGroupKey;
}>;

const CHECK_PRESENTATION: Readonly<Record<string, CheckPresentation>> = {
  FIN_CALCULATION_IDENTITY: { label: "计算身份一致性", logic: "核对计算记录与被复核对象是否保持同一权威身份。", groupKey: "CALCULATION" },
  FIN_CALCULATION_INPUT_SNAPSHOT: { label: "计算输入快照", logic: "检查计算所使用的输入快照是否被明确记录并可追溯。", groupKey: "CALCULATION" },
  FIN_CALCULATION_RECOMPUTATION: { label: "计算重算一致性", logic: "依据已记录输入执行可观察的确定性重算检查。", groupKey: "CALCULATION" },
  FIN_MATERIAL_FORMULA_CLOSURE: { label: "重要公式闭包", logic: "检查重要财务公式是否完成输入、计算与结果闭包。", groupKey: "CALCULATION" },
  FIN_METRIC_BINDING: { label: "指标绑定", logic: "核对发布指标与其计算记录之间的精确绑定。", groupKey: "CLAIM_OUTPUT" },
  FIN_CLAIM_SUPPORT: { label: "结论支持", logic: "检查发布结论是否由精确计算与声明对象共同支持。", groupKey: "CLAIM_OUTPUT" },
  FIN_TYPED_RELEASE_CARDINALITY: { label: "发布对象完整性", logic: "检查发布包中的类型化财务对象数量是否满足发布约束。", groupKey: "CLAIM_OUTPUT" },
  FIN_JUDGMENT_SUPPORT: { label: "财务判断支持", logic: "检查财务判断是否具有权威对象支持，且没有脱离可观察记录。", groupKey: "JUDGMENT" },
  FIN_PROOF_REQUIREMENT_CLOSURE: { label: "证明与发布门槛", logic: "检查适用的证明要求是否在发布前完成闭包。", groupKey: "PROOF_RELEASE" }
};

const GROUP_META: readonly Readonly<{ key: FinancialReviewGroupKey; title: string; description: string }>[] = [
  { key: "CALCULATION", title: "计算完整性", description: "核对计算身份、输入快照、重算结果与重要公式闭包。" },
  { key: "CLAIM_OUTPUT", title: "指标与结论", description: "核对发布指标、计算记录与对外结论之间的精确绑定。" },
  { key: "JUDGMENT", title: "财务判断", description: "核对财务判断是否具有可观察、可追溯的支持。" },
  { key: "PROOF_RELEASE", title: "证明与发布门槛", description: "核对证明要求及发布前的完整性约束。" },
  { key: "GENERAL", title: "其他复核", description: "呈现未被当前业务分类覆盖的真实复核记录。" }
];

export function reviewSelectorKey(selector: ReviewCheckSelectorV1): string | null {
  const sorted = [...selector.subjectRefs].sort();
  if (selector.subjectRefs.length === 0 || selector.subjectRefs.some((ref, index) => ref !== sorted[index])) return null;
  return JSON.stringify([selector.reviewId, selector.checkCode, sorted]);
}

export function resolveExactReviewCheck(
  review: FinancialReviewSurfaceV1,
  selector: ReviewCheckSelectorV1
): FinancialReviewCheckV1 | null {
  const requestedKey = reviewSelectorKey(selector);
  if (requestedKey === null || selector.reviewId !== review.reviewId) return null;
  const matches = review.checks.filter((check) => reviewSelectorKey(check.selector) === requestedKey);
  return matches.length === 1 ? matches[0] : null;
}

export function checkPresentation(checkCode: string): CheckPresentation {
  return CHECK_PRESENTATION[checkCode] ?? {
    label: "其他权威检查",
    logic: "按持久化检查代码执行可观察的业务规则；当前公共契约未提供更细的安全说明。",
    groupKey: "GENERAL"
  };
}

export function groupFinancialReview(review: FinancialReviewSurfaceV1): readonly FinancialReviewGroup[] {
  const buckets = new Map<FinancialReviewGroupKey, FinancialReviewCheckV1[]>();
  for (const check of review.checks) {
    const key = checkPresentation(check.selector.checkCode).groupKey;
    const bucket = buckets.get(key) ?? [];
    bucket.push(check);
    buckets.set(key, bucket);
  }
  return GROUP_META.flatMap((meta) => {
    const checks = buckets.get(meta.key);
    if (checks === undefined || checks.length === 0) return [];
    const ordered = [...checks].sort((left, right) => {
      const code = left.selector.checkCode.localeCompare(right.selector.checkCode);
      return code === 0 ? left.selector.subjectRefs.join("\u0000").localeCompare(right.selector.subjectRefs.join("\u0000")) : code;
    });
    return [{
      groupKey: meta.key,
      groupTitle: meta.title,
      groupDescription: meta.description,
      checks: ordered,
      passCount: ordered.filter((check) => check.status === "PASS").length,
      reviewCount: ordered.filter((check) => check.status === "REVIEW").length,
      blockCount: ordered.filter((check) => check.status === "BLOCK").length
    }];
  });
}

export function exceptionReviewChecks(review: FinancialReviewSurfaceV1): readonly FinancialReviewCheckV1[] {
  return review.checks.filter((check) => check.status !== "PASS");
}

export function reviewHasObservableMachineRelation(check: FinancialReviewCheckV1): boolean {
  return check.outputRefs.some((ref) => ref.status === "AVAILABLE" && ref.targetRef !== null);
}

export function reviewGateSatisfied(projection: RunProjection, reviewSurface: FinancialReviewSurfaceV1 | null = null): boolean {
  if (reviewSurface !== null) {
    return reviewSurface.runId === projection.run.runId &&
      reviewSurface.objectId === projection.object.objectId &&
      reviewSurface.reviewId === projection.review.reviewId &&
      reviewSurface.availability.status === "READY" &&
      reviewSurface.verdict === "PASS";
  }
  return projection.review.availability.status === "AVAILABLE" && projection.review.status === "PASS";
}

export function subjectKind(ref: string): string {
  if (ref.startsWith("CALC-")) return "计算";
  if (ref.startsWith("CLAIM-")) return "结论";
  if (ref.startsWith("METRIC-")) return "指标";
  if (ref.startsWith("JUDGMENT-")) return "判断";
  if (ref.startsWith("EVIDENCE-")) return "证据";
  return "对象";
}
