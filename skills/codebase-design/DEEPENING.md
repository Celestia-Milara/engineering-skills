# Deepening

说明如何在考虑依赖关系的前提下，安全地加深一组浅层 Module。本文使用 [SKILL.md](SKILL.md) 中的术语：**module**、**interface**、**seam**、**adapter**。

## Dependency categories

评估候选 Module 时，先检查合并能否减少调用方知识和重复变化，再按依赖特点选择验证方式。依赖类别提供线索，不独自决定是否合并或使用替身。

### 1. In-process

纯计算、内存状态、不涉及 I/O。通常容易通过真实实现获得快速反馈；职责紧密时可合并，但独立复用、算法验证或所有权边界可能更适合保留子模块。不因“进程内”就默认合并或新增 Adapter。

### 2. Local-substitutable

存在本地测试替身的依赖（例如 Postgres 的 PGLite、in-memory filesystem）。替身可降低反馈成本，但先确认目标行为所需的事务、并发、扩展或文件语义；替身不能覆盖的部分用真实依赖验证。替换点可以留在内部，无需为了测试把 port 暴露给所有调用方。

### 3. Remote but owned (Ports & Adapters)

跨网络边界的自有服务（例如 microservices、internal APIs）。确有隔离需要时，用 port 表达稳定契约，将 HTTP/gRPC/queue 等传输实现作为 Adapter。内存 Adapter 适合快速验证业务规则，真实 Adapter 仍需覆盖相关序列化、错误映射与调用契约；不能由内存测试通过推断跨服务集成通过。

建议表述示例：*“在 Seam 上定义一个 port，为生产环境实现 HTTP adapter，并为测试实现 in-memory adapter。这样即使系统部署在网络边界两侧，逻辑仍集中在一个 deep Module 中。”*

### 4. Third-party dependencies

第三方服务（例如 Stripe、Twilio）通常需要替身以控制费用、故障或副作用。按真实协议设置返回与错误，并保留适当的契约、沙箱或集成验证。是否拥有依赖不是使用替身的唯一依据；自有依赖也可能需要确定性控制和故障注入。

## Seam discipline

- **每个 Seam 都应有实际理由。** 依赖替换、故障注入、兼容或隔离可以支持引入 port；不以 Adapter 数量作为硬门槛，也不为凑数创建实现。
- **Internal seams 与 external seams。** 替换点可以位于内部；测试仍应验证相应模块的稳定行为，不断言私有调用结构或仅为测试扩大对外接口。

## Testing strategy: preserve useful coverage

- 默认在稳定 Interface 上检查可观察行为。独立算法、属性测试或有价值的故障案例可以继续留在子模块层。
- 删除旧测试前，逐项确认其有效行为、错误路径和回归案例已由新验证承接；只删除重复或仅固化已移除实现结构的测试，不因“旧单测”这一标签成批删除。
- 断言结果和真实交互契约；例如禁止重复扣款、持久化格式或必要操作顺序都可以是行为。内部方法恰好调用几次不自动成为契约。
- 替身测试与生产 Adapter 的验证相互补充。按改动影响执行必要的契约或集成检查；无法执行时明确剩余风险，不把替身通过报告为真实集成通过。
