SELECT question_id,
       difficulty,
       question_text,
       ARRAY[option_a, option_b, option_c, option_d] AS options,
       correct_answer,
       image_filename
FROM question_multiple_choice_view
ORDER BY question_id
LIMIT 10;
