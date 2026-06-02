# OTA 升级方案：测试阶段使用 HTTP + 固件签名

本文档用于指导测试阶段实现固件 OTA。当前目标是：

```text
设备配置、激活、语音服务器地址、时间同步：仍走现有 CONFIG_OTA_URL 对应接口
固件升级检查和固件下载：走单独的 OTA 发布服务器
传输协议：测试阶段先使用 HTTP
可信校验：使用 manifest 签名 + 固件 SHA256
```

当前工程里，OTA 应下载的是 APP 固件：

```text
build/xiaozhi.bin
```

不要把下面这些文件作为 OTA 固件下发：

```text
build/merged-binary.bin
releases/*.zip
bootloader.bin
partition-table.bin
ota_data_initial.bin
generated_assets.bin
```

`merged-binary.bin` 是给网页烧录工具或首次整机烧录使用的完整 flash 镜像；OTA 只写入 `ota_0` / `ota_1` 这类 APP 分区。

## 总体流程

测试阶段流程如下：

```text
1. 设备开机
2. 设备请求现有配置接口 CONFIG_OTA_URL
   - 获取激活信息
   - 获取 MQTT/WebSocket 语音服务器地址
   - 获取服务器时间
3. 如果启用了独立固件 OTA，设备再请求固件发布服务器
4. 固件发布服务器返回 manifest
5. 设备使用内置公钥校验 manifest 签名
6. 签名通过后，设备判断版本是否需要升级
7. 设备用 HTTP 下载 OTA 发布包
8. 下载过程中写入 OTA 分区，同时计算 SHA256
9. 下载完成后校验 size 和 SHA256
10. 校验通过才调用 esp_ota_end 和 esp_ota_set_boot_partition
11. 设备重启进入新版本
12. 新版本启动成功后调用 esp_ota_mark_app_valid_cancel_rollback
```

关键点：

```text
HTTP 只负责传输，不负责可信
可信由签名保证
SHA256 只保证下载内容和 manifest 一致
manifest 签名保证 manifest 不能被伪造
```

只校验 SHA256 不够安全。因为如果攻击者能劫持 HTTP，也可以同时替换 OTA 发布包和 `sha256`。所以必须有服务端私钥签名，设备端只内置公钥验签。

## 当前固件状态

当前工程已经有独立固件 OTA 的基础开关：

```text
CONFIG_ENABLE_RELEASE_OTA
```

定义位置：

```text
main/Kconfig.projbuild
```

当前逻辑：

```text
CONFIG_OTA_URL
  继续负责设备配置、激活、语音服务器地址、时间同步

Ota::CheckFirmwareVersionFromReleaseServer()
  负责访问独立固件发布服务器
```

当前代码里的独立发布服务器地址在：

```text
main/ota.cc
```

示例：

```cpp
static constexpr const char* FIRMWARE_RELEASE_CHECK_URL =
    "http://192.168.1.100:8080/v1/firmware/ota/";
```

测试阶段需要把它改成实际 OTA 发布服务器地址，例如：

```cpp
static constexpr const char* FIRMWARE_RELEASE_CHECK_URL =
    "http://14.103.183.47:18080/v1/firmware/ota/";
```

当前 `CheckFirmwareVersionFromReleaseServer()` 只解析了：

```json
{
  "firmware": {
    "version": "2.1.1",
    "url": "http://server/firmwares/fogseek-nano/20260601153000_2.1.1_ota.bin",
    "force": 0
  }
}
```

后续需要扩展解析：

```text
size
sha256
signature
sign_alg
```

当前 `Ota::Upgrade()` 已经支持 HTTP 下载、写 OTA 分区、`esp_ota_end()`、`esp_ota_set_boot_partition()`，但还需要补充：

```text
下载前校验 manifest 签名
下载时计算 SHA256
下载完成后校验 size 和 SHA256
校验失败时 esp_ota_abort，不切换 boot partition
```

## 服务端职责

服务端要做四件事：

```text
1. 保存每个产品/板型的最新固件版本
2. 对固件计算 SHA256
3. 使用私钥对 manifest 关键字段签名
4. 提供 OTA 检查接口和固件下载接口
```

### 服务端文件结构建议

建议服务端目录如下：

