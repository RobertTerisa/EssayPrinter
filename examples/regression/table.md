# 表格回归

下表为单行表头、多行数据：

| 方法 | 耗时 | 备注 |
|------|------|------|
| Baseline | 12 ms | 单线程 |
| Router/Worker | 7 ms | 4 并发 |
| Optimized | 5 ms | 缓存命中 |
