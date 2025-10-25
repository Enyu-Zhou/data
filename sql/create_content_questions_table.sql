CREATE TABLE IF NOT EXISTS content.questions(
    question_id bigint PRIMARY KEY,
    question_type text NOT NULL CHECK (question_type IN ('single_choice', 'multiple_choice', 'true_false', 'fill_in_blank', 'subjective')),
    accuracy real NOT NULL CHECK (accuracy > 0 AND accuracy < 1),
    question text NOT NULL,
    answer text[] NOT NULL,
    analysis text[] NOT NULL,
    explanation text[] NOT NULL,
    knowledge text[] NOT NULL,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW()
);