```text
/srv/fogseek-ota/
  keys/
    ota_sign_private.pem        # 私钥，只在服务端/发布机保存，不能放到 Git
    ota_sign_public.pem         # 公钥，可以给固件端内置
  firmwares/
    fogseek-nano/
      20260601153000_2.1.1_ota.bin
        manifest.json
    fogseek-nano-lcd1.8/
      20260601153000_2.1.1_ota.bin
        manifest.json
```

### 固件文件和命名要求

服务端发布的 OTA 文件内容必须来自本地构建产物：

```text
build/xiaozhi.bin
```

但上传到服务端后，不再叫 `xiaozhi.bin`，统一重命名为：

```text
<时间戳>_<版本号>_ota.bin
```

示例：

```text
20260601153000_2.1.1_ota.bin
```

推荐时间戳格式：

```text
yyyyMMddHHmmss
```

完整下载路径示例：

```text
firmwares/fogseek-nano/20260601153000_2.1.1_ota.bin
firmwares/fogseek-nano-lcd1.8/20260601153000_2.1.1_ota.bin
```

不要用：

```text
build/merged-binary.bin
```

原因：

```text
merged-binary.bin 包含 bootloader、partition table、otadata、app、assets
OTA API 只写 APP 分区
把 merged-binary.bin 写进 APP 分区会导致固件格式错误或无法启动
```

### OTA 检查接口

测试阶段建议接口：

```text
POST http://<ota-server>:<port>/v1/firmware/ota/
```

设备会携带这些 HTTP Header：

```text
Device-Id: <MAC 地址>
Client-Id: <设备 UUID>
Serial-Number: <如果 eFuse USER_DATA 写入了 SN，则会携带>
User-Agent: <BOARD_NAME>/<当前固件版本>
Accept-Language: zh-CN
Content-Type: application/json
```

设备请求 body 是当前工程的系统信息 JSON，里面包含板型、版本、芯片、flash、运行分区等信息。服务端至少应该使用以下信息做判断：

```text
board / board_type
当前固件 version
Device-Id 或 Serial-Number
运行分区 ota label
```

服务端响应 `200 OK`，如果没有新版本：

```json
{
  "firmware": {
    "available": false
  }
}
```

如果有新版本：

```json
{
  "firmware": {
    "available": true,
    "board": "fogseek-nano",
    "version": "2.1.1",
    "url": "http://14.103.183.47:18080/firmwares/fogseek-nano/20260601153000_2.1.1_ota.bin",
    "size": 2275120,
    "sha256": "64位小写hex",
    "sign_alg": "ecdsa-p256-sha256",
    "signature": "base64签名",
    "force": 0
  }
}
```

字段说明：

| 字段 | 必填 | 说明 |
|---|---:|---|
| `available` | 是 | 是否有可升级版本 |
| `board` | 是 | 固件适配的板型，例如 `fogseek-nano` |
| `version` | 是 | 新固件版本，来自工程 `PROJECT_VER` |
| `url` | 是 | OTA 发布包下载地址，文件名格式为 `<时间戳>_<版本号>_ota.bin` |
| `size` | 是 | OTA 发布包字节数 |
| `sha256` | 是 | OTA 发布包的 SHA256，小写 hex |
| `sign_alg` | 是 | 测试阶段固定为 `ecdsa-p256-sha256` |
| `signature` | 是 | 对规范化签名原文的私钥签名，ECDSA DER 签名后再 base64 编码 |
| `force` | 否 | `1` 表示强制升级，即使版本号判断不更新 |

### 签名算法

测试阶段推荐：

```text
ECDSA P-256 + SHA256
```

原因：

```text
ESP-IDF 自带 mbedTLS，对 ECDSA P-256 支持成熟
签名长度较短
实现复杂度适中
```

### 公钥和私钥由谁生成

密钥应由固件发布方生成，通常是服务端负责人、发布系统负责人或 CI/CD 发布环境生成。原则是：

```text
私钥归服务端/发布系统持有
公钥归固件端持有
```

推荐流程：

```text
1. 服务端或发布机生成 ECDSA P-256 私钥
2. 从私钥导出公钥
3. 私钥只放在服务端或 CI/CD 的安全目录/密钥系统中
4. 公钥交给固件端，编译进固件
5. 服务端每次发布固件时用私钥签名 manifest
6. 设备端每次检查 OTA 时用内置公钥验签
```

不要由设备端生成私钥。设备端只需要公钥，不能拥有 OTA 签名私钥。

服务端生成密钥示例：

