# InfoScreen questions

这个文件用问答方式记录会影响项目推进的长期选择。记录的是“决定了什么”和“为什么这么决定”，不是执行流水、临时问题清单、清理记录或归因记录。

## 什么内容应该写进这里？

当实现走不通、测试暴露缺口、验收标准发生变化，并且这些反馈改变了项目方向时，应该把最终形成的项目决策写进来。

写法应该是：先提出项目问题，再回答当前决定和原因。一次性的实现问题直接在代码、测试或配置里修掉，不在这里保留过程。

## 根目录为什么要限制文件？

决定：根目录只放仓库控制文件、文档、项目元数据、测试配置、CI 配置和部署/操作入口。

原因：InfoScreen 是本地长期运行的 kiosk 项目，源码、运行时数据、个人照片、生成物、缓存文件如果混在根目录，会让后续维护和验收很难判断哪些是项目代码、哪些是本机状态。

## 前端入口为什么只能是 `surface/web/index.html` 和 `surface/web/assets/`？

决定：dashboard 的 HTML 入口是 `surface/web/index.html`，CSS 和 JavaScript 放在 `surface/web/assets/` 下。

原因：这样可以避免根目录或 `surface/web/` 下出现重复、过期、不可判断是否仍然生效的前端文件。前端入口越少，后续修改和验收越稳定。

## 运行时数据为什么放在 `surface/.env/`？

决定：天气、日程、市场、本地活动、照片索引、日志等运行时数据放在 `surface/.env/`，用户照片输入放在 `surface/.env/photos/`。

原因：这些内容属于本机状态或个人数据，不是项目源码。源码仓库应该只保存程序、文档、测试 fixture 和部署入口。

## 页面区域为什么必须有唯一 renderer owner？

决定：每个可见 DOM mount 只能有一个数据 renderer。producer job 可以同时产出多个 runtime 文件，也可以被多个 UI 读取；但多个浏览器脚本不能异步重写同一个 DOM。

当前 ownership：

- `dashboard.js`：时钟、页面 uptime、Market card、Market tape、Weather、模拟 metrics。
- `calendar_board.js`：Calendar board。
- `local_event_card.js`：Local event card、sync ticker、EN/FR/ZH news ticker、photo wall。
- `market_custom.js`：Market 配置控件，只调用 API 和 `window.loadMarket()`，不渲染报价。

原因：重复 renderer 会出现正确内容一闪而过，随后被另一套字段、DOM 或 CSS class 覆盖。Market、news 和 sync ticker 都必须通过测试锁定唯一 owner。

## 页面上的数据来源必须怎么记录？

决定：README 和 `docs/design.md` 必须为每个页面区域同时记录 DOM/前端 owner、scheduler/trigger、producer、runtime JSON 或 API、外部/本地数据源以及失败表现。没有后台 job 的 UI 也必须明确写成浏览器本地、模拟值或静态文案。

原因：只有文件名或状态名不足以运维。需要能从页面问题直接追溯到“哪个任务运行、写了什么、从哪里取数、哪个 UI 消费”。同时也要避免把模拟值和静态标签误认为真实监控。

## 哪些页面状态不是真实系统监控？

决定：当前 CPU/MEM/DSK/NET 由 `dashboard.js:updateDemoMetrics()` 使用 `Math.random()` 生成；POWER、DISPLAY、NETWORK、`AC_ONLY`、`ONLINE`、`LAN_OK` 是静态 HTML；`UPTIME` 是浏览器页面会话时长。这些都不是 Surface OS 指标或健康检查。

原因：在没有 producer、runtime schema、HTTP endpoint 和真实 renderer 之前，不得把这些值描述成系统监控。未来实现真实监控时必须同时替换 producer、数据契约、UI 和文档。

## 左侧同步状态分别对应什么任务、产物和界面？

决定：左侧 sync ticker 只监控四个 runtime JSON 的文件新鲜度。每个状态必须能追溯到唯一 producer、产物和 UI consumer。

| 状态 | 触发任务 | Producer | Runtime 产物 | HTTP 路径 | UI consumer |
| --- | --- | --- | --- | --- | --- |
| `SCHEDULE` | Mac LaunchAgent `com.renchili.infoscreen.schedule-sync`，默认每 120 秒 | `mac/export.py` + `mac/sync_schedule.sh` | `surface/.env/schedule.json` | `/schedule.json` | `calendar_board.js` 的 calendar 面板和 `local_event_card.js` 的 sync ticker |
| `WEATHER` | Surface user timer `infoscreen-live-data.timer`，每 5 分钟 | `surface/fetch_live_data.py` | `surface/.env/weather.json` | `/weather.json` | `dashboard.js` 的 weather 面板和 sync ticker |
| `MARKET` | Surface user timer `infoscreen-live-data.timer`，每 5 分钟 | `surface/fetch_live_data.py` | `surface/.env/market.json` | `/market.json` | `dashboard.js` 的 market card、market tape 和 sync ticker |
| `NEWS` | Surface user timer `infoscreen-event-stream.timer`，每 5 分钟 | `surface/fetch_event_stream.py` | `surface/.env/event_stream.json` | `/event_stream.json` | `local_event_card.js` 的 news ticker 和 sync ticker |

