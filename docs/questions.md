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

## Mac 日历为什么是推送到 Surface？

决定：日历数据源是 Mac 上的 macOS Calendar/EventKit，所以由 Mac 的 LaunchAgent 定时运行 `mac/sync_schedule.sh`，导出 `mac/schedule.json` 后用 `scp` 推到 Surface 的 `~/infoscreen/surface/.env/schedule.json`。

原因：Surface/Ubuntu 端没有 macOS EventKit，不能直接读取 Mac Calendar。把 `schedule.json` 放在 `surface/.env/` 可以保持 runtime 数据边界清楚，也避免 `~/infoscreen/schedule.json` 污染仓库根目录。

## Surface IP 改了应该改哪里？

决定：不要改 committed 脚本里的 IP。运行 `bash mac/scripts/setup-schedule-sync.sh --host <surface-ip> --user rody --remote-path '~/infoscreen/surface/.env/schedule.json'`，让它写入本地未提交的 `mac/local.env` 并刷新 LaunchAgent。

原因：IP 是本机部署状态，不是源码。把 IP 写死在 repo 会导致网络变化后定时任务继续推错机器，也会让文档和脚本失去可信度。

## 为什么测试使用 pytest 和 fixture 做本地闭环？

决定：测试使用 pytest，覆盖 backend/API、frontend content、CSS layout contract、runtime fixture、HTTP closed-loop、script/workflow contract。

原因：这个项目需要能在本地、容器、CI runner、agent 环境里重复验证。使用 committed fixture 可以避免测试依赖外网、真实账户或真实 `surface/.env/` 数据。

## 仓库卫生为什么不做成一堆产品单元测试？

决定：仓库卫生主要由目录规则、`.gitignore`、`.githooks/pre-commit`、`scripts/ci/check_repo.py` 和文档里的验证命令约束；产品测试聚焦产品行为和稳定 contract。

原因：产品测试应该证明 dashboard、API、数据和脚本行为正确，不应该变成宽泛的文件树扫描器。源布局规则需要存在，并且 acceptance runner 要执行 repo-wide hygiene check。

## GitHub Actions 关闭时怎么验收？

决定：GitHub Actions 可以由操作者关闭；关闭时缺少 workflow run 不算项目代码失败。

原因：Hosted CI 是否运行是仓库设置问题，不等同于源码是否正确。验收报告需要区分代码问题、文档问题、测试覆盖缺口、运行证据缺口和 CI 未运行。

## 为什么默认不上传测试 artifact？

决定：默认不上传 GitHub Actions artifact，除非明确要求。CI/job log 和本地 runner 输出作为主要证据面。

原因：当前项目更需要 runner、容器和 agent 能直接读到日志，而不是默认把测试结果打包上传。需要可下载产物时再单独开启。
