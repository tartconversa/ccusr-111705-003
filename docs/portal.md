# 本地来源行为

家电维修目录列出稳定的 `data-key` 和详情路径；详情需由浏览器导航读取，`地址`选择改变当前页面状态，`条款`和`预约预览`是分步出现的可见内容。换地址后旧时段选择可能保留。详情接口是浏览器页面，不是业务 API；运行时只允许访问环回来源。

`fixtures/portal.json` 提供合成业务资料，不包含真实个人数据。`records.save_catalog` 覆盖同一目录身份；`records.save_detail_entries` 以业务键追加入口访问，不把入口访问等同于资格、授权、可预约或正式提交。测试均只访问本地环回页面。

## 地址资格观察（app.eligibility）

`observe_eligibility(origin, item_id, address)` 在浏览器里走完一次完整的资格核对，并把每一步的页面证据与来源 URL 一起落为观察记录：

1. 从目录卡片点击进入详情，记录目录页与详情页两个来源 URL；卡片上的“可预约”只保留为 `catalog_fact`，不参与资格判读。
2. 地址只按精确文本回填，绝不从 `#areas` 联想列表自动挑选相似楼栋；联想项被记录为证据，精确地址不在列表中时标注 `address_not_in_suggestions`。
3. 点击“查询上门范围”后按页面内容等待条款与时段渲染完成（不用固定 sleep），记录 `#address-result`、`#provider`、`#terms` 与 `#visit-slot` 的全部选项。
4. 条款文本含“需确认”时按调用方意图勾选 `#terms-confirmed` 并如实记录；`confirm_terms=False` 可保留“条款未确认”的未确认证据。
5. 时段只选择属于当前已核对地址的选项；无可确认时段时保留空值，若发现旧地址选中态残留则直接报错，不沿用旧状态。
6. 点击预览后读取 `#qualification-preview`；预览指向其他地址时按旧状态串扰处理。
7. `domain.interpret_qualification` 纯函数判读：地址未识别、无可确认时段、条款未确认、预览与地址不一致等任一环节缺失即为 `unconfirmed` 并附原因；证据链齐备才是 `eligible`，且任何结论都带 `orderable=False`，不虚构可下单。

### 会话隔离与可重跑

- 每次观察启动独立浏览器实例并创建全新无痕上下文，结束即关闭；记录 `session_id` 与关闭前的 cookie/存储快照作为隔离证据，不同地址之间不共享 cookie、存储、缓存或页面会话。
- 资格缓存以 `(origin, item_id, 精确地址)` 的哈希键存于 `qualification_observations` 表：同一地址重跑命中自己的缓存直接重放（`cache_hit=True`），不同地址键不同、互不共享；`refresh=True` 强制重跑并只覆盖该地址自己的行。地址不做归一化，“桐花苑 1 栋/2 栋”等相似楼栋天然得到不同键。
- 页面流程的技术性失败（元素缺失、超时等）生成 `technical_error` 的未确认记录，不写入缓存、不污染同地址后续重跑。

### 不提交订单

演练门户没有下单控件；观察过程监听全部网络请求并校验：仅允许环回来源、仅允许 GET，任何写方法或非环回请求都会令观察失败。记录中的 `order_submitted` 由请求证据得出，恒为未提交。`review.review_eligibility` 输出客服可引用的带来源摘要，未确认项附中文原因并明确禁止向客户承诺可预约或可下单。
