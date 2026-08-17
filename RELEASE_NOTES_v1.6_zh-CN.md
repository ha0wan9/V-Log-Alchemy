# V-Log Alchemy v1.6

## Panasonic 全局正向配对重建

v1.6 用一套整体重建方法取代 Panasonic Standard 适配器原有的逐点伪逆，以及
v1.5 的对手色度输出补丁。完整 LUT 节点由解码前向表配对联合求解：

```text
Standard RGB = F_standard(internal RGB)
V-Log RGB    = F_vlog(internal RGB)
拟合 L，使 L(F_standard(x_i)) ~= F_vlog(x_i)
```

数据项、二阶平滑、严格中性轴、v1.3 弱先验和受控相机配对在同一个目标中优化。
不再逐点反解 Standard，也不再在结果后叠加补色。

本次分别重建全部 10 张适配器：GH6、S5II、S5IIX、G9II、GH7、S9、S1IIE、
S1RII、S1II 和 DC-L10。每张文件仍使用对应机型组自己的 Standard/V-Log
前向表；它们只共享固定 Panasonic V-Log/V-Gamut 终点和 S1RII 受控约束，
不会把 S1RII LUT 直接复制到其它相机。

## S1RII 受控验证

拟合数据来自 DC-S1RM2/S1RII 固件 1.5，在固定室内光源、固定自定义白平衡、
ISO 800、f/5.6 下拍摄：

- 0/+1/+2/+3 EV 共 72 个 SpyderCHECKR 24 彩色色块；
- +1/+2 EV 共 20,519 个低梯度配准场景样本；
- 四档真人手部场景全部排除在拟合之外。

下表为归一化 `[0,1]` V-Log RGB 码值空间的欧氏距离，不是 Delta E。每档曝光
只移除一个由中性色估计的标量码值偏移，不进行对手色对齐。

| 验证集 | v1.3 | v1.5 | v1.6 |
|---|---:|---:|---:|
| 全部色卡彩色块，V-Log | 0.09232 | 0.07293 | **0.00335** |
| 全部色卡彩色块，Classic Neg | 0.16896 | 0.13270 | **0.00508** |
| 青色色块，V-Log | 0.10412 | 0.04571 | **0.00423** |
| 青色色块，Classic Neg | 0.31953 | 0.08173 | **0.01225** |
| 完全留出真人手部，V-Log | 0.02180 | 0.02135 | **0.00392** |
| 完全留出真人手部，Classic Neg | 0.03228 | 0.05644 | **0.00961** |

展示的 +2 EV 人偶上臂在 V-Log 中的中位 RGB 误差为 `0.00255`，经过 Classic
Neg 后为 `0.00454`；四档人偶场景汇总为 `0.01062` 和 `0.01742`。

## 可复现性与包内容变化

- 新增 `Tools/fit_panasonic_forward_pairs.py`：矩阵无关的全局正则求解器，使用
  三线性回放并严格记录收敛状态。
- 新增 `Tools/rebuild_panasonic_forward_pairs.py`：使用解码表和内容一致的 v1.3
  先验，一次重建并整理全部 10 张机型适配器。
- 新增带哈希锁定的 20,591 样本受控锚点及元数据。
- `Calibration` 记录完整拟合参数、源/输出哈希、逐机型验证和 S1RII 受控结果。
- 30 个 RGB 求解通道全部达到低于 `1e-7` 的相对残差阈值；发布 LUT 保持严格
  中性轴与相机安全头部。
- 移除 v1.5 多项式补色及其应用工具；v1.6 是直接全局拟合，不是修补 v1.5。
- 重新生成两张 S1RII 单 LUT 示例。全分辨率双 LUT/单 LUT 平均差异为
  `0.153` 和 `0.147` 个 8-bit LSB。

## 限制

Standard 的裁切、色域压缩和多对一区域仍不可逆；歧义区域只能得到全局正则化的
条件估计。目前只有 S1RII 完成受控定量实拍验证；S9 在 issue #12 中有独立实拍
证据，其余机型组仍需对应机型的 Standard/原生 V-Log 配对测试。

输出 LUT 也无法复制原生 V-Log 的采集增益、噪声或高光余量。

## English

[Read the v1.6 English release notes](https://github.com/shenmintao/V-Log-Alchemy/blob/v1.6/RELEASE_NOTES_v1.6.md)
