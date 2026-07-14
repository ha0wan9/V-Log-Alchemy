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

这些 LUT 来自 SILKYPIX Developer Studio 8 SE 的同机型前向表：

```text
Standard RGB = F_standard(internal RGB)
V-Log RGB    = F_vlog(internal RGB)
S2V RGB      = F_vlog(pseudo_inverse(F_standard(Standard RGB)))
```

Standard 表为 129 点，V-Log 主表为 257 点，暗部细化表为 17 点。生成时使用 SILKYPIX 的三线性采样方式、odd/even 表的中点混合，并在三个通道均低于主表 `1/64` domain 时使用暗部表。

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

## 对照样张

[`Samples/Panasonic-Standard/README_zh-CN.md`](../../Samples/Panasonic-Standard/README_zh-CN.md) 包含三种风格的双 LUT/单 LUT 等价性对比、全分辨率误差，以及 Standard ISO 4000 与原生 V-Log ISO 5000 的真实拍摄路径参考。

## 限制

- Standard 已经裁掉的高光、饱和色和动态范围无法由 LUT 恢复；这里使用的是规范化伪逆。
- 结果只适用于 Panasonic `Standard` 照片格调，不适用于 Natural、Cinelike、709 Like 或相机内额外调整后的不同曲线。
- 双 LUT 路径比单个 33 点合并 LUT 少一次重新采样，通常是支持机型上的首选。
- Panasonic 没有公开相机 `.cube` 的插值算法。文件使用 33 点以降低不同插值实现造成的误差。

官方参考：

- [S1RII 完整手册 PDF](https://panasonic.jp/content/dam/panasonic/jp/ja/pim-assets/support/manual/000/000/003/190/256/000000003190256/dc_s1rm2.pdf)：照片格调、LUT Library、双 LUT 顺序与 base Photo Style。
- [S5II LUT Library](https://eww.pavc.panasonic.co.jp/dscoi/DC-S5M2/html/DC-S5M2_DVQP2839_eng/0071.html)：Cube 尺寸、full range 与 FAT32 文件名限制。
- [DC-L10 完整手册 PDF](https://panasonic.jp/content/dam/panasonic/jp/ja/pim-assets/support/manual/000/000/004/377/759/000000004377759/dc_l10.pdf)：双 LUT 与 Standard base tag 支持。
