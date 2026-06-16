import { Card, Col, Row, Skeleton, Statistic } from "antd";
import type { MonthlyStats } from "../api";
import { useLanguage } from "../i18n/LanguageContext";

interface SummaryCardsProps {
  stats: MonthlyStats | null;
  loading: boolean;
}

export default function SummaryCards({ stats, loading }: SummaryCardsProps) {
  const { t } = useLanguage();

  if (loading) {
    return (
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {Array.from({ length: 4 }).map((_, index) => (
          <Col xs={24} sm={12} md={6} key={index}>
            <Card>
              <Skeleton active paragraph={{ rows: 1 }} />
            </Card>
          </Col>
        ))}
      </Row>
    );
  }

  return (
    <Row gutter={16} style={{ marginBottom: 16 }}>
      <Col xs={24} sm={12} md={6}>
        <Card>
          <Statistic
            title={t("totalEmployees")}
            value={stats?.total_employees ?? 0}
            suffix={t("people") || undefined}
          />
        </Card>
      </Col>
      <Col xs={24} sm={12} md={6}>
        <Card>
          <Statistic
            title={t("absenteeism")}
            value={stats?.total_absenteeism_days ?? 0}
            suffix={t("days")}
            valueStyle={{ color: "#cf1322" }}
          />
        </Card>
      </Col>
      <Col xs={24} sm={12} md={6}>
        <Card>
          <Statistic
            title={t("lateness")}
            value={stats?.total_lateness_days ?? 0}
            suffix={t("times")}
            valueStyle={{ color: "#d48806" }}
          />
        </Card>
      </Col>
      <Col xs={24} sm={12} md={6}>
        <Card>
          <Statistic
            title={t("missingPunch")}
            value={stats?.total_missing_punch_days ?? 0}
            suffix={t("times")}
            valueStyle={{ color: "#d48806" }}
          />
        </Card>
      </Col>
    </Row>
  );
}