```bash
openssl ecparam -name prime256v1 -genkey -noout -out ota_sign_private.pem
openssl ec -in ota_sign_private.pem -pubout -out ota_sign_public.pem
```

私钥只保存在服务端：

```text
ota_sign_private.pem
```

公钥需要内置到固件：

```text
ota_sign_public.pem
```

固件端验签速度很快。设备只对 manifest 的几行文本做一次 ECDSA P-256 验签，数据量通常只有几百字节。相比 HTTP 下载 2MB 以上固件和写 flash，验签耗时很小，通常不会成为 OTA 性能瓶颈。

下载固件时还要做 SHA256。SHA256 是边下载边计算，不需要把整个固件一次性放进内存，也不会明显拖慢 OTA。

### 签名原文格式

服务端和设备端必须使用完全一致的签名原文。建议不要直接对 JSON 字符串签名，因为 JSON 字段顺序、空格、转义方式容易不一致。

建议固定为以下文本格式：

```text
board=<board>
version=<version>
url=<url>
size=<size>
sha256=<sha256>
```

注意：

```text
每行使用 \n 换行
最后一行后面不追加额外空行
sha256 使用小写 hex
size 使用十进制字符串
url 必须和响应 JSON 里的 url 完全一致
```

示例：

```text
board=fogseek-nano
version=2.1.1
url=http://14.103.183.47:18080/firmwares/fogseek-nano/20260601153000_2.1.1_ota.bin
size=2275120
sha256=2b1c...64位小写hex...
```

服务端对这段 UTF-8 文本计算 SHA256，然后使用 ECDSA P-256 私钥签名。签名结果使用 ECDSA DER 格式，再 base64 后放入 `signature`。

设备端当前实现按以下格式验签：

```text
sign_alg = ecdsa-p256-sha256
signature = base64(ECDSA_DER_SIGNATURE)
```

### 服务端发布流程

每次发布新固件，服务端执行：

```text
1. 从构建机器拿到 `build/xiaozhi.bin`
2. 确认固件板型，例如 fogseek-nano
3. 确认版本号，例如 2.1.1
4. 生成发布时间戳，例如 `20260601153000`
5. 将 `build/xiaozhi.bin` 重命名为 `20260601153000_2.1.1_ota.bin`
6. 上传到对应 board 的固件目录
7. 计算 size
8. 计算 sha256
9. 生成签名原文
10. 使用 ota_sign_private.pem 签名
11. 保存 manifest.json
12. OTA 检查接口开始返回该版本
```

计算 SHA256：

```bash
sha256sum 20260601153000_2.1.1_ota.bin
```

Windows PowerShell：

```powershell
Get-FileHash .\20260601153000_2.1.1_ota.bin -Algorithm SHA256
```

### 服务端版本选择逻辑

服务端应该按板型下发固件，不能把 LCD 版本发给普通 nano，也不能反过来。

建议判断优先级：

```text
1. Serial-Number，如果设备有独立 SN，则按 SN 查产品型号和灰度策略
2. Device-Id/MAC，如果没有 SN，则按 MAC 做灰度
3. 请求 body 中的 board/board_type
4. User-Agent 中的 BOARD_NAME
```

版本判断：

```text
如果 latest_version > current_version，返回 available=true
如果 force=1，返回 available=true
否则返回 available=false
```

灰度发布可以增加服务端策略：

```text
指定 SN 升级
指定 MAC 升级
指定百分比升级
指定当前版本升级
指定 board 升级
```

### 固件下载接口

固件下载地址示例：

```text
GET http://14.103.183.47:18080/firmwares/fogseek-nano/20260601153000_2.1.1_ota.bin
```

响应要求：

```text
HTTP 200
Content-Type: application/octet-stream
Content-Length: 必须有，且等于 manifest.size
```

服务端必须支持稳定的大文件下载。测试阶段可以不做断点续传，因为当前固件端 `Ota::Upgrade()` 是一次性顺序下载并写入 OTA 分区。

## 设备端职责

设备端要做五件事：

```text
1. 保留现有 CONFIG_OTA_URL，用于设备配置和语音服务器地址
2. 启用 CONFIG_ENABLE_RELEASE_OTA
3. 请求独立固件 OTA 服务器
4. 校验 manifest 签名
5. 下载 OTA 发布包后校验 size 和 SHA256，再切换 OTA 分区
```

### 设备端配置

测试阶段需要启用：

