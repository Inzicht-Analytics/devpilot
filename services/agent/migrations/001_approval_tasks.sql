CREATE TABLE IF NOT EXISTS approval_tasks (
    task_id TEXT PRIMARY KEY NOT NULL,
    repository TEXT NOT NULL,
    title TEXT NOT NULL,
    digest TEXT NOT NULL CHECK(length(digest) = 64),
    decision TEXT CHECK(decision IN ('approve', 'reject')),
    reviewer TEXT,
    reason TEXT,
    decided_at TEXT,
    resulting_status TEXT,
    CHECK (
        (decision IS NULL AND reviewer IS NULL AND reason IS NULL AND decided_at IS NULL AND resulting_status IS NULL)
        OR
        (decision IS NOT NULL AND reviewer IS NOT NULL AND reason IS NOT NULL AND decided_at IS NOT NULL
         AND resulting_status IS NOT NULL AND
         ((decision = 'approve' AND resulting_status = 'awaiting_approval')
          OR (decision = 'reject' AND resulting_status = 'cancelled')))
    )
);
