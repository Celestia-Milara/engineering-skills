---
name: codebase-design
description: "比较深模块与接口设计（deep modules / interface design / testable seams），决定复杂性归属、模块边界及可测试接缝。需要设计或改进模块接口时使用；普通局部功能或文案修改无需架构设计流程。"
---

# Codebase Design

在明确需要设计或调整模块接口时，用 **deep modules** 的视角比较方案：将相关复杂性封装在易用的 Interface 后，让调用方更容易使用、维护者更容易定位变化。这是一组设计启发式，项目已有约束、真实调用方和本次范围优先，不据此扩展普通功能改动。

替换旧测试前，确认其有效行为、错误路径和回归案例已由新验证承接；不能仅因测试属于旧模块就删除。方案比较不依赖多 agent，环境不支持时在当前会话完成。领域词汇复用项目现有位置，没有词汇表也能继续，不为使用本 skill 新建 CONTEXT.md。

## Glossary

以下术语用于说明设计取舍。优先沿用项目的 component、service、API、boundary 等既有词汇，需要时说明它们与本表的对应关系，不要求改名或统一成新术语。

**Module**：具有 Interface 和 Implementation 的对象，可以是函数、类、package，或跨层的一段功能。先明确本次讨论的规模和调用方。

**Interface**：调用方正确使用 Module 所需了解的契约，包括类型签名、不变量、顺序约束、错误模式、必要配置和性能特征，不限于语言中的 `interface` 关键字。

**Implementation**：Module 内部的内容，也就是它的代码主体。它与 **Adapter** 不同：一个对象可以是 Adapter 很小、Implementation 很大（例如 Postgres repo），也可以是 Adapter 很大、Implementation 很小（例如 in-memory fake）。讨论 Seam 时使用“Adapter”，其他情况使用“Implementation”。

**Depth**：Interface 带来的 Leverage，指调用方（或测试）每掌握一单位 Interface，就能使用多少行为。大量行为藏在精简 Interface 背后的 Module 是 **deep**；Interface 几乎和 Implementation 一样复杂的 Module 是 **shallow**。

**Seam** _(Michael Feathers)_：可以在不修改该位置代码的情况下改变行为的地方，可以位于模块接口或内部依赖替换处。选择替换位置与选择封装哪些行为是两个相关但不同的问题；不要与领域边界混为一谈。

**Adapter**：在 Seam 上满足 Interface 的具体对象。它描述的是*角色*（填补什么位置），而不是内容（内部有什么）。

**Leverage**：调用方从 Depth 中获得的收益。调用方每掌握一单位 Interface，就能获得更多能力。同一份 Implementation 能惠及 N 个调用点和 M 个测试。

**Locality**：维护者从 Depth 中获得的收益。变更、缺陷、知识和验证集中在一个位置，而不是散布到各个调用方。修复一次，处处生效。

## Deep vs shallow

**Deep module**：调用方需要了解的契约较少，能使用的相关行为较多：

```
┌─────────────────────┐
│   Small Interface   │  ← 方法少，参数简单
├─────────────────────┤
│                     │
│  Deep Implementation│  ← 复杂逻辑封装在内部
│                     │
└─────────────────────┘
```

**Shallow module**：接口负担接近其封装的行为，应检查它是否仍带来独立职责、兼容适配或隔离价值：

```
┌─────────────────────────────────┐
│       Large Interface           │  ← 方法多，参数复杂
├─────────────────────────────────┤
│  Thin Implementation            │  ← 仅做转发
└─────────────────────────────────┘
```

设计 Interface 时可以自问：

- 是否可以减少方法数量？
- 是否可以简化参数？
- 是否可以在内部封装更多复杂性？

## Principles

- **Depth 按调用方所需了解的契约衡量。** 不以实现行数、方法数量或合并模块数量代替认知成本；独立复用、职责、所有权和性能约束也可能支持保留小模块。
- **移除模块的思想实验。** 设想去掉该模块后复杂性会消失，还是散落到调用方；同时检查兼容、权限和依赖隔离等价值。这里讨论的是模块的作用，不是删除测试。
- **默认通过稳定的行为接口测试。** 内部子模块也可有自己的稳定契约；为确定性、故障注入或昂贵依赖使用内部替身时，断言仍应针对行为，不把私有调用结构固化成规格，也不为测试暴露私有实现。
- **为实际变化或隔离需求设置 Seam。** 生产与测试 Adapter 是常见依据，但不要求凑足两个实现；说明这层间接性解决了什么实际问题。替身不能代替生产 Adapter 的契约和必要集成验证。

## Designing for testability

好的 Interface 会让测试变得自然：

1. **需要替换的依赖可由调用方注入。** 不必把每个内部对象都参数化。

   ```typescript
   // 易于测试
   function processOrder(order, paymentGateway) {}

   // 难以测试
   function processOrder(order) {
     const gateway = new StripeGateway();
   }
   ```

2. **将纯计算与必要副作用分开。** 状态变更和 I/O 本身也可能是业务契约，应提供可观察结果和验证入口。

   ```typescript
   // 易于测试
   function calculateDiscount(cart): Discount {}

   // 难以测试
   function applyDiscount(cart): void {
     cart.total -= discount;
   }
   ```

3. **减少调用方必须掌握的概念。** 少量清晰入口通常更易用，但一个通用入口也可能隐藏复杂模式；测试范围由行为和风险决定，不由方法数量决定。

## Relationships

- 一个 **Module** 可以面向不同调用方提供不同 **Interface**；本次设计先明确评估哪一份契约。
- **Depth** 是 **Module** 的属性，以其 **Interface** 为基准衡量。
- **Seam** 可以在 **Interface** 上，也可以位于模块内部的依赖替换处。
- **Adapter** 位于 **Seam** 上，并满足 **Interface**。
- **Depth** 为调用方带来 **Leverage**，为维护者带来 **Locality**。

## Avoid misleading shortcuts

- **把 Depth 定义为 Implementation 行数与 Interface 行数的比值**：行数不能代表调用方成本或封装收益。
- **把“Interface”仅理解为 TypeScript 的 `interface` 关键字或类的 public methods**：范围太窄；此处的 Interface 包含调用方必须了解的所有信息。
- **把技术替换点当作领域边界**：明确讨论的是行为契约、依赖替换还是业务职责，沿用项目词汇并消除歧义。

## Going deeper

- **根据依赖调整一组 Module**，参见 [DEEPENING.md](DEEPENING.md)：比较合并收益、依赖替换及测试覆盖承接。
- **探索不同的 Interface 设计**，参见 [DESIGN-IT-TWICE.md](DESIGN-IT-TWICE.md)：按任务规模在当前会话或多个 agent 中比较有实质差异的方案。
