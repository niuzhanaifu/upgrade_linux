# ESP32 Upgrade Server

一个用于 Linux 服务器的 ESP32 代码拉取、编译、固件升级管理页面。

## 功能

- 前端页面：编译、升级、日志查看、配置状态展示。
- 后端接口：启动编译任务、启动升级任务、查询任务状态和日志。
- 编译流程：自动 `git clone` 或 `git pull`，再执行配置的编译命令。
- 升级流程：执行配置的升级命令，可使用最新固件路径。
- 默认端口：`8010`，不会和 `DA_FU_WENG_APP` 股票服务默认的 `8000` 冲突。

## 本地运行

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn upgrade_server.main:app --host 0.0.0.0 --port 8010
```

打开：

```text
http://服务器IP:8010
```

## 后续需要补充的配置

这些配置先允许为空，补上后就可以真实拉代码、编译和升级。

```bash
export ESP_UPGRADE_REPO_URL="https://github.com/your-org/your-esp32-project.git"
export ESP_UPGRADE_REPO_BRANCH="main"
export ESP_UPGRADE_BUILD_COMMAND="idf.py build"
export ESP_UPGRADE_FIRMWARE_PATH="/codebase/upgrade_linux/work/source/build/app.bin"
export ESP_UPGRADE_UPGRADE_COMMAND="python3 tools/upgrade.py --firmware {firmware}"
```

常用环境变量：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `ESP_UPGRADE_HOST` | `0.0.0.0` | 服务监听地址 |
| `ESP_UPGRADE_PORT` | `8010` | 服务监听端口 |
| `ESP_UPGRADE_BASE_DIR` | `./var` | 工作目录 |
| `ESP_UPGRADE_REPO_URL` | 空 | ESP32 代码仓库地址 |
| `ESP_UPGRADE_REPO_BRANCH` | 空 | 可选分支 |
| `ESP_UPGRADE_SOURCE_DIR` | `$ESP_UPGRADE_BASE_DIR/source` | 代码目录 |
| `ESP_UPGRADE_BUILD_SCRIPT` | `/root/codebase/esp32/projects/fetch_build_lula_esp32.sh` | 编译脚本 |
| `ESP_UPGRADE_BUILD_SCRIPT_WORKDIR` | `/root/codebase/esp32/projects` | 编译脚本运行目录 |
| `ESP_UPGRADE_BUILD_INCREMENTAL_ARG` | `--incremental` | 增量编译参数 |
| `ESP_UPGRADE_BUILD_FULL_ARG` | `--full` | 全量编译参数 |
| `ESP_UPGRADE_BUILD_COMMAND` | 空 | 旧编译命令配置，当前编译接口使用脚本 |
| `ESP_UPGRADE_BUILD_WORKDIR` | `$ESP_UPGRADE_SOURCE_DIR` | 编译命令运行目录 |
| `ESP_UPGRADE_FIRMWARE_PATH` | 空 | 固件路径 |
| `ESP_UPGRADE_UPGRADE_COMMAND` | 空 | 升级命令，支持 `{firmware}` 和 `{source_dir}` |

## ESP32 Release OTA

固件发布接口已经集成到同一个服务里，不需要再起一个端口：

```text
POST http://14.103.183.47:8010/v1/firmware/ota/
GET  http://14.103.183.47:8010/firmwares/xiaozhi.bin
```

服务器只发布 app 固件，也就是 ESP-IDF 构建出来的 `build/xiaozhi.bin`。不要把 `merged-binary.bin` 放给 OTA 下载。

把固件复制到服务器：

```bash
mkdir -p /codebase/upgrade_linux/firmwares
cp /path/to/xiaozhi-esp32/build/xiaozhi.bin /codebase/upgrade_linux/firmwares/xiaozhi.bin
```

在 `/etc/esp32-upgrade.env` 里配置：

```bash
ESP_OTA_PUBLIC_BASE_URL=http://14.103.183.47:8010
ESP_OTA_LATEST_VERSION=2.1.1
ESP_OTA_FIRMWARE_DIR=/codebase/upgrade_linux/firmwares
ESP_OTA_FIRMWARE_FILE=xiaozhi.bin
ESP_OTA_FORCE=0
```

然后重启：

```bash
sudo systemctl restart esp32-upgrade
```

ESP32 固件端的发布检查地址需要改为：

```cpp
static constexpr const char* FIRMWARE_RELEASE_CHECK_URL =
    "http://14.103.183.47:8010/v1/firmware/ota/";
```

同时确认：

```text
CONFIG_ENABLE_RELEASE_OTA=y
# CONFIG_SKIP_VERSION_CHECK is not set
```

## Linux systemd 部署

可以参考 [deploy/systemd/esp32-upgrade.service](deploy/systemd/esp32-upgrade.service)。

首次部署或后续重新部署，建议在服务器执行：

```bash
export UPGRADE_APP_REPO_URL="https://github.com/your-org/upgrade_linux.git"
export UPGRADE_APP_BRANCH="main"
chmod +x deploy/redeploy.sh
./deploy/redeploy.sh
```

后续如果 `/codebase/upgrade_linux` 已经是 git 仓库，直接运行：

```bash
cd /codebase/upgrade_linux
./deploy/redeploy.sh
```

脚本会自动拉取本项目最新代码、安装后端依赖、更新 systemd 服务并重启。

如果你只是从本地目录复制部署，也可以在项目根目录执行：

```bash
chmod +x deploy/install.sh
./deploy/install.sh
```

ESP32 代码仓库、编译命令、升级命令建议写在服务器的 `/etc/esp32-upgrade.env`，重新部署不会覆盖这个文件。

## 编译接口

编译接口会在后台执行脚本，不会让 HTTP 请求一直阻塞到编译结束：

```text
POST /api/v1/build/incremental
POST /api/v1/build/full
```

后端判断规则：

- 进程退出码 `0`：编译成功。
- 进程退出码非 `0`：编译失败。
- stdout 中解析 `OUTPUT_DIR=`、`MERGED_BIN=`、`FIRMWARE_VERSION=`。

查询任务结果：

```bash
curl http://14.103.183.47:8010/api/v1/jobs/{job_id}
curl http://14.103.183.47:8010/api/v1/jobs/{job_id}/logs
```

成功后的 `job.result` 示例：

```json
{
  "success": true,
  "returncode": 0,
  "output_dir": "/root/codebase/esp32/projects/releases/20260601_153012",
  "merged_bin": "/root/codebase/esp32/projects/releases/20260601_153012/20260601_153012_2.1.0_merged.bin",
  "firmware_version": "2.1.0",
  "mode": "incremental"
}
```

和股票服务同时运行的原因：

- 股票服务目录是 `/opt/dafuweng/server`，本服务建议部署到 `/codebase/upgrade_linux`。
- 股票服务 systemd 名称是 `dafuweng-stock`，本服务名称是 `esp32-upgrade`。
- 股票服务默认监听 `8000`，本服务默认监听 `8010`。
- 两个服务的 Python 包名、环境变量前缀、数据目录都不同，不会互相覆盖。
