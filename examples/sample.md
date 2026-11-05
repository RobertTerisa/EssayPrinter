# 双层架构

本文是一篇面向工程实践的架构思路探讨，并非对 DeepSeek Harness 现有产品功能的介绍。

> 设计的核心矛盾：既要保持全局对话的连续性，又要让高并发执行互不干扰。

## Router 层

为了兼顾连续性与吞吐量，我们可以将「维护全局连续性」与「高并发执行」拆分到两个不同的层级中：由常驻的 **Router 层** 统一承接人类交互与全局协调，由上下文隔离的 Worker 层并发执行具体任务。

![双层架构：Router 层统一负责路由与对外交互，多个 Worker Session 隔离并发执行任务](media/image4.png)

## 实验结果

### 方法

我们对基线实现与 Router/Worker 拆分实现做了一次简单基准测试。

| 方法 | 耗时 | 备注 |
|------|------|------|
| Baseline | 12 ms | 单线程 |
| Router/Worker | 7 ms | 4 并发 |

```python
def route(task):
    return worker_pool.submit(task)
```
