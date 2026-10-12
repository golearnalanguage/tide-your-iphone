# Third-party notices and source provenance

核对日期：2026-10-12。来源为下列上游仓库及其许可证文件。

## 本次发布

本仓库的 [LICENSE](LICENSE) 覆盖本项目新增源码。仓库包含一个 Python 标准库
实现的通用 CLI，以及虚构示例和测试。

`pymobiledevice3` 由用户另行安装并通过子进程调用。本仓库未分发其源码或软件包。
Biome 解码实验使用的 `aw-import-screentime` 和 `ccl-segb` 位于独立实验环境，
此版本通过 M0 文本或 JSON/CSV 文件对接结果。

## 上游清单

| 上游 | 核对结果 | 发布中包含的内容 |
|---|---|---|
| [ActivityWatch/aw-import-screentime](https://github.com/ActivityWatch/aw-import-screentime) | 核对时根目录未见许可证文件，GitHub 许可证元数据为空 | 项目链接、设计来源说明、导出结果的输入适配 |
| [tmad4000/iphone-layout-tool](https://github.com/tmad4000/iphone-layout-tool) | 核对时根目录未见许可证文件，GitHub 许可证元数据为空 | 项目链接与桌面布局研究方向的说明 |
| [doronz88/pymobiledevice3](https://github.com/doronz88/pymobiledevice3/blob/master/LICENSE) | GPLv3；以该链接中的具体许可文本为准 | 调用其 CLI 的本项目适配代码；设备工具另行安装 |
| [cclgroupltd/ccl-segb](https://github.com/cclgroupltd/ccl-segb/blob/main/LICENSE) | MIT；以该链接中的版权与许可文本为准 | 项目链接与前期解码工具来源说明 |
| [zhaotianjing/screentime-csv-exporter](https://github.com/zhaotianjing/screentime-csv-exporter) | 核对时原仓库链接返回 404；当前未引入代码 | 初期研究记录中的项目链接与来源说明 |

## 后续引入源码时

每次复制、修改或分发上游源码，应记录来源项目、文件、具体提交版本及修改内容，
保留原作者版权头、原许可证和必须的通知文件。上游许可需要与拟发布内容对应；
缺少明确许可证的源码先取得明确授权。

引用和致谢用于记录贡献；源码再分发授权由相应许可证或作者授权确定。
上游源码应在独立目录记录原许可，本项目的 MIT 声明适用于本项目新增部分。