```text
CONFIG_ENABLE_RELEASE_OTA=y
```

如果使用 `scripts/release.py`，建议把该配置放进对应板型的 `config.json`，避免每次 release 后被 sdkconfig 重置。

例如：

```json
{
  "sdkconfig_append": [
    "CONFIG_ENABLE_RELEASE_OTA=y"
  ]
}
```

现有配置接口仍然使用：

```text
CONFIG_OTA_URL
```

也就是：

```text
115.190.136.178:8080
```

仍然负责：

```text
设备配置
语音服务器地址
激活
时间同步
```

独立固件 OTA 服务器只负责：

```text
固件版本检查
固件下载
```

### 设备端需要新增的数据字段

`Ota` 类建议增加：

```cpp
std::string firmware_board_;
std::string firmware_sha256_;
std::string firmware_signature_;
std::string firmware_sign_alg_;
size_t firmware_size_ = 0;
```

`CheckFirmwareVersionFromReleaseServer()` 需要解析：

```text
firmware.available
firmware.board
firmware.version
firmware.url
firmware.size
firmware.sha256
firmware.sign_alg
firmware.signature
firmware.force
```

### 设备端 manifest 校验

设备端内置 OTA 公钥：

```cpp
static const char OTA_PUBLIC_KEY_PEM[] = R"PEM(
-----BEGIN PUBLIC KEY-----
...
-----END PUBLIC KEY-----
)PEM";
```

校验流程：

```text
1. 检查 firmware.available 是否为 true
2. 检查 board 是否匹配当前 BOARD_TYPE 或 BOARD_NAME
3. 检查 version/url/size/sha256/signature 是否齐全
4. 使用完全一致的规则拼接签名原文
5. 使用内置公钥校验 signature
6. 验签失败则不下载、不升级
7. 验签成功后再判断 version 是否大于 current_version，或 force=1
```

如果签名失败，日志建议：

```text
Release OTA manifest signature verification failed
```

如果板型不匹配，日志建议：

```text
Release OTA board mismatch: expected=fogseek-nano, got=fogseek-nano-lcd1.8
```

### 设备端下载和写入校验

`Ota::Upgrade()` 当前已经做了基本下载和写入，后续要补充：

```text
1. 下载前检查 Content-Length 是否等于 manifest.size
2. 下载过程中边写 OTA 分区，边计算 SHA256
3. 下载完成后检查 total_read == manifest.size
4. 下载完成后检查 actual_sha256 == manifest.sha256
5. 只有全部通过，才执行 esp_ota_end()
6. 只有 esp_ota_end() 成功，才执行 esp_ota_set_boot_partition()
7. 任意失败都执行 esp_ota_abort()
```

推荐顺序：

```text
HTTP Open
检查状态码 200
检查 Content-Length
开始读数据
收到足够 image header 后 esp_ota_begin
循环 esp_ota_write
同步更新 SHA256
下载结束
检查 size
检查 SHA256
esp_ota_end
esp_ota_set_boot_partition
返回成功
```

注意：如果在 `esp_ota_begin()` 之前就因为 Content-Length 不一致失败，不需要调用 `esp_ota_abort()`。只有已经拿到 `update_handle` 后失败，才需要 abort。

### 设备端版本有效标记

新固件启动后，当前工程已有逻辑：

```cpp
Ota::MarkCurrentVersionValid()
```

它会在运行分区状态为：

```text
ESP_OTA_IMG_PENDING_VERIFY
```

时调用：

```cpp
esp_ota_mark_app_valid_cancel_rollback();
```

测试阶段要确认：

```text
新版本启动成功后会标记有效
如果新版本启动失败，bootloader 能回滚到旧版本
```

## 服务端最小实现建议

测试阶段服务端可以用一个简单程序实现。

需要提供两个接口：

```text
POST /v1/firmware/ota/
GET  /firmwares/<board>/<timestamp>_<version>_ota.bin
```

服务端伪代码：

```python
def check_ota(request):
    device = parse_headers_and_json(request)
    board = detect_board(device)
    current_version = detect_current_version(device)

    latest = find_latest_firmware(board)
    if latest is None:
        return {"firmware": {"available": False}}

    if not is_newer(latest.version, current_version) and not latest.force:
        return {"firmware": {"available": False}}

    return {
        "firmware": {
            "available": True,
            "board": board,
            "version": latest.version,
            "url": latest.url,
            "size": latest.size,
            "sha256": latest.sha256,
            "sign_alg": "ecdsa-p256-sha256",
            "signature": latest.signature,
            "force": 1 if latest.force else 0
        }
    }
```

