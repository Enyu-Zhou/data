# 题库录入工作指南

## 快速执行步骤

1. 生成符合规范的试卷 Markdown（例如 `exam/2025-新高考一卷.md`）
2. 运行 `scripts/ingest_exams.py` 将 Markdown 导入 PostgreSQL
3. 在 PostgreSQL 中查询、校验并使用题库数据

---

## 第 1 步：生成格式化 Markdown 试卷

### 目录与命名

- 所有试卷放在 `exam/` 目录；文件名统一为 `年份-试卷名称.md`，与试卷标题一致。
- 图片放在 `image/` 目录，命名为 `年份_试卷名称_题号_序号.svg`（或 `.png` 等）。
- Markdown 使用 UTF-8 编码，禁止在题干末尾添加多余空格。

### 标准模板

为便于模型从截图生成结构化 Markdown，务必从以下模板开始：

```markdown
# 2025-新高考一卷

## info

**province**: 浙江、山东、广东、福建、湖南、湖北、河北、江苏、江西、安徽、河南

### 1

**question_type**: single_choice

**difficulty**: 1

**kp_names**:

**question_text**: $(1+5i)i$的虚部为$(\quad)$

- A. $-1$

- B. $0$

- C. $1$

- D. $6$

**correct_answer**: C
```

> 按题号顺序重复 `### <number>` 段落，直到最后一题。

### 字段顺序与要求

- 每题字段严格按以下顺序出现：
  1. `**question_type**`: `single_choice` / `multiple_choice` / `fill_blank` / `problem_solving`
  2. `**difficulty**`: 1–5 的整数
  3. `**kp_names**:` 保留字段但不填写内容
  4. `**question_text**`: 题干内容，可跨多行
  5. 选项或子问（视题型决定）
  6. `**correct_answer**`: 单选填字母，多选填字母列表，填空/解答题写答案或留空
- 题干、选项、子问末尾不要加句号或分号。
- 多选题答案使用空格分隔字母（例如 `A B D`），脚本会转换为逗号分隔。
- 解答题（`problem_solving`）的小问使用无序列表（`-`），不可额外写 `(1)(2)`。
- 若题干或小问包含图片，置于对应段落下方，格式 `![描述](../image/文件名.svg)`。

### LaTeX 与文本规范

- 所有数学表达式使用 LaTeX：行内 `$...$`，必要时使用 `\dfrac`、`\sqrt` 等。
- 中文文字不要放入 `$...$` 中；英文字母、数字在公式中统一使用 LaTeX。
- 填空横线写作 `$\underline{\qquad\qquad}$`，选择题空格写作 `$(\quad)$`。
- 不使用 HTML 标签或自定义语法。

### 图片与资源

- 图片文件需与 Markdown 中的引用一致，扩展名保持小写。
- 同一题多张图片按出现顺序命名 `_1`、`_2` 等，并在 Markdown 中保持顺序一致。
- 若题目无图片，确保 Markdown 中没有残留的引用标记。

### 质量自检清单

- 核实题号连续且从 1 开始。
- 题干、选项、答案均无全角空格或不可见字符。
- 省份列表使用全角顿号或中文逗号分隔；脚本会自动拆分。
- 手动预览 Markdown（如在 VS Code 中）确认列表渲染正常。

---

## 第 2 步：导入 PostgreSQL

### 初始化数据库

1. 云端数据库地址 `101.126.70.212`，用户名 `zhouenyu`，数据库名 `group`，端口 `5432`，密码保存在 `~/.pgpass`。首次部署或需重建结构时执行：

   ```bash
   psql -h 101.126.70.212 -U zhouenyu -d group -f sql/001_init_create.sql
   ```

   `.pgpass` 会自动提供密码。如表结构已存在且无需调整，可跳过此步骤。

2. 确保安装 `psycopg`，建议命令：

   ```bash
   pip install "psycopg[binary]"
   ```

### 运行导入脚本

使用脚本 `scripts/ingest_exams.py` 将 Markdown 写入数据库：

```bash
python scripts/ingest_exams.py exam/2025-新高考一卷.md --dsn "postgresql://zhouenyu@101.126.70.212:5432/group"
```

- 多个文件可一次传入：`python scripts/ingest_exams.py exam/*.md --dsn "postgresql://zhouenyu@101.126.70.212:5432/group"`
- 使用 `--dry-run` 仅校验解析并输出计划操作，不写数据库。
- 日志中若出现 `Parsed exam ...` 表示解析成功；`Ingested exam ...` 表示完成写入。脚本会按照题号自动 upsert 题目、试卷与映射关系。

### 导入后校验

- 使用预置视图快速抽查写入结果（视图定义已在 `sql/001_init_create.sql` 中创建）：

  ```bash
  for f in sql/check_question_*_view.sql; do
    psql -h 101.126.70.212 -U zhouenyu -d group -f "$f"
  done
  ```

- 可再执行 `SELECT COUNT(*) FROM exam_question;`、`SELECT COUNT(*) FROM exam;` 等基础查询确认写入数量。
- 若仓库提供额外 `test/show_*.sql` 校验脚本，可继续使用 `psql -f` 方式运行。

---

## 第 3 步：通过视图查询 PostgreSQL 数据

进入云端数据库：

```bash
psql -h 101.126.70.212 -U zhouenyu -d group
```

四个视图已在 `sql/001_init_create.sql` 中定义，应用层只需访问视图即可拿到题目详情：

