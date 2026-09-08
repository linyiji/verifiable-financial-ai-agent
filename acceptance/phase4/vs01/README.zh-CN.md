# Phase 4 VS01 验收门禁

[English](README.md)

本目录仅包含验收基础设施，不导入或修改产品行为。
测试执行前验证冻结契约权威，结果文件将测试框架就绪状态与真实集成 VS01 决定分开记录。

## 测试框架准备

使用 Python 3.11、仓库声明的 PostgreSQL extra、PostgreSQL 16 客户端/服务端工具及 Node 24。
全新 Python/浏览器测试框架的引导步骤：

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev,postgres]'
psql --version  # must identify PostgreSQL 16.x
```

浏览器包由锁文件固定。调用运行器前先引导一次：

```sh
cd acceptance/phase4/vs01/browser
npx --yes --package=node@24.8.0 --call "npm ci"
npx --yes --package=node@24.8.0 --call "npm run install:chromium"
cd ../../../..
```

然后从仓库根目录运行：

```sh
PYTHONPATH=. python3.11 acceptance/phase4/vs01/run_vs01.py self-test \
  --output-dir acceptance/phase4/vs01/out/self-test
```

预期准备结果：

```text
HARNESS_STATUS=READY
VS01_INTEGRATED_STATUS=NOT_RUN
```

合成夹具仅用于 Python/Node 测试框架自测，绝不能满足集成控制项，也不能将 `VS01_INTEGRATED_STATUS` 改为 `PASS`。

## 主协调方集成执行

串行集成 A、B、C 及本验收专用改动后，复制并审查 `integrated-config.example.json`。
使用两个提供方支持的真实公司，并将示例后端、前端、迁移和 C 所有 SSE 采集命令替换为各负责人交付的精确命令。
如果 B 的服务命令要求预构建输出，应在此门禁前运行 B 文档规定的锁文件安装与生产构建命令；X 有意不发明冻结契约中不存在的前端工具链。
缺少负责人提供的命令是阻塞依赖，不是用原型替代的理由。
PostgreSQL 管理 URL 只能通过配置的环境变量提供，绝不能写入 JSON 或命令参数。

```sh
export VS01_POSTGRES_ADMIN_URL='postgresql://<user>:<password>@<host>:<port>/<admin-db>'
PYTHONPATH=. python3.11 acceptance/phase4/vs01/run_vs01.py integrated \
  --config /absolute/path/to/reviewed-vs01-config.json \
  --output-dir acceptance/phase4/vs01/out/integrated
