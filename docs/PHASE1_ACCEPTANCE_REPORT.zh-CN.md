# Phase 1 验收报告

[English](PHASE1_ACCEPTANCE_REPORT.md)

日期：2026-09-03<br>
基线：Python 3.11 / Node.js 24<br>
数据库目标：PostgreSQL；已验证本地模式：SQLite + SQLAlchemy async

## 结果

- 完整 pytest 套件：75 passed, 0 failed, 0 skipped
- 依赖警告：2 项 TestClient 弃用警告
- Ruff：PASS
- Python compileall：PASS
- 真实 Uvicorn 启动：PASS
- `/health`：HTTP 200
- `/openapi.json`：HTTP 200，18 个路径
- Phase-1 最小验收链：PASS

## 已保存执行证据

运行 `PYTHONPATH=. .venv/bin/python scripts/run_acceptance.py` 可重新生成：

- `artifacts/acceptance/latest/acceptance_summary.json`
- `artifacts/acceptance/latest/runtime_events.json`
- `artifacts/acceptance/latest/calculation_records.json`
- `artifacts/acceptance/latest/canonical_execution_record.json`
- `artifacts/acceptance/latest/released_research_result.json`
- `artifacts/acceptance/latest/financial_report.json`
- `artifacts/acceptance/latest/writeback_proposal.json`
- `artifacts/acceptance/pytest.xml`

这些生成产物刻意由 Git 忽略。生成器和本报告受跟踪；
本地运行产物可能包含特定执行的 ID。

## 延后验收用例

- AC-013 / AC-014：生成能力产品流程
- AC-017：真实 RISC Zero 证明
- AC-026：跨对象比较门

上述内容均明确不在最小 Phase-1 链范围内。ZK 适配器保留 `NOT_IMPLEMENTED`，
绝不将其表述为证明通过。