原因：状态名称本身不足以定位故障。必须从状态直接找到运行任务、写出的文件以及受影响的 UI，才能避免在错误机器或错误进程上排查。

## `OK`、`STALE`、`MISS`、`ERR` 和 `AGE` 表示什么？

决定：sync ticker 对对应 HTTP 路径执行 `HEAD`，读取服务器返回的 `Last-Modified`，用浏览器当前时间计算 `AGE`。它监控的是 runtime 文件修改时间，不是日历事件时间，也不是 JSON 内部的 `updated_at`。

阈值固定为：`SCHEDULE` 600 秒、`WEATHER` 900 秒、`MARKET` 600 秒、`NEWS` 600 秒。`AGE` 在阈值内为 `OK`；文件存在但超过阈值为 `STALE`；文件不存在或没有 `Last-Modified` 为 `MISS`；请求失败为 `ERR`。

原因：文件新鲜度能统一覆盖 Mac 推送任务和 Surface 本地 timer，同时不要求每种 JSON 使用相同 schema。

## 同步状态异常时怎么处理？

决定：先按状态映射找到 producer，不要先重启整个项目。

- `SCHEDULE STALE/MISS`：在 Mac 检查 LaunchAgent、`mac/local.env` 中的 Surface 地址和 `~/Library/Logs/infoscreen-sync/`；该任务不在 Surface 上运行。
- `WEATHER STALE/MISS` 或 `MARKET STALE/MISS`：在 Surface 检查 `infoscreen-live-data.timer`、`infoscreen-live-data.service` 和 `surface/fetch_live_data.py`。二者由同一个 job 生成，可能一起异常，也可能只有某个 provider 失败。
- `NEWS STALE/MISS`：在 Surface 检查 `infoscreen-event-stream.timer`、`infoscreen-event-stream.service` 和 `surface/fetch_event_stream.py`。
- 任意状态为 `ERR`：先检查 `infoscreen-http.service` 和浏览器到 `/schedule.json`、`/weather.json`、`/market.json`、`/event_stream.json` 的访问，因为 `ERR` 表示监控请求失败，不等同于 producer 一定失败。
- 文件刚更新但 `AGE` 仍明显异常：检查浏览器设备与 Surface 的系统时间；`SCHEDULE` 还要检查 Mac 系统时间。

原因：`STALE/MISS` 通常属于 producer 或产物路径问题，`ERR` 首先属于 HTTP/网络监控链路问题，两类故障不能混在一起处理。

## Market 为什么只能有一个渲染 owner？

决定：`surface/web/assets/js/dashboard.js` 是 `marketList` 和 `globalMarketTapeTrack` 的唯一数据渲染 owner；`market_custom.js` 只负责配置和触发 `window.loadMarket()`；`local_event_card.js` 不得 GET、解析或渲染 `market.json` 内容，也不得写入 Market DOM。它只能为 sync ticker 对 `/market.json` 执行 `HEAD` 以检查 freshness。

原因：多个异步脚本写同一个 DOM 会出现先显示正确结果、随后被另一套旧字段映射和样式覆盖的闪烁问题，无法保证最终 UI 一致。

## 本地活动和照片为什么不属于四个 sync stat？

决定：本地活动由 `infoscreen-local-events.timer` 每 6 小时更新，也可以由 UI POST 搜索触发；照片由用户修改本地文件后手动运行 `surface/build_photos_json.py`。当前 sync ticker 只监控 schedule、weather、market、news，不监控 local events 和 photos。

原因：四个 sync stat 是现有 freshness contract，不代表页面全部 producer。完整页面映射必须在 README 和 design 中列出所有区域，避免把“未出现在 ticker”误解成“没有任务或没有数据来源”。

## 为什么测试使用 pytest 和 fixture 做本地闭环？

决定：测试使用 pytest，覆盖 backend/API、frontend content、CSS layout contract、runtime fixture、HTTP closed-loop、script/workflow contract。

原因：这个项目需要能在本地、容器、CI runner、agent 环境里重复验证。使用 committed fixture 可以避免测试依赖外网、真实账户或真实 `surface/.env/` 数据。

## 仓库卫生为什么不做成一堆产品单元测试？

决定：仓库卫生主要由目录规则、`.gitignore`、`.githooks/pre-commit` 和文档里的验证命令约束；产品测试聚焦产品行为和稳定 contract。

原因：产品测试应该证明 dashboard、API、数据和脚本行为正确，不应该变成宽泛的文件树扫描器。源布局规则需要存在，但它属于仓库治理，不是业务功能。

## GitHub Actions 关闭时怎么验收？

决定：GitHub Actions 可以由操作者关闭；关闭时缺少 workflow run 不算项目代码失败。

原因：Hosted CI 是否运行是仓库设置问题，不等同于源码是否正确。验收报告需要区分代码问题、文档问题、测试覆盖缺口、运行证据缺口和 CI 未运行。

## 为什么默认不上传测试 artifact？

决定：默认不上传 GitHub Actions artifact，除非明确要求。CI/job log 和本地 runner 输出作为主要证据面。

原因：当前项目更需要 runner、容器和 agent 能直接读到日志，而不是默认把测试结果打包上传。需要可下载产物时再单独开启。
