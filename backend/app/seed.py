from datetime import datetime

from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.models import Company, Employee, MonthlyAttendance, User

DEMO_ADMIN_EMAIL = "admin@demo.com"
DEMO_ADMIN_PASSWORD = "Admin123!"

DEMO_EMPLOYEES = [
    {
        "name": "陈鹏",
        "department": "朋创",
        "position": "工程师",
        "employee_code": "E001",
        "attendance": {
            "total_attendance_days": 21,
            "absenteeism_count": 0,
            "lateness_count": 0,
            "missing_punch_count": 0,
            "anomaly_summary": None,
            "supplement_submitted": False,
        },
    },
    {
        "name": "芮超杰",
        "department": "电机部",
        "position": "技术员",
        "employee_code": "E002",
        "attendance": {
            "total_attendance_days": 18,
            "absenteeism_count": 1,
            "lateness_count": 0,
            "missing_punch_count": 0,
            "anomaly_summary": "旷工1天",
            "supplement_submitted": True,
        },
    },
    {
        "name": "张成",
        "department": "项目推进部",
        "position": "项目经理",
        "employee_code": "E003",
        "attendance": {
            "total_attendance_days": 20,
            "absenteeism_count": 2,
            "lateness_count": 1,
            "missing_punch_count": 0,
            "anomaly_summary": "迟到、旷工2天",
            "supplement_submitted": False,
        },
    },
    {
        "name": "蔡传军",
        "department": "朋创",
        "position": "主管",
        "employee_code": "E004",
        "attendance": {
            "total_attendance_days": 22,
            "absenteeism_count": 0,
            "lateness_count": 0,
            "missing_punch_count": 1,
            "anomaly_summary": "缺卡1天",
            "supplement_submitted": False,
            "notes": "年假",
        },
    },
    {
        "name": "李明",
        "department": "电机部",
        "position": "工程师",
        "employee_code": "E005",
        "attendance": {
            "total_attendance_days": 19,
            "absenteeism_count": 0,
            "lateness_count": 2,
            "missing_punch_count": 1,
            "anomaly_summary": "迟到2次、缺卡1天",
            "supplement_submitted": True,
        },
    },
]


def seed_database(db: Session) -> None:
    company = db.query(Company).first()
    if not company:
        company = Company(name="演示公司", dingtalk_corp_id="demo_corp_001")
        db.add(company)
        db.flush()

        now = datetime.utcnow()
        for index, item in enumerate(DEMO_EMPLOYEES, start=1):
            employee = Employee(
                company_id=company.id,
                dingtalk_user_id=f"dt_user_{index:03d}",
                name=item["name"],
                department=item["department"],
                position=item["position"],
                employee_code=item["employee_code"],
                is_active=True,
            )
            db.add(employee)
            db.flush()

            attendance_data = item["attendance"]
            db.add(
                MonthlyAttendance(
                    company_id=company.id,
                    year=2026,
                    month=5,
                    employee_id=employee.id,
                    total_attendance_days=attendance_data["total_attendance_days"],
                    absenteeism_count=attendance_data["absenteeism_count"],
                    lateness_count=attendance_data["lateness_count"],
                    missing_punch_count=attendance_data["missing_punch_count"],
                    anomaly_summary=attendance_data.get("anomaly_summary"),
                    supplement_submitted=attendance_data.get("supplement_submitted", False),
                    notes=attendance_data.get("notes"),
                    last_sync_from_dingtalk=now,
                )
            )

    admin = db.query(User).filter(User.email == DEMO_ADMIN_EMAIL).first()
    if not admin:
        db.add(
            User(
                company_id=company.id,
                name="HR Admin",
                email=DEMO_ADMIN_EMAIL,
                password_hash=hash_password(DEMO_ADMIN_PASSWORD),
                role="hr_admin",
                is_active=True,
            )
        )

    db.commit()
