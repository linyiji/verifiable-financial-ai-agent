import { Phase4ApiError } from "../api/client";
import type { Phase4CreateResearchObjectInput } from "../data/FrontendDataSource";

// Manual identity entry, not provider-backed company search or verification.
export function normalizeObjectInput(input: Phase4CreateResearchObjectInput): Phase4CreateResearchObjectInput {
  const result = {
    symbol: input.symbol.trim().toUpperCase(),
    companyName: input.companyName.trim(),
    exchange: input.exchange.trim().toUpperCase(),
    currency: input.currency.trim().toUpperCase(),
    sector: input.sector?.trim() || null
  };
  if (!/^[A-Z0-9][A-Z0-9.-]{0,31}$/u.test(result.symbol)) throw new Error("请输入有效股票代码（字母、数字、点或连字符，最多 32 字符）。");
  if (!result.companyName || result.companyName.length > 200) throw new Error("请输入公司名称（最多 200 字符）。");
  if (!/^[A-Z0-9][A-Z0-9 .-]{0,39}$/u.test(result.exchange)) throw new Error("请输入交易所名称或代码（最多 40 字符）。");
  if (!/^[A-Z]{3}$/u.test(result.currency)) throw new Error("请输入三位计价货币代码。");
  if (result.sector !== null && result.sector.length > 120) throw new Error("行业最多 120 字符，也可留空。");
  return result;
}

export function objectCreationFailure(error: unknown): { message: string; uncertain: boolean } {
  if (error instanceof Phase4ApiError && error.code === "CONFLICT") {
    return { message: "该股票代码已存在，或请求与先前提交冲突。请关闭窗口，在对象列表核对；不同交易所的同一代码目前不能重复创建。", uncertain: false };
  }
  if (error instanceof Phase4ApiError && error.status >= 400 && error.status < 500) {
    return { message: "创建请求未被接受，请检查公司身份字段后重试。", uncertain: false };
  }
  // A lost response may follow a successful commit. Retain the exact request/key.
  return { message: "创建结果尚未确认。请重试同一请求；也可关闭窗口后刷新对象列表核对。不会自动创建研究 Run。", uncertain: true };
}
