# ESP32 Upgrade Server

一个用于 Linux 服务器的 ESP32 代码拉取、编译、固件升级包查询和 OTA 发布管理页面。

## 功能

- 前端页面：编译、升级包查询、日志查看、配置状态展示。
- 后端接口：启动编译任务、查询升级包、查询任务状态和日志。
- 编译流程：调用配置的编译脚本，执行增量或全量编译。
- 升级包查询：扫描 OTA 包目录，并在任务输出窗口显示匹配到的 OTA 包。
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

这些配置先允许为空，补上后就可以真实拉代码、编译和查询升级包。

```bash
export ESP_UPGRADE_REPO_URL="https://github.com/your-org/your-esp32-project.git"
export ESP_UPGRADE_REPO_BRANCH="main"
export ESP_UPGRADE_BUILD_COMMAND="idf.py build"
export ESP_UPGRADE_FIRMWARE_PATH="/codebase/upgrade_linux/work/source/build/app.bin"
export ESP_UPGRADE_OTA_PACKAGE_DIR="/root/codebase/esp32/projects/release/ota"
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
| `ESP_UPGRADE_BUILD_RECORDS_PATH` | `$ESP_UPGRADE_BASE_DIR/build_records.json` | 编译记录文件 |
| `ESP_UPGRADE_CLEANUP_ENABLED` | `1` | 是否开启定时清理 |
| `ESP_UPGRADE_CLEANUP_RETENTION_DAYS` | `14` | 保留最近多少天的任务和编译记录 |
| `ESP_UPGRADE_CLEANUP_HOUR` | `3` | 每天清理小时，北京时间 |
| `ESP_UPGRADE_CLEANUP_MINUTE` | `0` | 每天清理分钟，北京时间 |
| `ESP_UPGRADE_BUILD_COMMAND` | 空 | 旧编译命令配置，当前编译接口使用脚本 |
| `ESP_UPGRADE_BUILD_WORKDIR` | `$ESP_UPGRADE_SOURCE_DIR` | 编译命令运行目录 |
| `ESP_UPGRADE_FIRMWARE_PATH` | 空 | 固件路径 |
| `ESP_UPGRADE_UPGRADE_COMMAND` | 空 | 旧升级命令配置，当前前端升级按钮不再调用 |
| `ESP_UPGRADE_OTA_PACKAGE_DIR` | `/root/codebase/esp32/projects/release/ota` | 前端“获取升级包信息”扫描的 OTA 包目录 |
| `ESP_UPGRADE_OTA_PUBLISH_DIR` | `/root/codebase/esp32/projects/release/ota_publish` | 前端 OTA 发布复制到的目录 |
| `ESP_UPGRADE_OTA_PUBLISH_HISTORY_PATH` | `$ESP_UPGRADE_BASE_DIR/ota_publish_history.json` | OTA 发布历史记录文件 |
| `ESP_UPGRADE_OTA_UPGRADE_RECORDS_PATH` | `$ESP_UPGRADE_BASE_DIR/ota_upgrade_records.json` | 设备请求 OTA 升级检查的记录文件 |
| `ESP_UPGRADE_OTA_UPGRADE_RECORDS_LIMIT` | `1000` | OTA 升级记录最多保留条数 |
| `ESP_OTA_DEFAULT_BOARD` | `fogseek-nano` | 默认发布板型 |
| `ESP_OTA_SIGN_PRIVATE_KEY_PATH` | `/root/codebase/esp32/projects/release/keys/ota_sign_private.pem` | OTA manifest ECDSA P-256 私钥 |
| `ESP_OTA_SIGN_PUBLIC_KEY_PATH` | `/root/codebase/esp32/projects/release/keys/ota_sign_public.pem` | OTA manifest 公钥，给固件端内置 |
| `ESP_OTA_AUTO_GENERATE_TEST_KEYS` | `1` | 研发测试阶段私钥不存在时自动生成测试密钥 |

## ESP32 Release OTA

固件发布接口已经集成到同一个服务里，不需要再起一个端口。研发测试阶段使用 HTTP 传输，但 OTA 检查接口会返回带签名的 manifest 字段，设备端应校验 `signature` 和下载后的 `sha256`：

```text
POST http://14.103.183.47:8010/v1/firmware/ota/
GET  http://14.103.183.47:8010/firmwares/fogseek-nano/<timestamp>_<version>_ota.bin
```

服务器只发布 app 固件，也就是 ESP-IDF 构建出来的 `build/xiaozhi.bin`，发布后统一命名为 `<时间戳>_<版本号>_ota.bin`。不要把 `merged-binary.bin` 放给 OTA 下载。

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
ESP_OTA_DEFAULT_BOARD=fogseek-nano
ESP_OTA_SIGN_PRIVATE_KEY_PATH=/root/codebase/esp32/projects/release/keys/ota_sign_private.pem
ESP_OTA_SIGN_PUBLIC_KEY_PATH=/root/codebase/esp32/projects/release/keys/ota_sign_public.pem
ESP_OTA_AUTO_GENERATE_TEST_KEYS=1
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

首次部署：

```bash
cd /codebase
git clone git@github.com:niuzhanaifu/upgrade_linux.git
cd /codebase/upgrade_linux
chmod +x deploy/redeploy.sh
./deploy/redeploy.sh
```

后续更新部署：

```bash
cd /codebase/upgrade_linux
./deploy/redeploy.sh
```

脚本会自动 `git fetch`、`git pull --ff-only`、安装后端依赖、更新 systemd 服务并重启。默认仓库地址是 `git@github.com:niuzhanaifu/upgrade_linux.git`。

如果你只是从本地目录复制部署，也可以在项目根目录执行：

```bash
chmod +x deploy/install.sh
./deploy/install.sh
```

ESP32 代码仓库、编译脚本和升级包目录建议写在服务器的 `/etc/esp32-upgrade.env`，重新部署不会覆盖这个文件。

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

查询编译记录和可下载固件：

```bash
curl http://14.103.183.47:8010/api/v1/build-records
curl http://14.103.183.47:8010/api/v1/firmwares
curl -OJ http://14.103.183.47:8010/api/v1/firmwares/{record_id}/download
```

服务端每天北京时间 03:00 会清理超过 14 天的内存任务日志、编译记录和记录里指向的固件文件，避免固件持续占用服务器空间。

查询 OTA 升级包信息：

```bash
curl -X POST http://14.103.183.47:8010/api/v1/upgrade
curl http://14.103.183.47:8010/api/v1/jobs/{job_id}/logs
```

该接口会扫描 `ESP_UPGRADE_OTA_PACKAGE_DIR`，默认目录是 `/root/codebase/esp32/projects/release/ota`。只有符合 `<时间戳>_<版本号>_ota.bin` 格式的文件会显示在任务输出里，例如 `20260601153000_2.1.0_ota.bin`。

OTA 发布接口：

```bash
curl http://14.103.183.47:8010/api/v1/ota-packages
curl -X POST http://14.103.183.47:8010/api/v1/ota-publish \
  -H 'Content-Type: application/json' \
  -d '{"package_name":"20260601_153012_2.1.0_ota.bin","password":"300075"}'