```

运行器：

1. 验证带修订限定的契约回执及全部测试框架自测；
2. 验证 PostgreSQL 服务端主版本为 16，并创建随机专用数据库；
3. 迁移该数据库，启动真实产品后端并检查健康；
4. 通过 X1 创建独立 A/B 资源，在同一数据库/进程/采集会话中调用已跟踪、C 所有的真实场景驱动器，执行身份/错误/SSE 控制，再保留数据库并重启实际后端；
5. 启动两个已审查真实前端命令（主前端和后端不可用边界），准入一个同 Object 的新非终态备用 Run，提供切换/恢复证据，再在 Node 24 下执行 X2 Playwright 旅程；
6. 扫描保留的 API 响应体/头和 SSE 证据；Playwright 同时扫描可见 UI、序列化 DOM、加载源码、网络失败和浏览器错误中的禁止材料；
7. 写入 `PHASE4_VS01_ACCEPTANCE_RESULT.json` 和 `.md`，然后只删除生成的数据库。

服务缺失、PostgreSQL 版本不符、mock/Demo 命令、必需观察缺失、清理失败、候选工作区脏污（含未跟踪文件）、公开界面扫描不完整或必需控制未执行，任何一项都会阻止集成 PASS。
格式错误/不支持的衍生样本仅从摘要固定的真实帧生成，由冻结消费者判定器评估；绝不作为模拟产品响应提供。
最终 PASS 要求所有适用真实采集，而非仅合成自测。

## 绑定运行时的真实 SSE 场景采集

部分恢复和动态案例无法从一条正常路径流中诚实推断。主协调方/C 必须提供 `sse_scenario_capture` 指定的已跟踪驱动器；顶层运行器只在隔离 PostgreSQL 16 数据库和受管后端已运行后调用它。
驱动器只收到门禁所有的回环采集代理源地址和新输出路径；不接收直接后端源地址、数据库 URL、既有 Run ID、进程身份或候选/契约主张。
代理在私有账本中记录不可变请求/响应字节、精确头、顺序、哈希、完成状态和门禁签发的采集 ID。重定向和伪造采集回执失败关闭。

驱动器写入有界 `phase4-vs01-capture-index/v1` 文档，每个必需投影/流槽位仅包含一个唯一门禁签发采集 ID。
可使用门禁专用 `X-VS01-Capture-Cut-After-Complete-Frames` 请求头，在已审计完整帧边界停止 SSE 读取。
运行器独立对照封存账本解析每个 ID，拒绝缺失、重复、未使用、直连、部分或截断证据；从代理 Confirm 流量推导已准入 Run 身份，并重建私有完整证据文档。
绝不接受驱动器自写的响应体、头、摘要、候选元数据和绑定主张。

采集索引必须使用以下精确根结构和场景清单：

```json
{
  "schema_version": "phase4-vs01-capture-index/v1",
  "scenarios": {
    "event_inventory": {"streams": ["CAP-<48 uppercase hex>"]},
    "duplicate": {"before_projection": "CAP-...", "stream": "CAP-..."},
    "ordering_recovery": {"before_projection": "CAP-...", "stream": "CAP-...", "recovered_projection": "CAP-..."},
    "heartbeat": {"before_projection": "CAP-...", "stream": "CAP-..."},
    "terminal_failure": {"stream": "CAP-..."},
    "snapshot_race": {"before_projection": "CAP-...", "stream": "CAP-...", "after_projection": "CAP-..."},
    "sparse_graph_refresh": {"before_projection": "CAP-...", "stream": "CAP-...", "after_projection": "CAP-..."},
    "self_correction": {"before_projection": "CAP-...", "stream": "CAP-...", "after_projection": "CAP-..."},
    "replan_pending": {"before_projection": "CAP-...", "stream": "CAP-...", "after_projection": "CAP-..."},
    "replan_approved": {"before_projection": "CAP-...", "stream": "CAP-...", "after_projection": "CAP-..."}
  }
}
```

占位符仅作解释。`event_inventory` 合计必须包含全部 47 个支持的 V1 事件类型。
标签、驱动器自写摘要或直接后端观察不能获得任何控制项认可。

## 前端 API 绑定

冻结契约不规定运行时配置端点或前端构建系统。因此场景携带两个已审查公开 API 基地址，Playwright 在认定旅程前通过真实请求/响应账本证明实际源地址/路径。
对于本门禁，主 API 基地址精确为运行器管理的后端源地址加 `/api`；不可用 API 基地址精确为运行器确认关闭的源地址加 `/api`。
这排除无关服务证据，但不规定前端如何存储或注入公开基地址。
两个提供服务的前端都必须加载真实非空源码，不得返回夹具/Demo 回退响应。
浏览器对实际获取的源码字节计算哈希，不信任自报构建哈希。

## 仅主协调方集成说明

此处未修改任何仅主协调方可写文件。主协调方须提供 A/B/C 需要的路由/引导/迁移/前端注册和真实启动配置。
X 不提供根脚本或测试注册补丁：文档中的引导加精确运行器命令直接操作隔离路径。

集成前阅读 `DEPENDENCIES_AND_FINDINGS.json`。
X3 强制执行冻结的 `run.failed.failure_stage` 字段和精确 11 值补充约定。

请求的 Git 引用 `phase4/vs01-acceptance` 不能与既有本地/远程 `phase4` 引用共存，因为 Git 不能将一个名称同时存为文件和目录。
Owner 授权的无冲突映射是 `p4-vs01-acceptance` 和 `origin/p4-vs01-acceptance`；原请求名称仍保留在机器可读交付回执中。
