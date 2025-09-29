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

1. 本地数据库地址 `101.126.70.212`，用户名 `zhouenyu`，数据库名 `data`，端口 `5432`，密码保存在 `~/.pgpass`。首次部署或需重建结构时执行：

   ```bash
   psql -h 101.126.70.212 -U zhouenyu -d data -f sql/001_create_question_exam.sql
   ```

   `.pgpass` 会自动提供密码。如表结构已存在且无需调整，可跳过此步骤。
   远程环境已创建 `content` schema，本脚本会在本地确保同名 schema 存在并将所有对象写入其中。

2. 确保安装 `psycopg`，建议命令：

   ```bash
   pip install "psycopg[binary]"
   ```

### 运行导入脚本

使用脚本 `scripts/ingest_exams.py` 将 Markdown 写入数据库：

```bash
python scripts/ingest_exams.py exam/2025-新高考一卷.md --dsn "postgresql://zhouenyu@127.0.0.1:5432/data"
```

- 多个文件可一次传入：`python scripts/ingest_exams.py exam/*.md --dsn "postgresql://zhouenyu@127.0.0.1:5432/data"`
- 使用 `--dry-run` 仅校验解析并输出计划操作，不写数据库。
- 日志中若出现 `Parsed exam ...` 表示解析成功；`Ingested exam ...` 表示完成写入。脚本会按照题号自动 upsert 题目、试卷与映射关系。
- 导入脚本会在连接建立后执行 `SET search_path TO content, public`，无需额外指定 schema。

### 导入后校验

- 可执行 `SELECT COUNT(*) FROM exam_question;`、`SELECT COUNT(*) FROM exam;` 等基础查询确认写入数量。
- 依题型抽查详情时直接查询各题型子表（例如 `question_single_choice`、`question_multiple_choice` 等），也可以编写临时查询脚本放在 `sql/` 目录并通过 `psql -f` 执行。
- 若仓库提供额外 `test/show_*.sql` 校验脚本，可继续使用 `psql -f` 方式运行。

---

## 第 3 步：查询 PostgreSQL 数据

进入云端数据库：

```bash
psql -h 101.126.70.212 -U zhouenyu -d data
```

表结构由一张总表与四张题型子表组成，直接按需查询：

- `question`：保存题目公共字段（`question_type`、`difficulty`、创建/更新时间等）。
- `question_single_choice`、`question_multiple_choice`、`question_fill_blank`、`question_problem_solving_parts`：按题型存放细节。
- `exam`、`exam_question`：试卷与题目映射关系。

常用查询示例：

- 查询试卷中的单选题：

  ```sql
  SELECT eq.question_num,
         sc.question_text,
         ARRAY[sc.option_a, sc.option_b, sc.option_c, sc.option_d] AS options,
         sc.correct_answer
  FROM exam_question AS eq
  JOIN question AS q ON q.question_id = eq.question_id AND q.question_type = 'single_choice'
  JOIN question_single_choice AS sc ON sc.question_id = eq.question_id
  WHERE eq.exam_id = 123
  ORDER BY eq.question_num;
  ```

- 查询多选题答案数组：

  ```sql
  SELECT q.question_id,
         mc.question_text,
         mc.correct_answer -- char(1)[]
  FROM question AS q
  JOIN question_multiple_choice AS mc ON mc.question_id = q.question_id
  WHERE q.question_id = 789;
  ```

- 展开解答题各小问：

  ```sql
  SELECT q.question_id,
         p.part_number,
         p.question_text,
         p.image_filename,
         p.correct_answer
  FROM question AS q
  JOIN question_problem_solving_parts AS p ON p.question_id = q.question_id
  WHERE q.question_id = 321
  ORDER BY CASE WHEN p.part_number IS NULL THEN 0 ELSE 1 END,
           string_to_array(p.part_number, '-')::int[];
  ```

所有题干、选项、解析等字段均保存 Markdown 文本，`image_filename` 保持 Markdown 同步的文件名数组；

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