curl -X POST http://14.103.183.47:8010/api/v1/ota-publish/unpublish \
  -H 'Content-Type: application/json' \
  -d '{"password":"300075","board":"fogseek-nano"}'
curl http://14.103.183.47:8010/api/v1/ota-publish/history
```

发布成功后会创建 `ESP_UPGRADE_OTA_PUBLISH_DIR`，删除目录里的旧发布文件，然后把用户选择的 OTA 包复制进去，并写入发布历史。

下架 OTA 包会把 `ESP_UPGRADE_OTA_PUBLISH_DIR/<board>/manifest.json` 改为下架状态，使固件端再次请求时拿不到升级包并返回 `available=false`，同时会尽量删除该发布目录下的旧 OTA 文件。下载接口也会校验有效 manifest，所以即使旧 bin 因权限原因残留，也不会继续作为已发布固件下载。它不会删除 `ESP_UPGRADE_OTA_PACKAGE_DIR` 里的待发布源包，也不会改动 `ESP_OTA_SIGN_PRIVATE_KEY_PATH` / `ESP_OTA_SIGN_PUBLIC_KEY_PATH` 对应的私钥和公钥。

OTA 升级请求记录：

```bash
curl http://14.103.183.47:8010/api/v1/ota-upgrade-records
```

只有服务端实际向设备下发可升级 manifest，或者本应下发但签名/文件异常时，才会记录来源 IP、请求时间、Device-Id、Client-Id、板型、当前版本、目标版本、包名和结果。普通开机检查得到“无升级”不会写入记录，避免用户量大时产生大量冗余数据。

服务端下发升级时会先按“默认成功”记录。如果固件端升级完成后主动上报，服务端会用设备上报结果覆盖这条记录：

```bash
curl -X POST http://14.103.183.47:8010/v1/firmware/ota/result \
  -H 'Content-Type: application/json' \
  -H 'Device-Id: AA:BB:CC:DD:EE:FF' \
  -H 'Client-Id: device-uuid' \
  -d '{
    "record_id": "服务端下发的 upgrade_record_id",
    "success": true,
    "board": "fogseek-nano",
    "version": "2.1.1",
    "package_name": "20260601153000_2.1.1_ota.bin",
    "error": ""
  }'
```

如果固件端暂时不上报，记录会一直保持“默认成功”。如果上报失败，将显示为“失败”。

发布时服务端会：

- 复制 OTA 包到 `ESP_UPGRADE_OTA_PUBLISH_DIR/<board>/`。
- 计算固件 `size` 和 `sha256`。
- 使用 ECDSA P-256 私钥对固定格式签名原文签名。
- 在发布目录写入 `manifest.json`。
- OTA 检查接口根据设备上报的 `board` 和当前版本返回 `available=true/false`。

返回给设备的新 manifest 格式：

```json
{
  "firmware": {
    "available": true,
    "board": "fogseek-nano",
    "version": "2.1.1",
    "url": "http://14.103.183.47:8010/firmwares/fogseek-nano/20260601153000_2.1.1_ota.bin",
    "size": 2275120,
    "sha256": "64位小写hex",
    "sign_alg": "ecdsa-p256-sha256",
    "signature": "base64签名",
    "force": 0
  }
}
```

签名原文固定为：

```text
board=<board>
version=<version>
url=<url>
size=<size>
sha256=<sha256>
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
