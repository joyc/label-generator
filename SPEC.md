# Label Generator — Project Specification

## 目标

批量生成商品（服装）打印标签图片。输入一个 CSV/Excel 表格（每行一个商品），输出对应数量的 PNG 图片文件。每张图片 = 模板底图 + 叠加的商品变量（size、品类、商品型号、颜色、JAN 条码等）。

## 输入 / 输出

### 输入
- **模板图片**: `config/template.png`（打印用底图，已含 logo、固定文字、圆角框等不变元素）
- **坐标配置**: `config/layout.json`（每个变量的像素坐标、字号、对齐方式、旋转）
- **数据源**: `data/products.csv` 或 `data/products.xlsx`（列名需匹配 layout.json 中的 key）
- **字体**: `fonts/NotoSansCJK-Regular.otf` 和 `fonts/NotoSansCJK-Bold.otf`（中日文兼容）

### 输出
- `output/{sku}.png` —— 每行数据生成一张图

## CSV 列规范

| 列名 | 类型 | 说明 |
|------|------|------|
| sku | string | 商品唯一标识，作为输出文件名 |
| size | string | 尺码，如 S/M/L/XL |
| category | string | 品类标签，进圆角框，如 "半袖"/"長袖" |
| sku_code | string | 商品型号码，如 "J25011BLM" |
| color_name | string | 颜色/款式说明，如 "A．ブルーチェック" |
| jan | string | JAN-13 条码，12 位原码或 13 位完整码都可接受 |

## layout.json 格式

每个 key 对应 CSV 的列名，value 定义在模板上的位置与样式。所有文字推荐用 `anchor="mm"`（中心锚点），`xy` 直接描述字符中心，坐标更直观。

```json
{
  "_meta": {
    "template_size": [591, 354],
    "font": "fonts/NotoSansCJK-Regular.otf",
    "bold_font": "fonts/NotoSansCJK-Bold.otf"
  },

  "size": {
    "type": "text",
    "xy": [157, 132],
    "font_size": 64,
    "anchor": "mm",
    "color": "#000000",
    "bold": true
  },

  "category": {
    "type": "text",
    "xy": [304, 138],
    "font_size": 48,
    "anchor": "mm",
    "bold": true,
    "max_width": 150
  },

  "sku_code": {
    "type": "text",
    "xy": [235, 232],
    "font_size": 22,
    "anchor": "mm"
  },

  "color_name": {
    "type": "text",
    "xy": [235, 260],
    "font_size": 22,
    "anchor": "mm",
    "max_width": 320
  },

  "jan": {
    "type": "barcode",
    "format": "ean13",
    "xy": [509, 214],
    "anchor": "mm",
    "width": 210,
    "height": 130,
    "rotation": 90,
    "show_text": true
  }
}
```

### 字段说明

**通用字段（text 和 barcode 共用）**
- `type`: `"text"` 或 `"barcode"`
- `xy`: `[x, y]` 像素坐标
- `anchor`: 锚点，默认 `"lt"`。PIL 标准记法：首字母为水平对齐（l=left, m=middle, r=right），次字母为垂直对齐（t=top, m=middle, b=bottom, s=baseline）。推荐用 `"mm"` 做中心对齐。

**text 专属**
- `font_size`: 字号（像素）
- `color`: 十六进制颜色，默认 `"#000000"`
- `bold`: 是否用粗体字体，默认 `false`
- `max_width`: 最大文字宽度（像素），超出时按规则换行或截断

**barcode 专属**
- `format`: 条码类型，当前仅支持 `"ean13"`
- `width` / `height`: 条码**旋转前**的尺寸（即水平状态下的宽和高）
- `rotation`: 旋转角度（度），逆时针为正。常用值：`0` 水平、`90` 逆时针旋转后数字从上读到下
- `show_text`: 条码下方是否显示数字

### anchor 使用示例
- `"lt"`: xy 指向文字左上角
- `"mm"`: xy 指向文字中心（推荐，尤其放入预画框内居中时）
- `"rt"`: xy 指向文字右上角（右对齐数字金额常用）

## 技术栈

- **Python**: 3.11+
- **Pillow**: 图像渲染主力
- **python-barcode**: JAN/EAN-13 条码生成（版本 >=0.15.1，避免 Pillow 10+ 的 `getsize` 兼容问题）
- **pandas**: 读 CSV/Excel
- **typer** 或 argparse: CLI 入口
- 依赖管理用 `pyproject.toml` + `pip`，不要上 poetry

## 项目结构

```
label-generator/
├── SPEC.md
├── README.md
├── pyproject.toml
├── requirements.txt
├── .gitignore
├── config/
│   ├── template.png
│   └── layout.json
├── data/
│   └── products.csv           # 示例数据
├── fonts/
│   ├── NotoSansCJK-Regular.otf
│   └── NotoSansCJK-Bold.otf
├── output/                     # .gitignore 掉
├── src/
│   └── label_generator/
│       ├── __init__.py
│       ├── renderer.py         # 核心：LabelRenderer 类
│       ├── barcode_gen.py      # JAN-13 条码生成（含旋转）
│       ├── config.py           # 加载 layout.json
│       ├── data_loader.py      # 读 CSV/Excel
│       └── cli.py              # 命令行入口
└── tests/
    └── test_renderer.py
```

## 关键实现点

### 1. 字体加载
- 显式加载 `fonts/NotoSansCJK-Regular.otf` 和 `NotoSansCJK-Bold.otf`，**禁止**依赖系统字体。
- `bold: true` 时用 Bold 字体文件，否则用 Regular。
- 字体对象按 `(path, size)` 缓存（`functools.lru_cache`），避免每行重新加载。

