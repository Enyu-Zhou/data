-- ================================================
-- Ensure question.updated_at reflects subtype changes
-- ================================================

SET search_path TO content, public;

CREATE OR REPLACE FUNCTION touch_question_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    target_question_id integer := COALESCE(NEW.question_id, OLD.question_id);
BEGIN
    IF target_question_id IS NULL THEN
        RETURN NULL;
    END IF;

    UPDATE question
    SET updated_at = CURRENT_TIMESTAMP
    WHERE question_id = target_question_id;

    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS question_single_choice_touch_question ON question_single_choice;
CREATE TRIGGER question_single_choice_touch_question
AFTER INSERT OR UPDATE OR DELETE ON question_single_choice
FOR EACH ROW
EXECUTE FUNCTION touch_question_updated_at();

DROP TRIGGER IF EXISTS question_multiple_choice_touch_question ON question_multiple_choice;
CREATE TRIGGER question_multiple_choice_touch_question
AFTER INSERT OR UPDATE OR DELETE ON question_multiple_choice
FOR EACH ROW
EXECUTE FUNCTION touch_question_updated_at();

DROP TRIGGER IF EXISTS question_fill_blank_touch_question ON question_fill_blank;
CREATE TRIGGER question_fill_blank_touch_question
AFTER INSERT OR UPDATE OR DELETE ON question_fill_blank
FOR EACH ROW
EXECUTE FUNCTION touch_question_updated_at();

DROP TRIGGER IF EXISTS question_problem_solving_parts_touch_question ON question_problem_solving_parts;
CREATE TRIGGER question_problem_solving_parts_touch_question
AFTER INSERT OR UPDATE OR DELETE ON question_problem_solving_parts
FOR EACH ROW
EXECUTE FUNCTION touch_question_updated_at();
