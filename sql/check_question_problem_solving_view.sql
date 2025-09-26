SELECT question_id,
       difficulty,
       parts
FROM question_problem_solving_view
ORDER BY question_id
LIMIT 10;
