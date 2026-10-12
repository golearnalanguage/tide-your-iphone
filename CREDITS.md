# Credits

tide your iPhone 的初始研究与实验受益于以下项目。感谢各项目作者和贡献者提供
的数据格式研究、设备工具和实现经验。

| 项目与作者 | 对本项目的贡献 | 当前使用方式 |
|---|---|---|
| [ActivityWatch/aw-import-screentime](https://github.com/ActivityWatch/aw-import-screentime)，ActivityWatch 与其贡献者 | Biome `App.InFocus` 数据源、SEGB/Protobuf 解析与前台事件流程 | 先前独立实验中的 M0 Probe 使用其解码器；本仓库读取已经导出的统计文件 |
| [tmad4000/iphone-layout-tool](https://github.com/tmad4000/iphone-layout-tool)，tmad4000 与其贡献者 | 通过 `pymobiledevice3`、Apple Configurator 和 `cfgutil` 处理桌面布局的研究方向 | 方案参考；当前版本实现应用清单与排名，桌面布局功能尚未接入 |
| [doronz88/pymobiledevice3](https://github.com/doronz88/pymobiledevice3)，doronz88 与其贡献者 | Apple 设备发现和 InstallationProxy 安装清单读取 | 通过用户单独安装的 CLI 子进程调用 `usbmux list` 与 `apps list` |
| [cclgroupltd/ccl-segb](https://github.com/cclgroupltd/ccl-segb)，CCL Group 与其贡献者 | Apple SEGB 容器解析研究与工具 | 先前 M0 解码环境中的间接工具；本仓库消费统计结果 |
| [zhaotianjing/screentime-csv-exporter](https://github.com/zhaotianjing/screentime-csv-exporter)，zhaotianjing 与其贡献者 | 初期研究中提及的 Screen Time 会话和逐日 CSV 导出方案 | 初期研究参考；核对日原仓库链接返回 404 |

本仓库目前发布的 Python 模块、命令行封装、输入适配、校验和测试为本项目新增
实现。上游 Python 源码、Protobuf 定义、布局转换脚本和图像资源均未包含在本次
发布目录中。许可证核对结果及未来源码引入要求见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
