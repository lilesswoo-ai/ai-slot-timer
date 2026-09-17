# 发条AI时段小组件 (ai-slot-timer)
<img width="615" height="420" alt="image" src="https://github.com/user-attachments/assets/8699c1de-f57a-4460-bc52-35cb24670376" />

一块 Windows 桌面置顶小组件（**深蓝→浅蓝垂直渐变底 + 圆角卡片**，白色文字，带 DeepSeek 鲸鱼 / ChatGPT 螺旋徽章图标），同时显示两件事，帮你安排任务时间：

| 区块 | 内容 |
|---|---|
| **DeepSeek 峰谷计价** | 当前是闲时还是忙时、距下一阶段切换的倒计时、**下一段忙时 + 下一段闲时**时段、账户余额（需 API Key） |
| **ChatGPT 额度重置** | **5 小时窗口**：按首次设置的「下次重置」时刻为锚点自动续算倒计时 + 进度条；**一周窗口**：按首次设置的「重置日期」为锚点自动按 7 天续算，显示下次重置日期与剩余天数 |

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
5. 主界面右下角齿轮 → **设置页**（声音提醒、开机启动、DeepSeek API Key 余额配置）。

> **绿色版目录结构**：`发条AI时段小组件.exe`（主程序）、`assets/`（图标，勿删）、`short-notification-sound-for-meizu.mp3`（默认提示音，可替换同名文件自定义）、`启动小组件.bat`（备用启动器）、`README.md`、`config.example.json`（配置模板）。
>
> **运行环境**：Windows 7 SP1+ / 10 / 11（64 位），普通用户权限即可，无任何运行时依赖。想换提示音直接替换 `short-notification-sound-for-meizu.mp3`。

### 从源码运行（开发用）

1. 安装 Python 3.9+（勾选 **Add Python to PATH**）。
2. `pip install pillow pystray`（可选，托盘图标）。
3. `pythonw deepseek_chatgpt_timer.py` 启动；`python deepseek_chatgpt_timer.py --selftest` 自检。
4. 重新打包 exe：`pyinstaller --onefile --noconsole --name "发条AI时段小组件" deepseek_chatgpt_timer.py`。

> **开机启动**：设置页打开「开机启动：开」后，登录 Windows 时自动启动（写入当前用户注册表 Run 项，可随时关闭）。

> **隐私说明**：`config.json` 保存了你的 DeepSeek API Key、余额与重置锚点等私有数据，已被 `.gitignore` 排除，**不会**被提交到 GitHub。仓库中的 `config.example.json` 是空模板。

## 使用说明

- **拖拽**：按住面板任意位置拖动（按钮除外）。
- **关闭 = 隐藏到托盘**：面板右上角 × 只把窗口隐藏到系统托盘（右下角托盘图标），点托盘图标恢复显示；要真正退出，用右键菜单或托盘菜单里的「退出」。
- **置顶**：标题栏右侧「置顶：开/关」按钮一键切换。
- **ChatGPT 重置时间**：ChatGPT 的额度按「每 N 小时窗口」滚动计数。**只需设置第一次的重置时刻**（点【同步重置时间】输入用量页显示的时刻，例如 12:10），之后每到重置时刻组件会**自动按窗口小时数（默认 5 小时）续算下一次**（12:10 → 17:10 → 22:10 …），全程无需再手动同步；若用量页时刻有偏差，随时重新同步一次即可校正锚点。
- **ChatGPT 一周窗口**：**只需设置第一次的重置日期**（点【同步重置日期】输入用量页「1周」显示的重置日期，例如 09-19），之后每到重置日期组件会**自动按 7 天续算下一次**（09-19 → 09-26 → …）；未设置时按周期模式推算。
- **声音提醒**：设置页开启「DeepSeek 切换提醒 / GPT 重置提醒」后，忙闲切换到达、额度重置到达时会响铃；默认播放 **魅族提示音**（`short-notification-sound-for-meizu.mp3`），「声音」按钮可循环切换 魅族提示音 / 系统提示音 / 叮 / 滴滴 / 三连音。
- **GPT 重置后自动发送**：设置页开启「GPT 重置后自动发送」后，重置时间到达 **1 分钟后**会自动向 **ChatGPT 电脑端**的当前窗口粘贴「继续任务」并回车发送（相当于自动续上对话）。要求 ChatGPT 桌面端正在运行（窗口标题含 ChatGPT）；找不到窗口时本次自动跳过，不影响后续。默认关闭。
- **DeepSeek 余额**：设置页 →「设置 DeepSeek API Key」填入在 platform.deepseek.com → API Keys 创建的 Key（保存在本地 config.json，仅用于查询余额），主界面即显示「余额 ¥xx.xx · 可用/余额不足」，每 15 分钟自动刷新。官方接口**未开放今日用量查询**，当日消耗需登录 DeepSeek 控制台「用量信息」页查看（可导出 CSV）。
- **改周期**：设置页「窗口周期」或右键 →「窗口周期…」可改成 3 / 4 小时等（默认 5，自动续算也按此小时数滚动）。
- **节假日覆盖**：DeepSeek 官方规则是法定节假日全天按闲时计。遇到节假日当天，右键 →「今天强制闲时」，组件当天按全天闲时显示。
- **配置**：位置、周期、重置时间、声音开关保存在同目录 `config.json`，下次启动自动恢复。

## 设置页内容

与主界面同尺寸（600×400），右上角 ← 返回主界面：

| 分区 | 内容 |
|---|---|
| **声音提醒** | DeepSeek 切换提醒开关、GPT 重置提醒开关、提醒声音选择（魅族提示音/系统提示音/叮/滴滴/三连音，默认魅族提示音） |
| **DeepSeek 价格表** | Flash / Pro 在忙时与闲时的输入输出价格（元/百万 tokens，输入为缓存未命中价）+ 高峰时段规则 |
| **DeepSeek 余额** | 设置 API Key 后主界面实时显示账户余额（15 分钟刷新）；官方接口仅开放余额，今日用量请到 platform.deepseek.com 控制台查看 |

> ChatGPT 重置的相关设置已从设置页移除：**在主界面「同步重置时间」设置一次后，组件自动按 5 小时续算**，无需再手动同步。改周期仍可用右键菜单 →「窗口周期…」。

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
- 界面：600×400 物理像素、深蓝→浅蓝垂直渐变、圆角卡片、置顶、可拖拽、全 Canvas 绘制、双页面（主界面/设置页）。
- 图标：`assets/deepseek_icon.png`、`assets/chatgpt_icon.png`（28×28 白色圆底徽章）。
- 提示音：`short-notification-sound-for-meizu.mp3`（默认提示音，可替换为同名 wav/mp3）。
- 运行方式：`pythonw deepseek_chatgpt_timer.py`（无窗口）；自检：`python deepseek_chatgpt_timer.py --selftest`。
- 文件清单：
  - `deepseek_chatgpt_timer.py` —— 主程序（可整个文件夹拷贝到任意位置使用）
  - `启动小组件.bat` —— 静默启动脚本
  - `assets/` —— 品牌图标资源
  - `short-notification-sound-for-meizu.mp3` —— 默认提示音
  - `config.json` —— 自动生成，保存位置/周期/重置时间/声音开关/API Key
  - `widget_main.png` / `widget_settings.png` —— 主界面与设置页效果预览图
