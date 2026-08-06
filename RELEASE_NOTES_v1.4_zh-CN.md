# V-Log Alchemy v1.4

## 哈苏 LUT 改为可直接使用的显示输出

v1.3 及更早版本中的 4 个 Hasselblad RGB/D50 中间域 LUT，现已替换为 8 个
输出空间明确的显示 LUT：

- Hasselblad Standard 与 Nature
- Rec.709 与 sRGB 输出空间
- 适合相机/实时使用的 33 点版本，以及适合后期的 65 点版本

相机监看和视频流程使用 Rec.709；采用 sRGB 色彩管理的照片和桌面流程使用
sRGB。两套输出都是完整显示变换，无需后续 CST。

旧中间域 LUT 因 `.cube` 文件不携带 ICC 元数据而很容易被误用。为保证可复现，
它们仍可从 `v1.3` 标签获取，但不能把它们解释成 ACES AP1。

## 明确定义的色彩管线

显示转换现在明确执行：

1. 使用 gamma `2.19921875` 解码 Hasselblad RGB ICC TRC；
2. Hasselblad RGB 转 XYZ D50；
3. Bradford D50 到 D65 白点适配；
4. 转换到 BT.709/sRGB 原色；
5. 应用所选 BT.709 或 sRGB 输出传递函数。

超出目标色域的值会按通道裁切到 LUT 的 `0..1` 范围。这是定义明确的色度转换，
并不声称能精确复现尚未恢复的 Phocus 导出 ICC intent 或专有色域映射。

## 可复现生成器

- 移除所有作者本机绝对路径和外部私有 Python 模块依赖。
- 仓库内包含紧凑的日光 ColorCorrect 表、Standard film curve、Nature
  gradation，以及使用相对路径和 SHA-256 校验的 artifact manifest。
- 生成器默认输出改为 Rec.709；Hasselblad RGB/D50 中间域仅保留为名称明确的
  `hasselblad-rgb` 高级模式。
- 新增干净检出回归测试和 `Luts/Hasselblad/SHA256SUMS.txt`。
- 已验证隔离的暂存快照能够逐字节重新生成全部发布 LUT。

## 重新生成

```powershell
# 发布的 Rec.709 套装（默认）
python Tools\generate_hasselblad_vlog.py --all-styles --include-color-correct --highlight-rolloff

# 发布的 sRGB 套装
python Tools\generate_hasselblad_vlog.py --all-styles --include-color-correct --highlight-rolloff --output-space srgb
```

完整输出约定与限制见 `Luts/Hasselblad/README.md`。
