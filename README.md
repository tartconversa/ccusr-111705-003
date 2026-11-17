# 上门服务的地址资格与可约时段核验

这是家电维修资料的本地演练门户与目录采集器。演练数据仅在环回地址提供，不会操作真实用户、订单或商户。当前 `app.capture.read_catalog` 读取目录；`app.capture.read_detail_entry` 走卡片到详情并接收可选业务选择，`app.domain.interpret_entry` 确认业务身份，`app.records.save_detail_entries` 追加详情入口收据。

面向客服回复的完整资格核对由 `app.eligibility.observe_eligibility` 承担：它在独立浏览器会话里走完地址输入、上门范围查询、条款确认、时段选择与资格预览，输出带来源 URL 的观察记录；`app.domain.interpret_qualification` 只依据页面证据判读，证据不足一律 `unconfirmed`，任何结论都不等同于可下单，也不会提交订单。同一 `(来源, 业务, 精确地址)` 的观察可经 SQLite 缓存重跑，不同地址使用不同缓存键与全新无痕页面会话，互不共享。流程与边界见 `docs/portal.md`。

页面有分步交互，测试时从本地任意空闲端口启动演练站点。安装锁定依赖并准备 Chromium 后：

- `python -m unittest discover -s tests -v`：运行基线浏览器与资格观察测试。
- `python -m compileall -q app tests`：检查代码。
- `python -m app.site`：启动本地演练站点。
- `python -m app.cli`：另一个终端观察目录输出。
- `python -m app.cli observe <item_id> <地址> [--origin URL] [--cache PATH] [--refresh]`：对单个地址执行一次带来源的资格观察并打印客服摘要。

两个终端命令用于人工演示，自动测试不依赖固定端口。
