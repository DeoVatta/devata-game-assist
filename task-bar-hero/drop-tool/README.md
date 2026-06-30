# TaskbarHero Drop Tool 🎮

TaskbarHero 游戏开箱掉落预测工具。通过 **Frida** 实时读取游戏进程内存，展示即将掉落的普通/BOSS 箱子奖励内容，无需服务器交互。

---

## 功能

- 实时监测游戏内普通箱（NORMAL）和 BOSS 箱的掉落队列
- 显示即将掉落的 30 个物品（ID + 名称）
- 支持两种使用方式：GUI 图形界面 / CLI 命令行
- 本地只读，不修改游戏内存，纯预测工具

## 使用方式

### 方式一：GUI 版（推荐）

直接双击运行 `drop_items_gui.exe` 即可。

> ⚠️ 可能会被杀毒软件误报为威胁，属于误报（因使用 Frida 注入读取内存）

### 方式二：CLI 版

需要安装 [Frida](https://frida.re)：

```bash
# 先启动 TaskbarHero 游戏
# 然后用 Frida attach 到进程
frida -n TaskbarHero.exe -l drop_items_info_v4.js
```

### 使用时机

1. 进入游戏后，获取**第一个掉落箱子**或**切换地图**
2. 工具会显示接下来即将掉落的 NORMAL / BOSS 箱子奖励队列
3. 切换到不同等级箱子的地图会刷新掉落表

## 工作原理

```
游戏进程 (TaskbarHero.exe)
  │
  ├── Frida 注入 drop_items_info_v4.js
  │
  ├── Hook vw.jsq → 读取 bexl 字典（掉落队列）
  │     └── bexl 存储 EBoxType → List<BoxData> 的预生成队列
  │
  ├── 解码 ObscuredInt（CodeStage AntiCheat 混淆）
  │     └── decoded = (hiddenValue - field_08) ^ field_08
  │
  └── 输出：物品 ID、箱型、队列顺序（共 ~30 个）
```

核心流程：
- 地图加载 → bexl 队列填充 → jsq 从队列取 item[0]
- NORMAL 箱完全客户端同步（无服务器请求），因此可被本地读取
- 加权随机算法（EachDropOneWeight / SelectOneByClass）决定掉落内容

## 注意事项

1. **反作弊风险**：使用 Frida 读取游戏内存，可能会被游戏反作弊系统检测到，介意请勿使用
2. **杀软误报**：GUI 版 exe 使用 Frida 注入技术，可能被部分杀毒软件标记
3. **地图切换**：切换到相同等级箱子的地图不会刷新掉落表；切换到不同等级箱子的地图会刷新
4. **仅读取**：工具只读取内存数据，不修改任何游戏数据

## 文件结构

```
├── drop_items_gui.exe       # GUI 图形界面程序
├── drop_items_info_v4.js    # Frida 注入脚本（CLI 版）
├── 使用指南.txt             # 原始使用说明（中文）
├── README.md                # 本文件（中文）
└── README_EN.md             # English README
```

## 技术依赖

- [Frida](https://frida.re) — 动态插桩框架
- [CodeStage AntiCheat](https://assetstore.unity.com/packages/tools/input-management/antichat-toolkit-3627) — ObscuredInt 混淆（已逆向解码）
- TaskbarHero 游戏（Unity + IL2CPP）

## 相关项目

详细逆向分析报告见 [最终流程图](最终流程图.md)、[开箱逆向报告](开箱逆向报告.md)、[开箱流程图](开箱流程图.md)。

## 免责声明

本工具仅供学习研究目的。使用本工具可能违反游戏服务条款，请自行承担风险。
