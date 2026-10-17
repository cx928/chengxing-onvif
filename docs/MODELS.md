# 模型与推理后端

## 1. 支持的模型家族

| 家族 | 文件 | 后端 | 说明 |
| --- | --- | --- | --- |
| YOLO26 / 11 / v8 / v10 / 12 | `.pt` | Ultralytics (PyTorch) | 官方权重，自动下载 |
| RT-DETR | `.pt` | Ultralytics | Transformer 检测器（非 YOLO） |
| YOLO-World | `.pt` | Ultralytics | 开放词汇，可自定义目标 |
| 任意 YOLO 风格 ONNX | `.onnx` | ONNX Runtime | CPU / CUDA / TensorRT / DirectML / OpenVINO |
| 通用检测 ONNX | `.onnx` | ONNX Runtime | 通过输出布局识别解码 |
| OpenVINO IR | `.xml` + `.bin` | OpenVINO | Intel 核显 / 独显 / NPU |
| 自定义 | `.pt` / `.onnx` / `.xml` / `.engine` | 对应后端 | 放在 `data/models/` |

> 分类（-cls）、分割（-seg）、姿态（-pose）、OBB 模型不在当前检测管线内，
> 请使用检测（detect）模型。

## 2. 内置模型

| Key | 名称 | 类型 | 大小 | 备注 |
| --- | --- | --- | --- | --- |
| `yolo26n` / `s` / `m` | YOLO26 | PyTorch | 5–42MB | 最新一代，端到端 |
| `yolo11n` / `s` / `m` | YOLO11 | PyTorch | 5–39MB | 默认，稳定 |
| `yolov8n` / `s` | YOLOv8 | PyTorch | 6–22MB | 兼容性最好 |
| `yolov8n-human` | YOLOv8n-human | PyTorch | 6MB | 纯人形，误报低 |
| `yolov10n` | YOLOv10n | PyTorch | 6MB | 无 NMS |
| `yolo12n` | YOLO12n | PyTorch | 6MB | 注意力机制 |
| `rtdetr-l` | RT-DETR-L | PyTorch | 63MB | 非 YOLO，遮挡更稳 |
| `yolov8s-worldv2` | YOLO-World v2 | PyTorch | 24MB | 开放词汇 |
| `yolo26n-onnx` 等 | ONNX 预导出 | ONNX | 10–36MB | 免转换 |

## 3. 推理后端

### 3.1 自动选择（推荐）

后端 `auto` 会根据模型后缀与已安装的运行时选择：

| 模型后缀 | 实际后端 |
| --- | --- |
| `.pt` | Ultralytics |
| `.onnx` | ONNX Runtime |
| `.xml` | OpenVINO |
| `.engine` | ONNX Runtime / TensorRT（若可用） |

### 3.2 推理设备

| 设备值 | 含义 |
| --- | --- |
| `auto` | 按可用后端自动（CUDA → DirectML → OpenVINO GPU → CPU） |
| `cpu` | CPU |
| `cuda:0` | NVIDIA CUDA |
| `dml` | DirectML（Windows，Intel / AMD / NVIDIA） |
| `openvino` / `GPU` / `NPU` | OpenVINO 设备 |
| `xpu` | Intel Extension for PyTorch |
| `tensorrt` | ONNX Runtime TensorRT EP |

## 4. 安装加速运行时

### ONNX Runtime

```bash
# CPU
pip install onnxruntime
# NVIDIA GPU
pip install onnxruntime-gpu
# Windows 通用 GPU（Intel/AMD/NVIDIA）
pip install onnxruntime-directml
# Intel 核显（OpenVINO EP）
pip install onnxruntime-openvino
```

> 同一时间只能安装一个 `onnxruntime*` 包；切换时先卸载已有的。
>
> 建议使用 **Python 3.10–3.13**：截至发布时，部分推理运行时（onnxruntime / openvino）
> 尚未提供 Python 3.14 的预编译轮子，装不上时可改用 3.12 创建虚拟环境。

### OpenVINO（Intel 最佳）

```bash
pip install openvino
```

### PyTorch / Ultralytics

```bash
pip install ultralytics
# NVIDIA
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
# Intel XPU
pip install intel-extension-for-pytorch
# DirectML（Windows，AMD/Intel）
pip install torch-directml
```

## 5. 导出 ONNX / OpenVINO

在「模型库」中，已下载的 `.pt` 模型可点「导出」：

* 导出 ONNX：通用，可交给 ONNX Runtime；
* 导出 OpenVINO：Intel 核显/独显性能最佳。

导出在后台任务中执行，可在任务列表查看进度；产物位于 `data/models/`。

命令行等价操作：

```bash
python -m cxonvif models download yolo11n
python -c "from ultralytics import YOLO; YOLO('data/models/yolo11n.pt').export(format='onnx')"
```

也可以直接下载官方预导出的 ONNX 模型（`yolo11n-onnx` 等），省去转换。

## 6. 自定义模型

1. 把模型文件放进数据目录的 `models/` 子目录
   （Windows 默认 `C:\ProgramData\ChengXingOnvif\models`）
2. 刷新「模型库」，自定义模型会出现在列表底部
3. 在摄像机检测设置中选择该模型

类别名称处理：

* `.pt`：读取模型内置 `names`
* `.onnx`：默认按 COCO 80 类，可在 `detect.classMap` 中重映射
* 类别编号对应不上时，检测框仍会输出，但目标组可能落入 `other`（不会触发事件）

## 7. 目标组与事件映射

模型原始类别 → 目标组：

```
person                      → person（人形）
car / truck / bus / ...     → vehicle（车辆）
dog / cat / bird / ...      → animal（动物）
backpack / handbag / ...    → package（物品）
其他                        → other（不触发事件，除非 targets 包含 other）
```

可在摄像机配置的 `detect.classMap` 中覆盖，例如把 `car` 映射为 `vehicle`。

## 8. 性能建议

| 场景 | 建议 |
| --- | --- |
| 4 路 1080p | YOLO11n / YOLO26n，5 FPS，开启运动门控 |
| 8 路以上 | 降低分析宽度到 640–800，检测 3 FPS，使用 GPU 推理 |
| 人形准确率 | `yolov8n-human` 或 YOLO11s + 0.5 置信度 |
| 夜间/逆光 | 提高置信度阈值，配合区域排除误报 |
| NVIDIA 显卡 | ONNX Runtime CUDA 或 TensorRT，`cuda:0` |
| Intel 核显 | OpenVINO GPU（导出 IR 后效果最佳） |

## 9. 许可提醒

Ultralytics 权重与 `ultralytics` 包为 **AGPL-3.0**；商业闭源分发需购买企业许可，
或使用自训练模型 / 其他许可模型。ONNX Runtime、OpenVINO 为宽松许可。
