# 发条AI时段小组件 (ai-slot-timer)
<img width="720" height="557" alt="f2749993036ebe81" src="https://github.com/user-attachments/assets/cd2b7c46-02f9-4b0f-919d-04b2f926984a" />

<img width="1112" height="669" alt="image" src="https://github.com/user-attachments/assets/e602d75f-9f61-4975-aac9-58420882deeb" />



一块 Windows 桌面置顶小组件（**深蓝→浅蓝垂直渐变底 + 圆角卡片**，白色文字，带 DeepSeek 鲸鱼 / ChatGPT 螺旋徽章图标），**多页面自动轮播**，帮你安排任务时间：

| 区块 | 内容 |
|---|---|
| **DeepSeek 峰谷计价** | 当前是闲时还是忙时、距下一阶段切换的倒计时、**下一段忙时 + 下一段闲时**时段、账户余额（需 API Key） |
| **ChatGPT 额度重置** | **5 小时窗口**：按首次设置的「下次重置」时刻为锚点自动续算倒计时 + 进度条；**一周窗口**：按首次设置的「重置日期」为锚点自动按 7 天续算，显示下次重置日期与剩余天数 |
| **订阅到期提醒** | 内置「即梦 / Running Hub / 豆包免费 / WorkBuddy 积分」预设 + 自定义订阅：按月续费日（每月 N 日）或固定日期到期（YYYY-MM-DD）两种类型倒计时剩余天数；订阅多了自动增加页面，默认每 60 秒自动轮播一页；到期前 N 天（默认 3，可调）红字每 3 秒闪烁提醒 |
| **API 订阅额度** | 网页设置「API 订阅额度」区：内置 **硅基流动 / MiniMax(mimo) / DeepSeek / 智谱 / 月之暗面 / 火山引擎 / 阿里云百炼 / 腾讯云 / 自定义** 平台模板（名称 + API 地址），下拉选择后输入 API Key 即可**自动查询余额/订阅额度**（硅基流动、MiniMax、DeepSeek 支持一键查询）；无查询接口的平台可登记手动余额；API 条目在订阅页之后新增页面轮播显示 |

## 快速开始

### 安装版（推荐，带桌面图标 + 可选开机启动）

