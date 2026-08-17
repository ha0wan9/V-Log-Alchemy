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
| Fujifilm Classic Neg. | 0.153 | 0.735 |
| Leica Classic | 0.147 | 0.840 |

因此两条路径不是逐像素完全相同，但平均差异低于 1 个 8-bit 码值。较大的局部差异主要来自两个 33 点 LUT 合并为一个 33 点 LUT后的重新采样，以及原风格 LUT 的强裁剪/高对比边界。支持双 LUT 的相机优先使用两层原始链，可避免这次额外烘焙。

## Standard / 原生 V-Log 受控对照

`S1RII_Controlled_Standard_vs_NativeVLog.jpg` 使用 DC-S1RM2 固件 1.5、
+2 EV 的受控 HIF 配对：

- `P1024433.HIF`：Standard、ISO 800、1/13 秒、f/5.6、固定自定义白平衡。
- `P1024430.HIF`：原生 V-Log；ISO、快门、光圈、白平衡、光源和构图相同，
  并配准到 Standard 画面。

图片展示 v1.6 转换与原生 V-Log 在 Classic Neg 前后的结果，以及放大的差异图。
评估对每档曝光只移除一个由中性色估计的 V-Log 标量码值偏移，不做对手色对齐。
四档色卡的青色平均 RGB 距离在 V-Log 中为 `0.00423`，经过 Classic Neg 后为
`0.01225`；完全留出的四档真人手部相应为 `0.00392` 和 `0.00961`。完整指标和
配准数据见 `controlled_profile_comparison.json` 与
`Luts/Panasonic-Standard/Calibration/S1RIIControlledValidation.json`。

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

`Generated-LUTs` 中包含这两张等价性样张使用的 S1RII v1.6 全局拟合示例 LUT，所有文件第二行均为 `#LUMIXPHOTOSTYLE STD`。
