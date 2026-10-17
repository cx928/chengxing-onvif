# 水星安防（MERCURY）事件模拟与 NVR 对接

程星 ONVIF 可以让虚拟摄像机“看起来就是一台水星安防摄像机”，并把 AI 检测结果
以 ONVIF 事件的形式推送给录像机。

## 1. 原理

```
AI 检测 ──► 目标组（person / vehicle / animal / package）
              │
              ▼
      厂商画像事件映射（MERCURY）
              │
      ┌───────┴────────┐
      ▼                ▼
ONVIF PullPoint   HTTP 主动推送
（NVR 订阅）       （平台 / 报警中心）
```

* **设备身份**：`GetDeviceInformation`、`GetScopes`、WS-Discovery、`GetCapabilities`
  均按画像返回；
* **事件主题集**：`GetEventProperties` 返回画像对应的 `TopicSet`，NVR 据此订阅；
* **事件内容**：`PullMessages` 返回带 `Source`（视频源、分析配置、规则）与
  `Data`（IsMotion / State / IsInside / Crossed）的标准通知消息。

## 2. 切换画像

摄像机 → **ONVIF / 水星** → 设备画像：

| 画像 | Manufacturer | 典型场景 |
| --- | --- | --- |
| 水星安防 MERCURY | `MERCURY` | 水星 / TP-LINK 系录像机 |
| TP-LINK VIGI | `TP-LINK` | VIGI NVR |
| 海康威视 | `Hikvision` | 海康 NVR（区域入侵/越界主题） |
| 大华 | `Dahua` | 大华 NVR（CrossLineDetector） |
| 宇视 UNV | `UNV` | 宇视 NVR |
| Ubiquiti UniFi | `Ubiquiti Inc.` | UniFi Protect |
| 通用 ONVIF | `ChengXing` | 通用 VMS |

制造商 / 型号 / 固件 / 硬件 ID 可在页面上覆盖，用于匹配特定型号。
URI 作用域会自动追加摄像机名称与硬件 ID。

## 3. 事件主题

### 3.1 默认主题（水星画像）

```
tns1:RuleEngine/CellMotionDetector/Motion   Data: IsMotion = true/false
tns1:VideoSource/MotionAlarm                Data: State    = true/false
tns1:RuleEngine/PeopleDetector/PeopleDetected   Data: State
tns1:RuleEngine/VehicleDetector/VehicleDetected Data: State
tns1:RuleEngine/FieldDetector/ObjectsInside Data: IsInside
tns1:RuleEngine/LineDetector/Crossed        Data: Crossed
```

### 3.2 自定义主题

在摄像机配置中覆盖（REST API 或配置文件）：

```json
{
  "onvif": {
    "eventTopics": {
      "person": ["tns1:RuleEngine/PeopleDetector/PeopleDetected"],
      "vehicle": [{"topic": "tns1:RuleEngine/VehicleDetector/VehicleDetected", "dataName": "State"}],
      "motion": ["tns1:RuleEngine/CellMotionDetector/Motion"]
    }
  }
}
```

修改后重启该摄像机生效。

## 4. PullPoint 自测

用 `curl` 模拟录像机订阅：

```bash
# 1) 创建订阅
curl -s -u admin:ONVIF密码 \
  -H 'Content-Type: application/soap+xml' \
  --data @subscribe.xml \
  http://192.168.1.10:8001/onvif/events_service

# subscribe.xml
<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">
  <s:Body>
    <CreatePullPointSubscription>
      <InitialTerminationTime>PT60S</InitialTerminationTime>
    </CreatePullPointSubscription>
  </s:Body>
</s:Envelope>
```

响应中的 `SubscriptionReference/Address` 即订阅地址。然后：

```bash
# 2) 拉取消息（先点网页上的“发送测试事件”）
curl -s -u admin:ONVIF密码 \
  -H 'Content-Type: application/soap+xml' \
  --data '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Body><PullMessages><Timeout>PT5S</Timeout><MessageLimit>10</MessageLimit></PullMessages></s:Body></s:Envelope>' \
  http://192.168.1.10:8001/onvif/subscription/<订阅ID>
```

也可以使用 ONVIF Device Manager（ODM）查看 Events 面板。

## 5. HTTP 主动推送

适用于不支持 ONVIF 订阅的 NVR / 平台。摄像机 → **事件推送**：

| 格式 | Content-Type | 说明 |
| --- | --- | --- |
| `json` | application/json | 通用事件 JSON，包含目标、置信度、检测框、截图 Base64 |
| `dahua` | application/json | 大华 AlarmCenter 风格 |
| `hikvision` | application/xml | 海康 EventNotificationAlert 风格 |
| `tplink` | application/json | 水星 / TP-LINK 报警推送风格 |
| `form` | x-www-form-urlencoded | 简单表单，便于接入自建平台 |

通用 JSON 示例：

```json
{
  "event": "detection",
  "cameraId": 1,
  "cameraName": "园区前门",
  "uuid": "…",
  "active": true,
  "groups": ["person"],
  "label": "人形",
  "confidence": 92,
  "timestamp": "2026-06-28T10:12:33.123Z",
  "detections": [{"label": "person", "confidence": 0.92, "box": [0.31, 0.22, 0.62, 0.88], "group": "person"}],
  "image": "<JPEG Base64>",
  "brand": "程星 ONVIF"
}
```

`事件推送 → 测试推送` 可直接验证地址与鉴权。

## 6. 兼容性说明

* 多数国产 NVR 对**第三方** ONVIF 摄像机的智能事件（人形/车辆）支持有限，
  通常只识别移动事件；设备画像能提高同品牌 NVR 的识别概率。
* 若 NVR 只显示移动报警，可先确认移动事件正常，再尝试切换画像或自定义主题。
* 事件是“状态型”：检测开始时 `true`，目标消失且超过冷却时间后 `false`；
  NVR 通常据此生成一段报警录像。
* 摄像机与录像机需在同一网段，或确保 UDP 3702 可通；否则请手动添加 IP 与端口。

## 7. 常见现象

| 现象 | 排查 |
| --- | --- |
| NVR 能添加但无事件 | 检查「上报移动事件」是否开启；用 ODM 看 PullPoint 是否收到消息 |
| 事件只来一次 | 检测目标的冷却时间过长；或 NVR 只处理状态变化 |
| 设备被识别为“未知品牌” | 切换画像；检查 Manufacturer 覆盖字段 |
| WS-Discovery 搜不到 | 防火墙 UDP 3702；虚拟机混杂模式；改用 IP 直连 |
| 时间不同步导致 NVR 拒收 | 打开 Windows 时间同步；事件时间使用 UTC |
