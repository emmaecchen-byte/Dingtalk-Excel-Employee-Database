BEGIN;

ALTER TABLE version_history
    DROP CONSTRAINT IF EXISTS version_history_created_by_check;

ALTER TABLE version_history
    ADD CONSTRAINT version_history_created_by_check CHECK (
        created_by IN (
            'dingtalk_sync',
            'hr_upload',
            'manual_edit',
            'conflict_resolution',
            'rollback'
        )
    );

COMMIT;
