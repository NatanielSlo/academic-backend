CREATE TABLE study_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lecture_id UUID NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(lecture_id)
);

CREATE TABLE study_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id UUID NOT NULL REFERENCES study_plans(id) ON DELETE CASCADE,
    order_index INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    done BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE(plan_id, order_index)
);

CREATE INDEX idx_study_plans_lecture_id ON study_plans(lecture_id);
CREATE INDEX idx_study_tasks_plan_id ON study_tasks(plan_id);