### 2. 文字自动换行 / 截断
- 如果 layout 里指定了 `max_width`，文字超宽时按字符断行（中日文按字符，英文按单词）。
- 超过 2 行时截断并加 `…`。
- 用 `font.getbbox(text)` 量宽度，**不要**用过时的 `font.getsize`。

### 3. JAN-13 条码
- 用 `python-barcode` 的 `EAN13` 类 + `ImageWriter` 直接输出 PNG（不要走 SVG 再转，会失真）。
- 输入 12 位时自动补校验位；输入 13 位时验证校验位正确性，错了就报错并跳过该行。
- 生成流程：
  1. 生成水平 EAN-13 PNG（原始尺寸由 `python-barcode` 决定）
  2. 按 layout 的 `width` × `height` resize
  3. 如果 `rotation != 0`，调用 `img.rotate(rotation, expand=True)`
  4. 根据 `anchor` 和 `xy` 计算最终左上角粘贴坐标，`Image.paste` 到模板上
- `show_text` 控制条码下方是否显示数字。传给 `ImageWriter` 的 options 里设 `write_text` 参数。

### 4. anchor 坐标换算
渲染文字和贴条码都需要把 `(xy, anchor)` 换算成实际左上角坐标。对于文字，PIL 的 `draw.text(xy, text, font, anchor)` 原生支持 anchor 参数，直接传。对于条码（`Image.paste` 不支持 anchor），需要先根据旋转后的图像尺寸手动计算左上角：

```python
# 伪代码
bw, bh = rotated_barcode.size
if anchor == "mm":
    paste_x, paste_y = xy[0] - bw // 2, xy[1] - bh // 2
elif anchor == "lt":
    paste_x, paste_y = xy
# ... 其他情况
```

### 5. 坐标系
- 原点在左上角，x 向右，y 向下（PIL 标准）。
- 所有像素坐标以**模板图实际尺寸**为准（当前模板 591×354）。

### 6. 文件命名
- 输出文件名用 `{sku}.png`，sku 缺失时用 `{jan}.png`，都缺失则用行号 `row_{i}.png`。
- 非法字符（`/\:*?"<>|`）替换为 `_`。

## CLI 用法

```bash
python -m label_generator.cli \
  --data data/products.csv \
  --template config/template.png \
  --layout config/layout.json \
  --output output/
```

默认参数走上面的路径，无参直接能跑。

## 错误处理

- 数据列缺失 → 启动时一次性报出所有缺失列，别一行一行报。
- JAN 校验失败 → 跳过该行，汇总打印失败列表，不要中断全流程。
- 模板/字体/layout 文件缺失 → 启动时 fail fast，给出明确路径提示。
- `layout.json` 里引用了 CSV 不存在的列 → 启动时报错。
- layout 里 `type` 是 `text` 但值是空字符串 → 跳过渲染，不报错（允许可选字段）。
- `_meta` 开头的 key 不作为渲染字段处理，仅供元信息使用。

## MVP 范围（先实现这些）

1. 读 CSV
2. 加载模板 + layout.json（含 `_meta` 块的跳过处理）
3. 渲染文字（中日文 + bold + anchor + max_width 换行）
4. 生成并贴 JAN-13 条码（含旋转）
5. 批量输出 PNG
6. CLI 入口跑通

## 后续扩展（先不做）

- Excel 读取（pandas 已经能做，加个 `.xlsx` 分支即可）
- 多页 PDF 合并输出（ReportLab）
- ZPL 直出（接 Zebra 打印机）
- Web UI（FastAPI + 预览）
- 字号自适应（文字太长时自动缩小字号）

## 示例数据

生成 `data/products.csv`，至少包含 5 行，覆盖不同 size、品类、颜色款式，测试中日文渲染：

```csv
sku,size,category,sku_code,color_name,jan
PJM001,M,半袖,J25011BLM,A．ブルーチェック,490123456789
PJM002,L,半袖,J25011PNK,B．ピンクストライプ,490123456780
PJM003,S,長袖,J25012WHT,C．ホワイト,490123456781
PJM004,XL,半袖,J25013NVY,D．ネイビーチェック,490123456782
PJM005,M,長袖,J25012GRY,E．グレー無地,490123456783
```

## 验証標準

運行 `python -m label_generator.cli` 后：
- `output/` 下有 5 个 PNG，文件名为 `PJM001.png` ~ `PJM005.png`
- 視覚対比 `PJM001.png` 与設計成品図（`M` 在左、`半袖` 在圆角框内、JAN 竖排在右侧）応高度一致
- 用手机条码扫描 APP 扫描任一张图，能识别出対応 JAN 码
- 中日文字符正常显示，不出現方块（未加载字体的典型症状）
- 长的 color_name 被正确换行或截断，不越过模板中心线进入条码区

## 模板现状备忘（本项目专用）

当前模板 `config/template.png` 尺寸 591×354，已包含以下固定元素（不要在代码中重复渲染）：
- 顶部 "WEAR SHOW" logo
- 中间圆角框（x=225-383, y=100-176），专用于放 `category`
- "綿100%パジャマセット"（y≈203）
- "株式会社MIDWAY / 中国製"（y≈314）

如果更换模板（换设计或换尺寸），只需更新 `template.png` 和 `layout.json`，**代码无需修改**。这是坐标外置化的设计意图。
