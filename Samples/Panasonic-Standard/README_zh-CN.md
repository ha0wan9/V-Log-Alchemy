# Panasonic Standard 对照样张

[English](README.md) | [简体中文](README_zh-CN.md)

相机为 Panasonic DC-S1RM2 / S1RII。SILKYPIX 输出均为 8144×5424、RGB 16-bit、未压缩 TIFF、嵌入 sRGB ICC；仓库只发布缩小后的 JPEG 对照图和数值报告，不发布原 RAW/TIFF。

## 合并是否等价

两张 `*_Merge_Equality.jpg` 使用同一份 Standard TIFF 比较：

```text
路径 A：Standard -> S1RII S2V LUT -> 原 V-Log 风格 LUT
路径 B：Standard -> 合并生成的单个 STD LUT
```

右下角是 16 倍放大的绝对差异。全分辨率统计：

| 风格 | 平均误差（8-bit LSB） | P99（8-bit LSB） |
|---|---:|---:|
| Fujifilm Classic Neg. | 0.708 | 3.930 |
| Leica Classic | 0.493 | 3.293 |

因此两条路径不是逐像素完全相同，但平均差异低于 1 个 8-bit 码值。较大的局部差异主要来自两个 33 点 LUT 合并为一个 33 点 LUT后的重新采样，以及原风格 LUT 的强裁剪/高对比边界。支持双 LUT 的相机优先使用两层原始链，可避免这次额外烘焙。

## Standard / 原生 V-Log 受控对照

`S1RII_Controlled_Standard_vs_NativeVLog.jpg` 使用 DC-S1RM2 固件 1.5 的
受控 HIF 配对：

- `P1024418.HIF`：Standard、ISO 800、1/50 秒、f/5.6、固定手动白平衡。
- `P1024415.HIF`：原生 V-Log；ISO、快门、光圈、白平衡、光源和构图相同，
  并配准到 Standard 画面。

图片同时展示 v1.5 转换前后及 Classic Neg 结果，并与正式原生 V-Log 路径对照。
画面中的 LUT 输出没有做后期对齐；只有差异图会移除 RGB 中位偏移，以单独观察
颜色残差。对齐后，Classic Neg 在稳定像素中的平均 RGB 距离为 `0.0305`，青色
区域为 `0.0669`。完整指标和配准数据见 `controlled_profile_comparison.json`。

剩余差异是真实限制：Standard 已裁切的信息不可恢复，原生 V-Log RAW 的采集/
增益路径也无法由输出 LUT 复制。

## SILKYPIX 同 RAW 探针

SILKYPIX 8 SE 的 GUI 不会为 Standard 拍摄的 RAW 列出 V-Log，但引擎接受 sidecar 枚举：

```ini
COLOR_STATE=SPECIFIED
COLOR_PROPERTY=COLORUI_PROPERTY_PANA
COLOR_MODE=COLORUI_PROPERTY_VLOG
```

这能证明 V-Log 表存在并被调用，但 Standard 拍摄 RAW 缺少原生 V-Log 捕获时的增益/照片格调元数据，因此强制结果不作为最终等价样张。旧探针端点和合并说明记录在 `comparison_report.json`。

`Generated-LUTs` 中包含这两张等价性样张使用的 S1RII v1.5 校正示例 LUT，所有文件第二行均为 `#LUMIXPHOTOSTYLE STD`。