签名生成伪代码：

```python
signing_text = (
    f"board={board}\n"
    f"version={version}\n"
    f"url={url}\n"
    f"size={size}\n"
    f"sha256={sha256}"
)

digest = sha256(signing_text.encode("utf-8"))
signature = ecdsa_p256_sign(private_key, digest)
signature_base64 = base64.b64encode(signature)
```

## 验收用例

服务端和设备端实现完成后，至少测试：

1. 正常升级：设备从 `2.1.0` 升级到 `2.1.1`，重启后版本号变为 `2.1.1`。
2. 无新版本：服务端返回 `available=false`，设备不下载固件。
3. 低版本：服务端返回 `2.0.9`，设备不升级，除非 `force=1`。
4. 强制升级：`force=1` 时，即使版本号不大于当前版本，也执行升级。
5. 签名错误：修改 `signature`，设备拒绝下载或拒绝升级。
6. URL 被篡改：只改 `url`，签名校验失败。
7. size 错误：`Content-Length` 或 manifest `size` 不一致，设备中止升级。
8. sha256 错误：固件内容被改，设备下载完成后校验失败，不切换分区。
9. 板型不匹配：给 nano 下发 lcd1.8 固件，设备拒绝升级。
10. 下载中断：设备保持旧版本可运行。
11. 新固件启动成功：设备调用 `esp_ota_mark_app_valid_cancel_rollback()` 标记有效。
12. 新固件启动失败：设备可回滚旧版本。

## 测试阶段安全边界

HTTP + manifest 签名能保证：

```text
攻击者不能伪造合法 manifest
攻击者不能替换固件内容而不被发现
攻击者不能把 URL、版本、大小、哈希改成自己的内容
```

但它不能保证：

```text
通信内容保密
服务器身份由 TLS 证明
防止网络层阻断
防止重放旧 manifest，除非设备端和服务端额外做版本/时间策略
防止通过非 OTA 方式直接写 flash
```

所以测试阶段可以使用 HTTP + 签名；量产阶段仍建议升级到：

```text
HTTPS + manifest 签名 + Secure Boot V2
```

## 量产阶段补充方向

量产阶段建议：

```text
1. OTA 检查接口改为 HTTPS
2. 固件下载 URL 改为 HTTPS
3. 继续保留 manifest 签名
4. 启用 Secure Boot V2
5. 可选启用 Flash Encryption
```

HTTPS 负责保护链路和服务器身份，manifest 签名负责保护发布元信息，Secure Boot 负责保证设备不会启动未授权 APP。

量产时的私钥原则：

```text
OTA manifest 私钥只在服务端
Secure Boot 私钥只在构建/发布环境
私钥不能进入 Git
私钥不能编进固件
设备端只保存公钥
```

## 当前工程后续改动清单

设备端后续实现建议按这个顺序做：

1. 在 `Ota` 类增加 `size`、`sha256`、`signature`、`sign_alg`、`board` 字段。
2. 扩展 `CheckFirmwareVersionFromReleaseServer()` 解析新版 manifest。
3. 增加 ECDSA P-256 manifest 验签函数。
4. 内置 OTA 公钥。
5. 验签通过后才设置 `has_new_version_ = true`。
6. 扩展 `Ota::Upgrade()` 支持预期 size 和 sha256 校验。
7. 下载过程中计算 SHA256。
8. 校验失败时 `esp_ota_abort()`，且不调用 `esp_ota_set_boot_partition()`。
9. 增加清晰日志，方便串口定位 OTA 失败原因。
10. 服务端实现发布脚本，自动生成 `manifest.json`。

服务端后续实现建议按这个顺序做：

1. 生成 ECDSA P-256 私钥和公钥。
2. 建立固件目录结构。
3. 编写发布脚本：复制 `build/xiaozhi.bin`，重命名为 `<时间戳>_<版本号>_ota.bin`，计算 size，计算 sha256，生成签名。
4. 实现 `POST /v1/firmware/ota/`。
5. 实现固件静态下载。
6. 按 board 区分 `fogseek-nano` 和 `fogseek-nano-lcd1.8`。
7. 增加灰度策略。
8. 增加发布记录和下载日志。
