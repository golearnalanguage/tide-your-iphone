# tide your iPhone

通用的本地应用清单与使用排名工具。给任意一台 USB iPhone、iPad 或 iPod
读取当前安装清单，再把已有的使用统计关联到 App 名称。

支持 Python 3.9 及以上。工具本身使用标准库；连接设备时，单独调用已安装的
`pymobiledevice3`。离线导入、排名关联和 SHA-256 校验可以独立运行。

## 快速开始

进入本项目目录即可运行：

```bash
python3 -m tide_your_iphone --help
python3 -m tide_your_iphone devices
python3 -m tide_your_iphone probe --output-dir data/my-phone
```

`pymobiledevice3` 从 `--pmd3`、环境变量 `TIDE_PMD3`、`PATH` 或当前 Python
环境依次查找。例如它位于另一个虚拟环境：

```bash
python3 -m tide_your_iphone devices --pmd3 /path/to/device-env/bin/pymobiledevice3
python3 -m tide_your_iphone probe \
  --pmd3 /path/to/device-env/bin/pymobiledevice3 \
  --output-dir data/my-phone
```

设备需通过 USB 连接、解锁，并已信任电脑。清单读取调用 `usbmux list` 与
`apps list`，应用大小计算和占位应用均关闭。

已实测的设备工具版本为 `pymobiledevice3==10.9.0`。通用版根据命令和返回数据
检查兼容性；需要重现实验时，额外传入 `--expect-pmd3-version 10.9.0`。

如需新建独立设备环境：

```bash
python3 -m venv .device-env
.device-env/bin/python -m pip install "pymobiledevice3==10.9.0"
python3 -m tide_your_iphone probe \
  --pmd3 .device-env/bin/pymobiledevice3 \
  --output-dir data/my-phone
```

也可将本项目安装为普通命令：

```bash
python3 -m pip install .
tide-your-iphone --help
```

## 多设备

`devices` 显示用于选择设备的 UDID；`probe` 的运行摘要缩写该标识。
多台设备连接时，通过 `--udid` 明确选择，每台设备使用自己的输出目录：

```bash
python3 -m tide_your_iphone devices --json
python3 -m tide_your_iphone probe --udid YOUR_DEVICE_UDID --output-dir data/phone-a
python3 -m tide_your_iphone probe --device-class iPad --output-dir data/ipad-a
```

`--device-class` 支持 `Any`（默认）、`iPhone`、`iPad`、`iPod`。
`--timeout` 指定每条设备命令的超时秒数，默认 120 秒。

## 六字段契约

`app_registry.json` 为行对象数组，`app_registry.csv` 使用相同列。两者都恰好
保留以下六个字段，按 Bundle ID 排序：

| 字段 | 来源 |
|---|---|
| `bundle_id` | `CFBundleIdentifier`，缺失时使用 InstallationProxy 响应键 |
| `base_display_name` | `CFBundleDisplayName` |
| `bundle_name` | `CFBundleName` |
| `application_type` | `ApplicationType` |
| `version` | `CFBundleShortVersionString` → `Product Version` → `CFBundleVersion` |
| `installed` | 当前清单中返回的应用为 `true` |

缺失名称保留为空。应用名称展示依次使用 `base_display_name`、`bundle_name`、
`bundle_id`。原始路径、权限、账号标识等属性在精简时丢弃。

注册表是某一台设备的一次安装状态快照。离线导入保留该快照的含义和时间范围。

## 离线示例

`examples/` 使用虚构应用，可直接验证完整流程：

```bash
python3 -m tide_your_iphone probe \
  --input examples/installation_proxy.json \
  --output-dir data/demo

python3 -m tide_your_iphone join \
  --registry data/demo/app_registry.json \
  --usage examples/usage.csv \
  --output-dir reports/demo

python3 -m tide_your_iphone verify data/demo/app_registry.sha256
python3 -m tide_your_iphone verify reports/demo/app_ranking.sha256
```

`probe --input` 接受 InstallationProxy JSON（对象或元数据数组），也接受已有的
六字段 Registry JSON/CSV。该模式不会启动设备工具。

## 通用统计输入

CSV 或 JSON 使用 `bundle_id`、`count`、可选 `metric` 三列：

