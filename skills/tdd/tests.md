# Good and Bad Tests

## Good Tests

通过稳定的行为接口测试；能用真实实现获得快速、确定反馈时优先使用。测试层级由目标行为和风险决定，不以“单元”或“集成”的名称判断价值。替身选择见 [mocking.md](mocking.md)。

```typescript
// 好：测试可观察的行为
test("user can checkout with valid cart", async () => {
  const cart = createCart();
  cart.add(product);
  const result = await checkout(cart, paymentMethod);
  expect(result.status).toBe("confirmed");
});
```

特点：

- 测试用户或调用方关心的行为
- 通过模块面向调用方的稳定契约观察行为
- 能经受内部重构
- 描述 WHAT，而非 HOW
- 每个测试聚焦一个行为，可用多个相关断言验证完整结果

## Bad Tests

**Implementation-detail tests**：只验证内部结构，无法说明用户或调用方行为是否正确。下面的内部调用如果不是业务契约，就不足以证明结账成功：

```typescript
// 差：测试 Implementation 的细节
test("checkout calls paymentService.process", async () => {
  const mockPayment = { process: jest.fn() };
  await checkout(cart, mockPayment);
  expect(mockPayment.process).toHaveBeenCalledWith(cart.total);
});
```

危险信号：

- 替换了真正要验证的逻辑，或替身只会重复预期结果
- 测试 private methods
- 断言没有业务含义的内部调用次数或顺序
- 行为没有变化，重构却导致测试失败
- 测试名称描述 HOW 而非 WHAT
- 使用与目标契约无关的内部状态作为成功证据

支付不得重复扣款、发送前必须取得授权等要求，本身就是交互或顺序契约，可以使用相应断言。先指出真实要求，再选择验证方式，不能从当前实现的调用图倒推需求。

```typescript
// 对“用户可以重新读取”的需求不充分：数据库有记录不保证读取接口可用
test("createUser saves to database", async () => {
  await createUser({ name: "Alice" });
  const row = await db.query("SELECT * FROM users WHERE name = ?", ["Alice"]);
  expect(row).toBeDefined();
});

// 对该读取需求：通过调用方接口验证完整行为
test("createUser makes user retrievable", async () => {
  const user = await createUser({ name: "Alice" });
  const retrieved = await getUser(user.id);
  expect(retrieved.name).toBe("Alice");
});
```

若要求就是数据库迁移、持久化格式或第三方消费的数据契约，直接检查 schema 或记录是合理入口；不必绕经可能共享同一错误的读取实现。

**Tautological tests**：期望值重复 Implementation 的计算逻辑，容易与实现犯同样的错误，不能提供独立证据。

```typescript
// 差：按照与代码相同的方式重新计算期望值
test("calculateTotal sums line items", () => {
  const items = [{ price: 10 }, { price: 5 }];
  const expected = items.reduce((sum, i) => sum + i.price, 0);
  expect(calculateTotal(items)).toBe(expected);
});

// 好：期望值是独立且已知的字面值
test("calculateTotal sums line items", () => {
  expect(calculateTotal([{ price: 10 }, { price: 5 }])).toBe(15);
});
```
