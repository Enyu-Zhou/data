-- ================================================
-- Exam & Question Schema (refactored)
-- Functionality: split question details into subtype tables and
--                manage exam-question relationships via joins
-- ================================================

-- ================================================
-- Enumerated types
-- ================================================

CREATE TYPE question_type_enum AS ENUM(
    'single_choice',
    'multiple_choice',
    'fill_blank',
    'problem_solving'
);

CREATE TYPE province_enum AS ENUM(
    '北京', '天津', '上海', '重庆', '河北', '山西', '辽宁', '吉林', '黑龙江',
    '江苏', '浙江', '安徽', '福建', '江西', '山东', '河南', '湖北', '湖南',
    '广东', '海南', '四川', '贵州', '云南', '陕西', '甘肃', '青海', '西藏',
    '内蒙古', '广西', '宁夏', '新疆', '香港', '澳门', '台湾'
);

-- ================================================
-- Core question tables
-- ================================================

CREATE TABLE question(
    question_id serial PRIMARY KEY,
    question_type question_type_enum NOT NULL,
    difficulty integer CHECK (difficulty BETWEEN 1 AND 5),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_question_id_type UNIQUE (question_id, question_type)
);

CREATE TABLE question_single_choice(
    question_id integer PRIMARY KEY,
    question_type question_type_enum GENERATED ALWAYS AS ('single_choice'::question_type_enum) STORED,
    question_text text NOT NULL,
    option_a text NOT NULL,
    option_b text NOT NULL,
    option_c text NOT NULL,
    option_d text NOT NULL,
    image_filename varchar(100)[],
    correct_answer char(1),
    explanation text,
    CONSTRAINT question_single_choice_question_fk FOREIGN KEY (question_id, question_type)
        REFERENCES question(question_id, question_type) ON DELETE CASCADE
);

CREATE TABLE question_multiple_choice(
    question_id integer PRIMARY KEY,
    question_type question_type_enum GENERATED ALWAYS AS ('multiple_choice'::question_type_enum) STORED,
    question_text text NOT NULL,
    option_a text NOT NULL,
    option_b text NOT NULL,
    option_c text NOT NULL,
    option_d text NOT NULL,
    image_filename varchar(100)[],
    correct_answer char(1)[],
    explanation text,
    CONSTRAINT question_multiple_choice_question_fk FOREIGN KEY (question_id, question_type)
        REFERENCES question(question_id, question_type) ON DELETE CASCADE
);

CREATE TABLE question_fill_blank(
    question_id integer PRIMARY KEY,
    question_type question_type_enum GENERATED ALWAYS AS ('fill_blank'::question_type_enum) STORED,
    question_text text NOT NULL,
    image_filename varchar(100)[],
    correct_answer text,
    explanation text,
    CONSTRAINT question_fill_blank_question_fk FOREIGN KEY (question_id, question_type)
        REFERENCES question(question_id, question_type) ON DELETE CASCADE
);

CREATE TABLE question_problem_solving_parts(
    part_id serial PRIMARY KEY,
    question_id integer NOT NULL,
    question_type question_type_enum GENERATED ALWAYS AS ('problem_solving'::question_type_enum) STORED,
    part_number varchar(50),
    question_text text,
    image_filename varchar(100)[],
    correct_answer text,
    explanation text,
    CONSTRAINT question_problem_solving_parts_part_number_format
        CHECK (part_number IS NULL OR part_number ~ '^[1-9][0-9]*(?:-[1-9][0-9]*)*$'),
    CONSTRAINT question_problem_solving_parts_question_fk FOREIGN KEY (question_id, question_type)
        REFERENCES question(question_id, question_type) ON DELETE CASCADE
);

-- ================================================
-- Exam tables
-- ================================================

CREATE TABLE exam(
    exam_id serial PRIMARY KEY,
    exam_year integer NOT NULL CHECK (exam_year > 0),
    exam_name varchar(100) NOT NULL,
    province province_enum[] NOT NULL,
    description text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (exam_year, exam_name)
);

CREATE TABLE exam_question(
    exam_question_id serial PRIMARY KEY,
    exam_id integer NOT NULL REFERENCES exam(exam_id) ON DELETE CASCADE,
    question_num integer NOT NULL CHECK (question_num > 0),
    question_id integer NOT NULL REFERENCES question(question_id) ON DELETE CASCADE,
    UNIQUE (exam_id, question_num),
    UNIQUE (exam_id, question_id)
);

