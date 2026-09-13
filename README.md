# 电子斗蛐蛐 · QuQuBattleGame

Windows 桌面宠物养成 + 蛐蛐对战游戏。蛐蛐常驻桌面最上层，打字、点鼠标都会给它涨经验，
后续版本会逐步加入属性、喂食、**斗蛐蛐对战**与收集养成。

详细版本路线见 **[ROADMAP.html](ROADMAP.html)**。

---

## 当前进度

| 版本 | 主题 | 状态 |
|---|---|---|
| v0.1 | 桌宠挂机 + 拖动 + 经验系统 | ✅ 已交付 |
| v0.2 | 属性与状态条 | ⬜ 待开始 |
| v0.3 | 喂食与训练互动 | ⬜ 待开始 |
| v0.4 | 斗蛐蛐对战（核心玩法） | ⬜ 待开始 |
| v0.5 | 擂台挑战与天赋词条 | ⬜ 待开始 |
| v0.6 | 捕捉孵化与图鉴 | ⬜ 待开始 |
| v1.0 | 音效、设置、打包exe | ⬜ 待开始 |

---

## 运行

**方式一（推荐）**：双击 `启动.bat` — 无控制台黑窗，蛐蛐直接出现在屏幕右下角。

**方式二**：`调试模式.bat` — 带控制台，异常会打印并写入 `error.log`。

依赖环境（已装好，路径固定在此）：

```
Python 3.13   C:\Users\Admin\.workbuddy\binaries\python\envs\default\Scripts\pythonw.exe
PySide6-Essentials 6.11.2
pynput
```

> 若换机器需自行安装：`pip install PySide6-Essentials pynput`

## 操作

| 操作 | 效果 |
|---|---|
| 按住蛐蛐拖动 | 拖到屏幕任意位置，松手自动吸附回屏幕内 |
| 打字 | 每个按键 +1 经验 |
| 鼠标左键点击 | 每次 +2 经验 |
| 右键蛐蛐 | 菜单：重置 / 退出 |
| 托盘图标右键 | 同上（蛐蛐被拖丢时的退路） |

经验线：升级所需 = `40 + (等级-1) × 35`。等级与位置存在 `save.json`，关掉再开接着长。

## 目录

```
QuQuBattleGame/
├── main.py        主程序：桌宠窗口、全局键鼠钩子、经验系统、存档
├── cricket.py     蛐蛐本体：动画状态机 + 纯 QPainter 手绘（无图片素材）
├── selftest.py    离屏渲染四种状态并截图，用于验证形象
├── smoke.py       冒烟测试：走一遍完整启动路径，1.2 秒后自动退出
├── live_shot.py   启动桌宠并抓桌面实机截图
├── docs/          各状态预览图
├── 启动.bat       无窗启动
└── 调试模式.bat   带控制台启动
```

## 设计要点

**不干扰正常使用电脑**：窗口设了 `WA_TransparentForMouseEvents`，鼠标点击会穿透蛐蛐落到下层窗口。
拖动不走 Qt 事件，而是用全局钩子（pynput）判断"按下点是否落在蛐蛐身上"，
再在 60fps 定时器里读 `QCursor.pos()` 移动窗口。

**蛐蛐是纯代码画的**：`cricket.py` 里全部用 QPainter 绘制，没有任何图片素材，
不怕打包丢资源，改形象只动这一个文件。

**动画**：呼吸缩放、随机眨眼、每 4~12 秒随机蹦跶/鸣叫/转身；跳跃是真实抛物线物理
（初速 620 重力）；鸣叫时翅膀掀起并高频抖动；吃经验会小幅兴奋。

## 版本提交规范

每个版本一个 commit，tag 打 `v0.1` / `v0.2` ……

```
git commit -m "v0.2: 属性与状态条"
git tag -a v0.2 -m "v0.2 属性与状态条"
```

## 推送到 GitHub

本机 SSH key 已生成：`C:\Users\Admin\.ssh\id_ed25519.pub`

远端仓库：<https://github.com/Wx0823/QuQuBattleGame>

```
git remote add origin git@github.com:Wx0823/QuQuBattleGame.git
git push -u origin main --tags
```

或直接双击 `推送到GitHub.bat`，按提示输入用户名 `Wx0823`。

> 验证 SSH：`ssh -T git@github.com` 应返回 `Hi Wx0823! ...`
