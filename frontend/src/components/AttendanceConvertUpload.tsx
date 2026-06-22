import { useRef } from "react";
import { Button, Progress, Tooltip, type ButtonProps } from "antd";
import { FileExcelOutlined } from "@ant-design/icons";

export interface AttendanceConvertUploadProps {
  year: number;
  month: number;
  loading?: boolean;
  progress?: number;
  label: string;
  hint?: string;
  onFileSelected: (file: File) => void | Promise<void>;
  buttonProps?: ButtonProps;
}

/**
 * Hidden file input + trigger button for DingTalk upload-and-convert.
 */
export default function AttendanceConvertUpload({
  loading = false,
  progress = 0,
  label,
  hint,
  onFileSelected,
  buttonProps,
}: AttendanceConvertUploadProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);

  const button = (
    <Button
      icon={<FileExcelOutlined />}
      loading={loading}
      onClick={() => inputRef.current?.click()}
      style={{
        borderColor: "#389e0d",
        color: "#389e0d",
        background: "#f6ffed",
        ...buttonProps?.style,
      }}
      {...buttonProps}
    >
      {label}
    </Button>
  );

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        hidden
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) {
            void onFileSelected(file);
          }
          event.target.value = "";
        }}
      />
      {hint ? <Tooltip title={hint}>{button}</Tooltip> : button}
      {loading && progress > 0 ? (
        <Progress percent={progress} size="small" style={{ minWidth: 120, marginTop: 8 }} />
      ) : null}
    </>
  );
}
