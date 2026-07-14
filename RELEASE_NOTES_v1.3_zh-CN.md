# V-Log Alchemy v1.3

## 新增

- Panasonic Standard 输入支持，覆盖 GH6、S5II/S5IIX、G9II、GH7、S9、S1IIE、S1RII、S1II 和 DC-L10 的 SILKYPIX 机型映射。
- 10 个 33 点 `Standard -> V-Log` 转换 LUT，均使用 full range，并在 `TITLE` 后立即包含 `#LUMIXPHOTOSTYLE STD`。
- `Tools/merge_standard_luts.py`：按机型把一个或两个 V-Log 风格 LUT 转成 Standard 输入版本；支持命令行和 Tkinter 图形界面。
- 双 LUT 串联模式：可显式烘焙 `LUT2(LUT1(StandardToVLog(x)))`。
- 发布 manifest、SHA-256 清单、逐机型验证报告和 SILKYPIX RAW 对照样张。

## 相机双 LUT

支持机型推荐使用 My Photo Style：机型转换 LUT 放在 `LUT1`，原 V-Log Alchemy 风格 LUT 放在 `LUT2`，两层浓度均先设为 100%。Panasonic 会先应用 LUT1，再应用 LUT2；基础照片格调取自 LUT1。

S5II、S5IIX 和 G9II 的双 LUT 分别要求固件 3.1、2.1 和 2.2 或更新。GH6 只能将 LUT 用于 V-Log View Assist，不能把这条 Standard 双 LUT 链烧录到照片或视频。

## 限制

Standard 已经裁掉的高光、动态范围和饱和色信息无法恢复。转换采用规范化伪逆，目标是让 Standard 拍摄在可逆区域内尽量接近同 RAW 的 SILKYPIX V-Log 渲染，而不是把 Standard 重新变成真正的原始 V-Log 采集。
