# 题库录入工作指南

本仓库维护高中数学题库、知识点树与考试数据。所有素材都经过 Markdown 预处理，再转换成 SQL 入库。以下流程与规范为最新版本。

## 1. 总体流程

1. **解析原题** → 通过 OCR/LLM 得到结构化 Markdown。
2. **整理 Markdown** → 按本文的字段与格式补全题干、选项、难度、知识点、图片。
3. **生成 SQL** → 将 Markdown 映射为 `INSERT` 语句（建议按题型批量生成）。
4. **导入与校验** → 在 PostgreSQL 中执行 SQL，随后运行 `test/show_*.sql` 验证表结构和内容。
5. **前端验收** → 抽查渲染效果，重点确认公式、图片、列表和多级题干。

## 2. Markdown 数据结构

- 每道题均放在 `exam/<name>.md` 中，按题号递增，以 `### <question_number>` 标记。
- 公共元信息放在文件开头的 `info` 区域，例如省份列表、考试名称等。
- 题目字段顺序为：
  1. `**question_type**`
  2. `**difficulty**`（1–5）
  3. `**kp_names**:`（全部清空，无内容，仅保留字段名）
  4. `**question_text**`
  5. 选项或子问（按题型组织）
  6. `**correct_answer**`（暂缺可留空）
- 多选题的 `**correct_answer**` 采用空格分隔选项（示例：`A B D`），避免混用中英文逗号。
- 解答题使用无序列表表示小问；若有图片，在题干字段后单独插入 `![描述](相对路径)`。
- 解答题的小问采用无序列表列出内容，文本中不要额外加“(1)(2)”等编号。
- 解答题的小问结尾不加句号、分号等标点

## 3. 题面排版约束

- 题干与小问结尾不要加句号、分号等标点，确保后续解析简单。
- 列表项（选项、步骤、小问）之间插入一个空行，避免 Markdown 渲染成单段文本。
- **数学表达式 LaTeX 规范**：
  - 所有数字和公式必须用 LaTeX 表示，行内公式写在 `$...$` 中
  - 中文汉字不用 LaTeX 公式包围
  - LaTeX 公式可以有必要的空格，但不能为了排版而空格
  - 不要混用 HTML 标签
- 选择题的待选位置写作 `$(\quad)$`；填空题答案横线写成 `$\underline{\qquad\qquad}$`。
- 平行关系使用标准 LaTeX 写法 `\parallel`（例如 $AB\parallel CD$）。

### 常用 LaTeX 写法

| 类别 | 写法 | 示例 |
| --- | --- | --- |
| 基本运算 | `a+b`, `a-b`, `a\times b`, `a\div b` | $a+b$, $a\times b$ |
| 分数根式 | `\dfrac{m}{n}`, `\sqrt{x}`, `\sqrt[n]{x}` | $\dfrac{1}{2}$, $\sqrt{16}$ |
| 比较符号 | `=`, `\neq`, `\lt`, `\gt`, `\leq`, `\geq` | $x\leq y$ |
| 三角函数 | `\sin`, `\cos`, `\tan` | $\sin \theta$ |
| 指数对数 | `e^{x}`, `\ln x`, `\log_a b` | $\ln x$, $\log_2 8$ |
| 集合符号 | `\in`, `\subset`, `\cap`, `\cup`, `\mid` | $A\cap B$, $x\mid y$ |
| 补集符号 | `\complement_{U}A` | $\complement_{U}A$ |
| 角度与平行 | `^\circ`, `\angle`, `\parallel` | $\angle ABC$, $AB\parallel CD$ |

## 4. 知识点处理

- `kp_names` 字段必须保留但不填写任何内容，只保留 `**kp_names**:` 字段名。
- 知识点清单位于 `knowledge_points/knowledge_points_init.sql`，将来可用脚本解析生成名称→ID 的映射。
- 后续由自动化工具或人工根据题目内容补充知识点。

## 5. 资源与路径

- 图片文件统一放在 `image/` 目录，文件名采用“年份+试卷名称+题号+图片序号”命名，例如 `image/2025_新高考一卷_6_1.svg`、`image/2025-新高考二卷_17_1.svg`。
- Markdown 中引用图片时使用相对路径（例如 `![图示](../image/2025_新高考一卷_6_1.svg)`）。
- 若题干或子问拥有多张图片，应在 SQL 的 `image_filename[]` 中保持一致的顺序与数量。

## 6. SQL 生成要点

- `questions` 表写入时，根据 `question_type` 选择对应复合类型列，其余复合列置 `NULL`。
- `difficulty` 为 1–5 的整数，`kp_ids` 在最终导入时用映射得到的 ID 数组（如 `ARRAY[68]`）。
- `exams` 表的 `questions` 字段需要 `ROW(question_num, question_id)` 的数组，按题号排序。

## 7. 校验清单

- `psql -f test/show_knowledge_points.sql` → 检查知识点层级与编码。
- `psql -f test/show_questions.sql` → 核对题型、难度、知识点 ID 与图片字段。
- `psql -f test/show_exams.sql` → 确认题目在试卷中的顺序与 province 列表。
- 如发现渲染问题，优先检查 Markdown 是否符合规范要求（空行、标点、LaTeX 格式、图片路径等）。
- 重点检查 LaTeX 公式规范：数字必须用 LaTeX，中文汉字不用 LaTeX 包围。

更新本指南时，请同步调整 Markdown 模板与自动化脚本，保持字段名称一致。