-- ================================================
-- Utility & integrity functions
-- ================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION enforce_question_subtype()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.question_type = 'single_choice' THEN
        IF NOT EXISTS (SELECT 1 FROM question_single_choice WHERE question_id = NEW.question_id) THEN
            RAISE EXCEPTION 'single_choice question % requires a row in question_single_choice', NEW.question_id;
        END IF;
    ELSIF NEW.question_type = 'multiple_choice' THEN
        IF NOT EXISTS (SELECT 1 FROM question_multiple_choice WHERE question_id = NEW.question_id) THEN
            RAISE EXCEPTION 'multiple_choice question % requires a row in question_multiple_choice', NEW.question_id;
        END IF;
    ELSIF NEW.question_type = 'fill_blank' THEN
        IF NOT EXISTS (SELECT 1 FROM question_fill_blank WHERE question_id = NEW.question_id) THEN
            RAISE EXCEPTION 'fill_blank question % requires a row in question_fill_blank', NEW.question_id;
        END IF;
    ELSIF NEW.question_type = 'problem_solving' THEN
        IF NOT EXISTS (SELECT 1 FROM question_problem_solving_parts WHERE question_id = NEW.question_id) THEN
            RAISE EXCEPTION 'problem_solving question % requires entries in question_problem_solving_parts', NEW.question_id;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM question_problem_solving_parts WHERE question_id = NEW.question_id AND part_number IS NULL) THEN
            RAISE EXCEPTION 'problem_solving question % requires a main part with NULL part_number', NEW.question_id;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

-- ================================================
-- Stored procedures for question creation
-- ================================================

CREATE OR REPLACE FUNCTION create_single_choice_question(
    p_question_text text,
    p_option_a text,
    p_option_b text,
    p_option_c text,
    p_option_d text,
    p_difficulty integer DEFAULT NULL,
    p_image_filename varchar(100)[] DEFAULT NULL,
    p_correct_answer char(1) DEFAULT NULL,
    p_explanation text DEFAULT NULL
)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    new_question_id integer;
BEGIN
    INSERT INTO question(question_type, difficulty)
    VALUES ('single_choice', p_difficulty)
    RETURNING question_id INTO new_question_id;

    INSERT INTO question_single_choice(
        question_id,
        question_text,
        option_a,
        option_b,
        option_c,
        option_d,
        image_filename,
        correct_answer,
        explanation)
    VALUES (
        new_question_id,
        p_question_text,
        p_option_a,
        p_option_b,
        p_option_c,
        p_option_d,
        p_image_filename,
        p_correct_answer,
        p_explanation);

    RETURN new_question_id;
END;
$$;

CREATE OR REPLACE FUNCTION create_multiple_choice_question(
    p_question_text text,
    p_option_a text,
    p_option_b text,
    p_option_c text,
    p_option_d text,
    p_difficulty integer DEFAULT NULL,
    p_image_filename varchar(100)[] DEFAULT NULL,
    p_correct_answer char(1)[] DEFAULT NULL,
    p_explanation text DEFAULT NULL
)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    new_question_id integer;
BEGIN
    INSERT INTO question(question_type, difficulty)
    VALUES ('multiple_choice', p_difficulty)
    RETURNING question_id INTO new_question_id;

    INSERT INTO question_multiple_choice(
        question_id,
        question_text,
        option_a,
        option_b,
        option_c,
        option_d,
        image_filename,
        correct_answer,
        explanation)
    VALUES (
        new_question_id,
        p_question_text,
        p_option_a,
        p_option_b,
        p_option_c,
        p_option_d,
        p_image_filename,
        p_correct_answer,
        p_explanation);

    RETURN new_question_id;
END;
$$;

CREATE OR REPLACE FUNCTION create_fill_blank_question(
    p_question_text text,
    p_difficulty integer DEFAULT NULL,
    p_image_filename varchar(100)[] DEFAULT NULL,
    p_correct_answer text DEFAULT NULL,
    p_explanation text DEFAULT NULL
)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    new_question_id integer;
BEGIN
    INSERT INTO question(question_type, difficulty)
    VALUES ('fill_blank', p_difficulty)
    RETURNING question_id INTO new_question_id;

    INSERT INTO question_fill_blank(
        question_id,
        question_text,
        image_filename,
        correct_answer,
        explanation)
    VALUES (
        new_question_id,
        p_question_text,
        p_image_filename,
        p_correct_answer,
        p_explanation);

    RETURN new_question_id;
END;
$$;

CREATE OR REPLACE FUNCTION create_problem_solving_question(
    p_question_text text DEFAULT NULL,
    p_difficulty integer DEFAULT NULL,
    p_image_filename varchar(100)[] DEFAULT NULL,
    p_correct_answer text DEFAULT NULL,
    p_explanation text DEFAULT NULL
)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    new_question_id integer;
BEGIN
    INSERT INTO question(question_type, difficulty)
    VALUES ('problem_solving', p_difficulty)
    RETURNING question_id INTO new_question_id;

    INSERT INTO question_problem_solving_parts(
        question_id,
        part_number,
        question_text,
        image_filename,
        correct_answer,
        explanation)
    VALUES (
        new_question_id,
        NULL,
        p_question_text,
        p_image_filename,
        p_correct_answer,
        p_explanation);

    RETURN new_question_id;
