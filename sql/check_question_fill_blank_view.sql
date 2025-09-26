SELECT question_id,
       difficulty,
       question_text,
       correct_answer,
       image_filename
FROM question_fill_blank_view
ORDER BY question_id
LIMIT 10;
