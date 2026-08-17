# Panasonic Standard 输入支持

[English](README.md) | [简体中文](README_zh-CN.md)

本目录为 V-Log Alchemy v1.3 增加 Panasonic `Standard` 照片格调输入支持。`Conversion` 中的 33 点 LUT 会先把指定机型的 Standard 输出近似转换为 V-Log/V-Gamut 编码，再交给本仓库原有的 V-Log 风格 LUT。

## 推荐：相机双 LUT

支持双 LUT 的相机不需要预先合并：

1. 在 My Photo Style 中将 `Conversion` 里对应机型的 `*S2V.cube` 设为 `LUT1`。
2. 将 V-Log Alchemy 原有的 V-Log 风格 LUT 设为 `LUT2`。
3. `LUT1` 和 `LUT2` 的 LUT 浓度都先设为 `100%`；只需减弱风格时，仅降低 `LUT2`。
4. 其余照片格调调整先保持 `0`，视频亮度范围使用 full range。

Panasonic 的双 LUT 是严格串联：`LUT2(LUT1(image))`。基础照片格调由 `LUT1` 决定，因此转换 LUT 必须位于 `LUT1`，而且第二行必须是：

```text
#LUMIXPHOTOSTYLE STD
```

原 V-Log 风格 LUT 放在 `LUT2`。不要交换顺序，也不要降低 `LUT1` 浓度，否则传入 `LUT2` 的信号不再是正确的 V-Log 编码。

## 单 LUT 合并

Windows 用户可双击 `Tools/merge_standard_luts.bat` 打开图形界面，也可以运行命令行工具：

```powershell
py Tools\merge_standard_luts.py --model S1RII `
  --lut1 Luts\Fujifilm\FLog2C_to_CLASSIC-Neg_VLog.cube `
  --lut2 Luts\Leica\L-Log_to_Classic_VLog.cube `
  --output-dir Standard-LUTs
```

工具会把两个输入分别转换成两个 Standard 输入 LUT，方便切换。直接运行 Python 脚本且不带参数也会打开图形界面。需要模拟相机的 LUT1 -> LUT2 串联时，可选择 `chain` 模式；这种模式输出一个合并文件。

所有输出均为相机可用的 33 点 full-range `.cube`，并在 `TITLE` 后立即写入 `#LUMIXPHOTOSTYLE STD`。在 FAT32 卡上，文件基本名最多 8 个字符；工具默认生成符合限制的名称。

## 机型与文件

| 机型 | 转换 LUT | SILKYPIX 组 | 双 LUT / 机内使用 |
|---|---|---|---|
| GH6 | `GH6S2V.cube` | L001 | 仅后期/研究；GH6 只有 V-Log View Assist，不能把 LUT 烧录到 Standard 拍摄结果 |
| S5II | `S5IIS2V.cube` | L002 | 双 LUT 需固件 3.1 或更新 |
| S5IIX | `S5IIXS2V.cube` | L002 | 双 LUT 需固件 2.1 或更新 |
| G9II | `G9IIS2V.cube` | L003 | 双 LUT 需固件 2.2 或更新 |
| GH7 | `GH7S2V.cube` | L004 | 支持双 LUT |
| S9 | `S9S2V.cube` | L005 | 支持双 LUT |
| S1IIE | `S1IIES2V.cube` | L006 | 支持双 LUT |
| S1RII / DC-S1RM2 | `S1RIIS2V.cube` | L007 | 支持双 LUT |
| S1II | `S1IIS2V.cube` | L008 | 支持双 LUT |
| DC-L10 | `L10S2V.cube` | L009 | 支持双 LUT |

S5II 与 S5IIX 使用同一 SILKYPIX 映射，但提供两个文件别名。G9II 与 GH7 的已解码映射相同，仍保留独立入口。其它 Panasonic 机型不能仅凭传感器尺寸或世代直接复用这些 LUT。

## 生成依据

这些 LUT 由 SILKYPIX Developer Studio 8 SE 的同机型前向表进行全局拟合。对共享的内部样本 `x_i`：

```text
Standard RGB = F_standard(internal RGB)
V-Log RGB    = F_vlog(internal RGB)
拟合 L，使 L(F_standard(x_i)) ~= F_vlog(x_i)
```

完整 LUT 节点在同一个正则最小二乘目标中联合求解，不再为每个输出节点单独选择 Standard 伪逆。目标包含二阶平滑、严格中性轴约束、受控相机配对，以及只在弱覆盖节点起作用的 v1.3 内容一致原版弱先验。9 点控制网格最终重采样为相机可用的 33 点 LUT。

