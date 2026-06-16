import { Modal, Typography } from "antd";
import type { ExcelUploadResponse } from "../services/api";
import { useLanguage } from "../i18n/LanguageContext";

interface UploadSummaryModalProps {
  open: boolean;
  result: ExcelUploadResponse | null;
  onClose: () => void;
  onResolveConflicts: () => void;
}

export default function UploadSummaryModal({
  open,
  result,
  onClose,
  onResolveConflicts,
}: UploadSummaryModalProps) {
  const { t } = useLanguage();

  if (!result) {
    return null;
  }

  const hasConflicts = result.conflicts_created > 0 || result.has_conflicts;

  return (
    <Modal
      open={open}
      title={t("uploadSummaryTitle")}
      onCancel={onClose}
      onOk={() => {
        onClose();
        if (hasConflicts) {
          onResolveConflicts();
        }
      }}
      okText={hasConflicts ? t("uploadSummaryResolve") : t("uploadSummaryOk")}
      cancelButtonProps={{ style: hasConflicts ? undefined : { display: "none" } }}
    >
      <Typography.Paragraph>
        {t("uploadSummaryBody", {
          changes: result.changes_detected,
          conflicts: result.conflicts_created,
        })}
      </Typography.Paragraph>
      {result.employees_affected > 0 && (
        <Typography.Text type="secondary">
          {t("uploadSummaryEmployees", { count: result.employees_affected })}
        </Typography.Text>
      )}
    </Modal>
  );
}
