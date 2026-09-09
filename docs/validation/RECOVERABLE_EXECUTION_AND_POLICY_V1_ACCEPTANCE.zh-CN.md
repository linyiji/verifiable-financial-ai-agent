# 统一恢复与决策治理 V1 — 离线验收

[English](RECOVERABLE_EXECUTION_AND_POLICY_V1_ACCEPTANCE.md) ·
[架构及接入边界](../architecture/RECOVERABLE_EXECUTION_AND_POLICY_V1.zh-CN.md) ·
[版本化策略](../architecture/OWNER_POLICY_V1.zh-CN.md)

日期：2026-09-09。结果：**PARTIAL / OFFLINE_IMPLEMENTATION**。
基线：`ea2002ca571c869c59936f64067ec0d7c7eaabd1`。
分支：`codex/recoverable-execution-policy-v1`。本地提交后，精确候选 SHA/TREE
写入本地 FINAL_RECEIPT；本轮不发布。

## 实测门禁

- V1/FMP/策略专项148个参数化用例通过，与全量后端重叠，不另加为独立用例。
- 全后端1720通过、20跳过、0失败；有2条依赖弃用提示。
- 独立隔离 PostgreSQL 门11通过：补跑全量因默认 SQLite Settings 跳过的3项，
  并覆盖迁移链与真实 Memory 仓储；其余8项与全量重叠。
  合并为1723个通过的测试 node ID，另17个可选用例未执行，不代表研究执行数量。
- 前端21个 `scripts/*.test.mjs` 程序全部通过，打印的内部断言数不混入后端计数；
  TypeScript/Vite build 通过。
- 最终本地门包含 Ruff、修改的 Bash 语法/ShellCheck、新增双语链接、diff、
  有限秘密模式及路径扫描。安装脚本旧 SC2016 是故意保存未来 shell 的字面 PATH
  语句；ShellCheck warning/error 门不将该 info 误判为错误。
- Docker build-context 实测排除了假 credentials、`.env`、`.vfacred`、`.git`、
  node_modules、dist 与 artifacts；构建 RUN 使用 `--network none`。

17个可选未执行用例：8个真实 RISC Zero receipt（本轮禁止真实 Proof），9个需要
Docker daemon 的 Sandbox/生成流水线用例（测试容器不暴露主机 Docker socket）。
Fake Proof/Sandbox、锁定工件/输入、安装器与 A/B/C 回归仍在通过的全量中。
不能据此宣称真实 Proof 或真实 Sandbox 隔离验收通过。PowerShell 原生执行为
NOT_OBSERVED，Windows 仅有 Python/脚本合同夹具覆盖。

## 隔离及复现

`scripts/recovery_v1_offline.py` 生成脱敏源码快照，不复制明文 Registry、真实
加密包、`.env`、数据库和原 `.git`。测试容器创建独立 Git index，静态工件校验
只看此份源码。依赖安装在专用 `tests/offline/Dockerfile.recovery-v1` 镜像中，
不变更正在运行的产品。

Docker internal 网络 `vfa-recovery-v1-offline` 无外部默认路由、主机端口或
Docker socket；测试容器 drop capabilities / no-new-privileges。仅可访问新建
tmpfs PostgreSQL16，host=postgres，database=recovery_v1_isolated。
使用显式假凭据，准入组合夹具在可取消的假 HTTP 边界等待，不制造金融或模型成功结果。

容器内依次运行专项与 `python -m pytest -q`。独立 PostgreSQL 门将 DATABASE_URL
设为同一个显式隔离 TEST_POSTGRESQL_URL，执行 test_postgresql_runtime.py、
test_generated_artifact_migration.py、test_resume_memory_postgresql.py。
前端使用 Node24、锁定 npm 依赖、测试专用 TypeScript loader 与 `npm run build`。
禁止将这些测试指向投资人或开发历史数据库。

迁移0016只应用到新隔离库，新增 V1 账本表，不回填历史合同/预算/epoch。
回退关闭新动作、保留记录，不破坏性降级。旧记录缺合同保持不可恢复。

## 回归发现的修正

产品：403端点拒绝污染凭据；200错误体限流未排除槽位；构造后显式预算覆盖的优先级；
上下文裁剪丢失金融语义。C03初版过度保留无关文案，触发现有上限，已由原产品投影
用例发现并修正，没有调高上限制造通过。

环境：补齐 Node/Git/OpenTelemetry、隔离 PostgreSQL、假供应商配置、脱敏 Git index。
陈旧夹具：实际迁移头0016、读取明确配置的库名/用户而非开发库字面值，以及固定仅测
准入的异步生产者以比较同一序列快照。没有删测试或降低 Required/Review/Proof/Release。

## 接受范围与剩余项

离线证据覆盖 FMP 分域健康、策略/文档一致性、物理预留、lease/epoch fencing、
checkpoint v2、保存结果对账、原 Scheduler 重投递、单次失败授权和真实 Memory
仓储事务守卫。已发送未知结果禁止重发，不宣称供应商 external exactly-once。
模型提案需要独立 DECIDER 权限、默认 OFF；默认仍为确定性 supervisor。
API/UI 组件尚未挂载到默认产品。

生产准入、动态批准事务、全部物理传输、旧投影表桥接和启动扫描器仍未完整接入。
Helper 测试通过不能关闭这些缺口；未认证或发布新运行镜像。
暂停、任意分支重做、自动补证据、再认证仍为延后范围。

历史305a保留已完成计算事件引用；保存投影不能确定缺失计算的规范身份及分支要求来源，
仍为 NOT_OBSERVED，因果结论 **NOT_PROVEN**，原 FAILED 状态不变。
原审计及 SHA256 清单保留。夹具 Run ID 是隔离模拟数据、不算 Live；未汇总其总数。

真实 Provider / 新真实 Run / 真实 Proof / Keychain / 解密 / 生产迁移均为0；
历史数据未修改；未 push。

证据目录：`artifacts/recoverable_execution_policy_v1/`。
Owner审阅就绪 YES；单独授权Live就绪 NO；生产 NOT_CERTIFIED；Phase6B NOT_DECIDED。

NEXT_EXACT_ACTION = OWNER_REVIEW_V1_AND_AUTHORIZE_BOUNDED_ACCEPTANCE。
本轮到此停止，不恢复历史 Run、不执行 Live、不发布、不开始 Phase6B。