Standard 表为 129 点，V-Log 主表为 257 点，暗部细化表为 17 点。正向采样使用 SILKYPIX 的三线性插值、odd/even 表的中点混合，并在三个通道均低于主表 `1/64` domain 时使用暗部表。

| 组 | V-Log domain max | Shadow domain max |
|---|---:|---:|
| L001 | 2.0 | 0.03125 |
| L002 | 7.1 | 0.1109375 |
| L003 | 4.0 | 0.0625 |
| L004 | 4.0 | 0.0625 |
| L005 | 7.1 | 0.1109375 |
| L006 | 7.0 | 0.109375 |
| L007 | 2.8 | 0.04375 |
| L008 | 8.0 | 0.125 |
| L009 | 4.0 | 0.0625 |

### 固定 V-Log 终点与受控约束

每张文件都由对应机型组自己的 Standard/V-Log 前向表独立拟合；S1RII LUT 不会
复制给其它机型。但所有拟合都以同一套固定 Panasonic V-Log/V-Gamut 编码为终点，
并共享 S1RII 受控终点配对。这取代了 v1.5 的对手色度输出补丁；v1.6 不再叠加
独立的拟合后补色。

受控数据包含四档曝光下 72 个 SpyderCHECKR 24 彩色色块，以及 +1/+2 EV 的
20,519 个配准场景样本；四档真人手部场景全部留出。相对机内原生 V-Log，青色色块
平均 RGB 距离在 V-Log 中为 `0.00423`、经过 Classic Neg 后为 `0.01225`；v1.5
分别为 `0.04571` 和 `0.08173`。完全留出的真人手部由 `0.02135`/`0.05644`
改善到 `0.00392`/`0.00961`。

带哈希锁定的锚点、拟合参数、源/输出哈希、逐机型报告和完整受控结果见
[`Calibration/PanasonicForwardPairGlobalFit.json`](Calibration/PanasonicForwardPairGlobalFit.json)
与 [`Calibration/S1RIIControlledValidation.json`](Calibration/S1RIIControlledValidation.json)。
提供 SILKYPIX 解码表和 v1.3 Panasonic 包后，`Tools/rebuild_panasonic_forward_pairs.py`
可一次重建全部 10 张适配器。

在相同名义 ISO、光圈和快门下，本次验证的原生 V-Log RAW 信号约为 Standard
RAW 的 `0.397x`，相差约 `1.33` 档。这属于采集/增益路径差异；输出 LUT 无法复制
原生 V-Log 的噪声、高光余量和曝光索引行为。

## 对照样张

[`Samples/Panasonic-Standard/README_zh-CN.md`](../../Samples/Panasonic-Standard/README_zh-CN.md) 包含两种风格的双 LUT/单 LUT 全分辨率等价性对比，以及 Standard/原生 V-Log 受控对照。

## 限制

- Standard 已经裁掉的高光、饱和色和动态范围无法由 LUT 恢复；歧义输入只能得到全局正则化的条件估计。
- 结果只适用于 Panasonic `Standard` 照片格调，不适用于 Natural、Cinelike、709 Like 或相机内额外调整后的不同曲线。
- 双 LUT 路径比单个 33 点合并 LUT 少一次重新采样，通常是支持机型上的首选。
- Panasonic 没有公开相机 `.cube` 的插值算法。文件使用 33 点以降低不同插值实现造成的误差。
- 公共终点约束已在 DC-S1RM2 固件 1.5 上完成定量验证，并有 S9 的定性实拍佐证；其它机型保留各自前向表，但仍待补充对应机型的受控配对实拍。

官方参考：

- [S1RII 完整手册 PDF](https://panasonic.jp/content/dam/panasonic/jp/ja/pim-assets/support/manual/000/000/003/190/256/000000003190256/dc_s1rm2.pdf)：照片格调、LUT Library、双 LUT 顺序与 base Photo Style。
- [S5II LUT Library](https://eww.pavc.panasonic.co.jp/dscoi/DC-S5M2/html/DC-S5M2_DVQP2839_eng/0071.html)：Cube 尺寸、full range 与 FAT32 文件名限制。
- [DC-L10 完整手册 PDF](https://panasonic.jp/content/dam/panasonic/jp/ja/pim-assets/support/manual/000/000/004/377/759/000000004377759/dc_l10.pdf)：双 LUT 与 Standard base tag 支持。