1. 在 [**GitHub Releases**](https://github.com/lilesswoo-ai/ai-slot-timer/releases) 下载 `ai-slot-timer-setup-1.0.0.exe`（约 32MB）。
2. 双击运行安装程序（中文向导，**无需管理员权限**）：
   - 默认安装到 `%LOCALAPPDATA%\发条AI时段小组件`，可改目录
   - **自动创建桌面快捷方式**
   - 勾选「开机自动启动」可让登录 Windows 时自动运行（可选）
3. 安装完成后自动启动小组件；开始菜单也可随时启动。
4. 卸载：开始菜单/设置 → 卸载「发条AI时段小组件」，会同时删除桌面图标与开机启动项。

> 安装版与绿色版功能完全相同，仅分发形态不同（安装版自动建桌面图标、可选开机启动、带卸载程序）。

### 绿色版（免安装）

1. 在 [**GitHub Releases**](https://github.com/lilesswoo-ai/ai-slot-timer/releases) 下载 `ai-slot-timer-v1.0.0-portable.zip`（约 30MB）。
2. 解压到任意目录（建议英文或中文路径均可），例如 `D:\发条AI时段小组件\`。
3. 双击 `发条AI时段小组件.exe` 即启动，**无需安装 Python、无需任何环境依赖**。
4. 首次启动自动生成 `config.json`；可选：复制 `config.example.json` 为 `config.json` 作模板。
5. 主界面右下角齿轮（或右键 →「打开设置（网页）」）会打开**网页版设置页**（浏览器大页面：订阅管理、轮播间隔、提醒天数、声音、开机启动、DeepSeek API Key、ChatGPT 窗口周期等）。

> **绿色版目录结构**：`发条AI时段小组件.exe`（主程序）、`settings.html`（网页设置页，勿删）、`assets/`（图标，勿删）、`short-notification-sound-for-meizu.mp3`（默认提示音，可替换同名文件自定义）、`启动小组件.bat`（备用启动器）、`README.md`、`config.example.json`（配置模板）。
>
> **运行环境**：Windows 7 SP1+ / 10 / 11（64 位），普通用户权限即可，无任何运行时依赖。想换提示音直接替换 `short-notification-sound-for-meizu.mp3`。

### 从源码运行（开发用）

1. 安装 Python 3.9+（勾选 **Add Python to PATH**）。
2. `pip install pillow pystray`（可选，托盘图标）。
3. `pythonw deepseek_chatgpt_timer.py` 启动；`python deepseek_chatgpt_timer.py --selftest` 自检；`--preview [目录]` 可逐页截图验证。
4. 重新打包 exe：`pyinstaller --onefile --noconsole --name "发条AI时段小组件" deepseek_chatgpt_timer.py`，然后把 `settings.html` 复制到 exe 同目录（网页设置页由 exe 旁文件提供）。

> **开机启动**：设置页打开「开机启动：开」后，登录 Windows 时自动启动（写入当前用户注册表 Run 项，可随时关闭）。

> **隐私说明**：`config.json` 保存了你的 DeepSeek API Key、余额与重置锚点等私有数据，已被 `.gitignore` 排除，**不会**被提交到 GitHub。仓库中的 `config.example.json` 是空模板。

## 使用说明

- **拖拽**：按住面板任意位置拖动（按钮除外）。
- **关闭 = 隐藏到托盘**：面板右上角 × 只把窗口隐藏到系统托盘（右下角托盘图标），点托盘图标恢复显示；要真正退出，用右键菜单或托盘菜单里的「退出」。
- **置顶**：标题栏右侧「置顶：开/关」按钮一键切换。
- **ChatGPT 重置时间**：ChatGPT 的额度按「每 N 小时窗口」滚动计数。**只需设置第一次的重置时刻**（点【同步重置时间】输入用量页显示的时刻，例如 12:10），之后每到重置时刻组件会**自动按窗口小时数（默认 5 小时）续算下一次**（12:10 → 17:10 → 22:10 …），全程无需再手动同步；若用量页时刻有偏差，随时重新同步一次即可校正锚点。
- **ChatGPT 一周窗口**：**只需设置第一次的重置日期**（点【同步重置日期】输入用量页「1周」显示的重置日期，例如 09-19），之后每到重置日期组件会**自动按 7 天续算下一次**（09-19 → 09-26 → …）；未设置时按周期模式推算。
- **声音提醒**：设置页开启「DeepSeek 切换提醒 / GPT 重置提醒」后，忙闲切换到达、额度重置到达时会响铃；默认播放 **魅族提示音**（`short-notification-sound-for-meizu.mp3`），「声音」按钮可循环切换 魅族提示音 / 系统提示音 / 叮 / 滴滴 / 三连音。
- **GPT 重置后自动发送**：网页设置开启「GPT 重置后自动发送」后，重置时间到达 **1 分钟后**会自动向 **ChatGPT 电脑端**的当前窗口粘贴「继续任务」并回车发送（相当于自动续上对话）。要求 ChatGPT 桌面端正在运行（窗口标题含 ChatGPT）；找不到窗口时本次自动跳过，不影响后续。默认关闭。
- **DeepSeek 余额**：网页设置 →「DeepSeek API Key」填入在 platform.deepseek.com → API Keys 创建的 Key（保存在本地 config.json，仅用于查询余额），主界面即显示「余额 ¥xx.xx · 可用/余额不足」，每 15 分钟自动刷新。官方接口**未开放今日用量查询**，当日消耗需登录 DeepSeek 控制台「用量信息」页查看（可导出 CSV）。
- **改周期**：网页设置「窗口周期」或右键 →「窗口周期…」可改成 3 / 4 小时等（默认 5，自动续算也按此小时数滚动）。
- **节假日覆盖**：DeepSeek 官方规则是法定节假日全天按闲时计。遇到节假日当天，右键 →「今天强制闲时」，组件当天按全天闲时显示。
- **API 订阅额度**：网页设置 →「API 订阅额度」→ 下拉选择平台模板 → 输入 API Key（可选填「手动余额」）→「＋ 添加 API」。支持一键查询的平台（硅基流动 `user/info`、MiniMax `token_plan/remains`、DeepSeek `user/balance`）每 15 分钟自动刷新余额；无 API Key 直查接口的平台（智谱 / 月之暗面 / 火山引擎 / 阿里云百炼 / 腾讯云）需登录各自控制台查看，可在设置页登记手动余额。新增的 API 条目在订阅到期提醒页之后新增页面显示，与订阅页一起轮播。
- **配置**：位置、周期、重置时间、订阅、声音开关保存在同目录 `config.json`，下次启动自动恢复。
<img width="1173" height="1794" alt="image" src="https://github.com/user-attachments/assets/bba4dc50-4fa1-4432-9c45-d0cadf7c5455" />

## 订阅到期提醒（多页面轮播）

- **添加订阅**：右下角齿轮（或右键 →「打开设置（网页）」）→ 网页设置「订阅到期提醒」区。首次运行已内置 **即梦 / Running Hub / 豆包免费 / WorkBuddy 积分** 四个预设；每个订阅可设为「每月 N 日续费」或「固定日期到期」（如限时权益，填 YYYY-MM-DD），可随时改名、改日、停用或删除，也可自由添加自定义订阅。
- **页面自动增加**：每页最多显示 4 个订阅，订阅多了会自动增加订阅页。
- **轮播**：默认每 **60 秒**自动切到下一页（主界面 → 订阅页 1 → 订阅页 2 → …循环），保证右下角轮换显示时都能看到提醒；点标题栏右侧页码（如 `2/3`）可立即手动切到下一页。轮播间隔可在网页设置里改为 10–3600 秒。
- **红字提醒**：剩余天数 ≤「到期前提醒天数」（默认 3，可设 0–30）时，「剩 X 天 / 今天到期」变为红字，并每 **3 秒**在深红/浅红之间交替闪烁，直到续费日过去。

## 设置页（网页形式）

主界面右下角齿轮（或右键 →「打开设置（网页）」）会打开浏览器里的**网页设置页**（小组件内置本地服务 `http://127.0.0.1:<随机端口>/`，仅本机可访问，关闭网页不影响小组件运行），大页面分区：

| 分区 | 内容 |
|---|---|
| **订阅到期提醒** | 添加 / 改名 / 改续费日或到期日 / 停用 / 删除订阅，内置 即梦、Running Hub、豆包免费、WorkBuddy 积分 预设 + 自定义（支持按月续费与固定日期两种类型） |
| **API 订阅额度** | 下拉选择平台模板（名称 + API 地址）→ 输入 API Key 查余额/订阅额度；支持一键查询：硅基流动、MiniMax(mimo)、DeepSeek；其余平台可登记手动余额；添加/改名/停用/删除 |
| **页面轮播与到期提醒** | 轮播间隔（秒）、到期前红字提醒天数 |
| **声音提醒** | DeepSeek 切换提醒、GPT 重置提醒、提醒声音（魅族/系统/叮/滴滴/三连音）、GPT 重置后自动发送 |
| **DeepSeek** | API Key（余额查询）、忙/闲价格表、高峰时段规则 |
| **ChatGPT 额度重置** | 窗口周期小时数、同步重置时间 / 一周重置日期、清除重置锚点 |
| **通用** | 窗口置顶、开机自动启动 |

> ChatGPT 重置锚点同步一次后自动按窗口小时数 / 7 天续算，无需重复同步。改周期也可用右键菜单 →「窗口周期…」。

## 定价规则（数据来源）

> 高峰时段为北京时间**周一至周五 09:00-12:00、14:00-18:00**，其余为空闲时段，空闲时段价格为高峰时段价格的一半。周末（周六、周日）全天不区分峰谷，统一按闲时计费。
> 价格（元/百万 tokens）：flash 忙 入2/出8、闲 入1/出4；v4-pro 忙 入9/出27、闲 入4.5/出13.5（输入为缓存未命中价）
> 来源：DeepSeek 官方定价页 https://api-docs.deepseek.com/zh-cn/quick_start/pricing/

## 参考项目（GitHub / npm 调研）

本项目没有直接修改现成仓库，而是参考了以下项目的核心思路后自建（纯本地时间计算、零外部 API 依赖）：

- [CodeZeno/Claude-Code-Usage-Monitor](https://github.com/CodeZeno/Claude-Code-Usage-Monitor)（MIT）
  —— Windows 任务栏小组件，5 小时滚动窗口 + 重置倒计时思路的来源。
- [ds-peak-warningx](https://www.npmjs.com/package/ds-peak-warningx)
  —— DeepSeek 峰谷时段判断规则（工作日高峰 01:00-04:00 / 06:00-10:00 UTC，周末全天闲时）。

## 技术说明

- 语言/依赖：**Python 3.9+，tkinter + Pillow + pystray**（渐变背景、品牌图标、系统托盘）；mp3 提示音用 Windows 自带 MCI 播放，无额外依赖。
- 界面：600×400 物理像素、深蓝→浅蓝垂直渐变、圆角卡片、置顶、可拖拽、全 Canvas 绘制、**多页面**（主界面 + 订阅到期提醒页 + API 额度页，默认每 60 秒轮播，页码可点手动切换）。
- 设置页：**网页形式**（小组件内置 127.0.0.1 本地 HTTP 服务，浏览器大页面；配置通过 GET/POST `/api/config` 读写，改动即保存并即时生效）。
- 图标：`assets/deepseek_icon.png`、`assets/chatgpt_icon.png`（28×28 白色圆底徽章）。
- 提示音：`short-notification-sound-for-meizu.mp3`（默认提示音，可替换为同名 wav/mp3）。
- 运行方式：`pythonw deepseek_chatgpt_timer.py`（无窗口）；自检：`python deepseek_chatgpt_timer.py --selftest`。
- 文件清单：
  - `deepseek_chatgpt_timer.py` —— 主程序（可整个文件夹拷贝到任意位置使用）
  - `settings.html` —— 网页设置页（主程序通过本地服务提供）
  - `启动小组件.bat` —— 静默启动脚本
  - `assets/` —— 品牌图标资源
  - `short-notification-sound-for-meizu.mp3` —— 默认提示音
  - `config.json` —— 自动生成，保存位置/周期/重置时间/订阅/声音开关/API Key
  - `widget_main.png` / `widget_settings.png` —— 主界面与设置页效果预览图