END;
$$;

CREATE OR REPLACE FUNCTION add_problem_solving_part(
    p_question_id integer,
    p_part_number varchar(50),
    p_question_text text,
    p_image_filename varchar(100)[] DEFAULT NULL,
    p_correct_answer text DEFAULT NULL,
    p_explanation text DEFAULT NULL
)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    new_part_id integer;
BEGIN
    INSERT INTO question_problem_solving_parts(
        question_id,
        part_number,
        question_text,
        image_filename,
        correct_answer,
        explanation)
    VALUES (
        p_question_id,
        p_part_number,
        p_question_text,
        p_image_filename,
        p_correct_answer,
        p_explanation)
    RETURNING part_id INTO new_part_id;

    RETURN new_part_id;
END;
$$;

-- ================================================
-- Views for read access
-- ================================================

CREATE OR REPLACE VIEW question_single_choice_view AS
SELECT
    q.question_id,
    q.question_type,
    q.difficulty,
    q.created_at,
    q.updated_at,
    s.question_text,
    s.option_a,
    s.option_b,
    s.option_c,
    s.option_d,
    s.image_filename,
    s.correct_answer,
    s.explanation
FROM
    question q
    INNER JOIN question_single_choice s USING (question_id);

CREATE OR REPLACE VIEW question_multiple_choice_view AS
SELECT
    q.question_id,
    q.question_type,
    q.difficulty,
    q.created_at,
    q.updated_at,
    m.question_text,
    m.option_a,
    m.option_b,
    m.option_c,
    m.option_d,
    m.image_filename,
    m.correct_answer,
    m.explanation
FROM
    question q
    INNER JOIN question_multiple_choice m USING (question_id);

CREATE OR REPLACE VIEW question_fill_blank_view AS
SELECT
    q.question_id,
    q.question_type,
    q.difficulty,
    q.created_at,
    q.updated_at,
    f.question_text,
    f.image_filename,
    f.correct_answer,
    f.explanation
FROM
    question q
    INNER JOIN question_fill_blank f USING (question_id);

CREATE OR REPLACE VIEW question_problem_solving_view AS
SELECT
    q.question_id,
    q.question_type,
    q.difficulty,
    q.created_at,
    q.updated_at,
    jsonb_agg(
        jsonb_build_object(
            'part_id', p.part_id,
            'part_number', p.part_number,
            'question_text', p.question_text,
            'image_filename', p.image_filename,
            'correct_answer', p.correct_answer,
            'explanation', p.explanation
        )
        ORDER BY
            CASE WHEN p.part_number IS NULL THEN 0 ELSE 1 END,
            CASE
                WHEN p.part_number IS NULL THEN NULL
                ELSE string_to_array(p.part_number, '-')::int[]
            END
    ) AS parts
FROM
    question q
    INNER JOIN question_problem_solving_parts p ON p.question_id = q.question_id
WHERE
    q.question_type = 'problem_solving'
GROUP BY
    q.question_id,
    q.question_type,
    q.difficulty,
    q.created_at,
    q.updated_at;

-- ================================================
-- Triggers
-- ================================================

CREATE CONSTRAINT TRIGGER question_enforce_subtype
AFTER INSERT OR UPDATE ON question
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION enforce_question_subtype();

CREATE TRIGGER question_set_updated_at
BEFORE UPDATE ON question
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER exam_set_updated_at
BEFORE UPDATE ON exam
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- ================================================
-- Indexes
-- ================================================

CREATE INDEX idx_questions_question_type ON question(question_type);
CREATE INDEX idx_questions_difficulty ON question(difficulty);
CREATE INDEX idx_questions_created_at ON question(created_at);

CREATE INDEX idx_exam_question_exam_id ON exam_question(exam_id);
CREATE INDEX idx_exam_question_question_id ON exam_question(question_id);
CREATE INDEX idx_exam_question_question_num ON exam_question(exam_id, question_num);

CREATE INDEX idx_exam_exam_year ON exam(exam_year);
CREATE INDEX idx_exam_province ON exam USING gin(province);

CREATE UNIQUE INDEX uq_problem_solving_main_part
    ON question_problem_solving_parts(question_id)
    WHERE part_number IS NULL;

CREATE UNIQUE INDEX uq_problem_solving_part_number
    ON question_problem_solving_parts(question_id, part_number)
    WHERE part_number IS NOT NULL;
