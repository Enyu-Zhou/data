SELECT question_id,
       difficulty,
       question_text,
       option_a,
       option_b,
       option_c,
       option_d,
       correct_answer,
       image_filename
FROM question_single_choice_view
ORDER BY question_id
LIMIT 10;
