# FMP 凭据池配置

[English](FMP_KEY_POOL_CONFIGURATION.md)

将真实 FMP 凭据保存在仓库之外、权限为 `0600` 的本地文件中。
支持的环境变量形式为连续、有限的序列：

```dotenv
FMP_API_KEY_1=
FMP_API_KEY_2=
FMP_API_KEY_3=
FMP_API_KEY_4=
```

启动 API 或验收命令前，将该文件加载到进程环境。编号槽位优先于旧的单个
`FMP_API_KEY`。槽位必须从 `FMP_API_KEY_1` 开始、保持连续，包含互不相同的非空值，
并且绝不能提交到仓库。

FMP 传输保留成功的槽位。HTTP 429 会让该槽位在当前进程内冷却，并尝试下一槽位；
HTTP 401 或 403 会将槽位标为不可用，并尝试下一槽位。其他供应商、网络和数据故障
不会轮换凭据。全部已配置槽位均不可用后，适配器以
`FMP_KEY_POOL_EXHAUSTED` 按失败关闭原则处理。