`question_single_choice_view`

| 字段 | 含义 | 类型 | 示例 |
| --- | --- | --- | --- |
| question_id | 题目主键 ID | `integer` | `6` |
| question_type | 题型枚举 | `question_type_enum` | `single_choice` |
| difficulty | 难度系数 | `integer` | `2` |
| created_at | 创建时间 | `timestamptz` | `2025-01-05 08:00:00+08` |
| updated_at | 最近更新 | `timestamptz` | `2025-01-05 08:10:00+08` |
| question_text | 题干（Markdown） | `text` | `$(1+5i)i$的虚部为$(\quad)$` |
| option_a | 选项 A | `text` | `$-1$` |
| option_b | 选项 B | `text` | `$0$` |
| option_c | 选项 C | `text` | `$1$` |
| option_d | 选项 D | `text` | `$6$` |
| image_filename | 图片文件名数组 | `varchar(100)[]` | `{"2025_一卷_6_1.svg"}` |
| correct_answer | 正确选项 | `char(1)` | `C` |
| explanation | 解析文本 | `text` | `虚部为实部...` |

`question_multiple_choice_view`

| 字段 | 含义 | 类型 | 示例 |
| --- | --- | --- | --- |
| question_id | 题目主键 ID | `integer` | `10` |
| question_type | 题型枚举 | `question_type_enum` | `multiple_choice` |
| difficulty | 难度系数 | `integer` | `2` |
| created_at | 创建时间 | `timestamptz` | `2025-01-05 08:00:00+08` |
| updated_at | 最近更新 | `timestamptz` | `2025-01-05 08:12:00+08` |
| question_text | 题干（Markdown） | `text` | `设抛物线$C:y^2=6x$...` |
| option_a | 选项 A | `text` | `结论 A` |
| option_b | 选项 B | `text` | `结论 B` |
| option_c | 选项 C | `text` | `结论 C` |
| option_d | 选项 D | `text` | `结论 D` |
| image_filename | 图片文件名数组 | `varchar(100)[]` | `NULL` |
| correct_answer | 正确选项数组 | `char(1)[]` | `{"B","D"}` |
| explanation | 解析文本 | `text` | `由焦点性质可得...` |

`question_fill_blank_view`

| 字段 | 含义 | 类型 | 示例 |
| --- | --- | --- | --- |
| question_id | 题目主键 ID | `integer` | `15` |
| question_type | 题型枚举 | `question_type_enum` | `fill_blank` |
| difficulty | 难度系数 | `integer` | `3` |
| created_at | 创建时间 | `timestamptz` | `2025-01-05 08:00:00+08` |
| updated_at | 最近更新 | `timestamptz` | `2025-01-05 08:14:00+08` |
| question_text | 题干（Markdown） | `text` | `函数$f(x)$的零点为$\underline{\qquad\qquad}$` |
| image_filename | 图片文件名数组 | `varchar(100)[]` | `NULL` |
| correct_answer | 填空答案 | `text` | `$x=2$` |
| explanation | 解析文本 | `text` | `代入方程求根...` |

`question_problem_solving_view`

| 字段 | 含义 | 类型 | 示例 |
| --- | --- | --- | --- |
| question_id | 题目主键 ID | `integer` | `18` |
| question_type | 题型枚举 | `question_type_enum` | `problem_solving` |
| difficulty | 难度系数 | `integer` | `4` |
| created_at | 创建时间 | `timestamptz` | `2025-01-05 08:00:00+08` |
| updated_at | 最近更新 | `timestamptz` | `2025-01-05 08:16:00+08` |
| parts | 主干及小问集合（顺序与 Markdown 保持一致） | `jsonb` | `[{"part_id":120,"part_number":null,"question_text":"主干","image_filename":null},{"part_id":121,"part_number":"1","question_text":"小问","image_filename":null}]` |

常用查询示例：

- 查询试卷中的单选题：

  ```sql
  SELECT eq.question_num,
         scv.question_text,
         ARRAY[scv.option_a, scv.option_b, scv.option_c, scv.option_d] AS options,
         scv.correct_answer
  FROM exam_question AS eq
  JOIN question_single_choice_view AS scv ON scv.question_id = eq.question_id
  WHERE eq.exam_id = 123
  ORDER BY eq.question_num;
  ```

- 查询多选题答案数组：

  ```sql
  SELECT question_id,
         question_text,
         correct_answer -- char(1)[]
  FROM question_multiple_choice_view
  WHERE question_id = 789;
  ```

- 展开解答题各小问：

  ```sql
  SELECT question_id,
         jsonb_array_elements(parts) ->> 'part_number' AS part_number,
         jsonb_array_elements(parts) ->> 'question_text' AS sub_question,
         jsonb_array_elements(parts) -> 'image_filename' AS images
  FROM question_problem_solving_view
  WHERE question_id = 321;
  ```

字段均保持 Markdown 文本，应用层可直接渲染；`image_filename` 保留与 Markdown 一致的文件名数组，前端可拼接 URL；`correct_answer` 字段类型由视图保证（单选为 `char(1)`、多选为 `char(1)[]`、填空为 `text`、解答题包含在 `parts jsonb` 中）。如需统计或检索，可在视图基础上再创建应用层查询或物化视图。

---

## 附录：常用 LaTeX 写法

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

更新本指南时，请同步检查脚本与 SQL 中的字段定义，避免命名不一致导致导入失败。