```csv
metric,bundle_id,count
foreground_entries,org.example.notes,12
foreground_entries,org.example.reader,4
homescreen_launches_experimental,org.example.notes,6
```

JSON 可为同样的行对象数组，或 `{ "指标名": [行对象...] }`。
已有 `rankings` 包装的 JSON 也可读取。指标名可以自行定义；`count` 为非负整数。

同一指标、同一 Bundle ID 的多行记录会累加；每个指标按次数降序排列，同次数按
Bundle ID 排序。整个输入都会处理，`--top N` 控制每个指标最终导出的行数。
覆盖率始终以筛选设备后的完整输入计算，JSON 标明这个范围。

已有 CSV 使用其他列名时：

```bash
python3 -m tide_your_iphone join \
  --registry data/my-phone/app_registry.csv \
  --usage daily_counts.csv \
  --bundle-column application \
  --count-column entries \
  --metric foreground_entries \
  --output-dir reports/my-phone
```

含有设备列的统计输入会检查是否混合多台设备；通过 `--usage-device` 选择：

```bash
python3 -m tide_your_iphone join \
  --registry data/my-phone/app_registry.json \
  --usage counts.csv \
  --device-column device_id \
  --usage-device YOUR_USAGE_DEVICE_ID \
  --output-dir reports/my-phone
```

使用数据应与注册表属于同一台设备。Biome 的设备 UUID 和 USB UDID 是不同的
标识，配对时使用对应数据源自己的标识。

当前注册表中缺失的 Bundle ID 在排名中保留 `resolution=unresolved`，
`installed=null`（CSV 为空），等待进一步解析。

## 兼容 Biome M0

```bash
python3 -m tide_your_iphone join \
  --registry data/my-phone/app_registry.json \
  --m0-output /path/to/m0_probe_output.txt \
  --output-dir reports/m0
```

旧入口也保留：

```bash
python3 app_registry_probe.py --pmd3 /path/to/pymobiledevice3 --output-dir data/my-phone
python3 join_m0_registry.py \
  --registry data/my-phone/app_registry.json \
  --m0-output /path/to/m0_probe_output.txt \
  --output-dir reports/m0
```

M0 文本中的前台与实验性主屏统计段可以独立出现。M0 只打印 Top 20 时，
通用版能关联的范围就是这些已打印数据；完整排名请提供完整 JSON/CSV 统计。
本版本消费使用统计文件，Biome 二进制解码仍由现有 M0/解析器提供。

## 输出与校验

`probe` 输出 `app_registry.json`、`app_registry.csv`、`app_registry.sha256`。
`join` 输出 `app_ranking.json`、`app_ranking.csv`、`app_ranking.sha256`。

排名 JSON 同时包含输入文件校验值、每个指标的覆盖率和统计范围。相同输入产生
相同内容与哈希。已有输出可用 `--overwrite` 更新；输入与输出同名时会要求更换
输出目录，避免覆盖原始数据。

## 开发验证

```bash
python3 -m unittest discover -s tests -v
```

测试覆盖设备选择、模拟设备命令、离线流程、三种统计格式、异常输入、文件
覆盖保护和 SHA-256。设备模拟使用虚构 UDID 和应用，不包含个人快照。

命令适配依据 [pymobiledevice3 apps CLI](https://github.com/doronz88/pymobiledevice3/blob/master/pymobiledevice3/cli/apps.py)
和 [usbmux CLI](https://github.com/doronz88/pymobiledevice3/blob/master/pymobiledevice3/cli/usbmux.py)。

## 作者与参考项目

本项目由 [golearnalanguage](https://github.com/golearnalanguage) 维护。
数据来源方案参考 [ActivityWatch/aw-import-screentime](https://github.com/ActivityWatch/aw-import-screentime)，
未来桌面整理方向参考 [tmad4000/iphone-layout-tool](https://github.com/tmad4000/iphone-layout-tool)。
设备清单读取使用用户独立安装的 [pymobiledevice3](https://github.com/doronz88/pymobiledevice3)。

完整贡献与使用方式见 [CREDITS.md](CREDITS.md)，许可证与源码来源边界见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)，维护者记录见 [AUTHORS.md](AUTHORS.md)。
本项目新增源码采用 MIT 许可证。
