"""가상의 11월 근태 데이터를 data/ 폴더에 CSV로 만든다.

실제 구성원 데이터가 아니라, 대시보드의 네 가지 유형이 모두 나오도록 설계한 예시 데이터다.
"""
import csv
from datetime import date, timedelta
from pathlib import Path

DATA = Path(__file__).parent / "data"
START, TODAY = date(2026, 11, 2), date(2026, 11, 20)


def workdays(start, end):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


EMPLOYEES = [
    ("E01", "윤OO", "라이브QA팀"),
    ("E02", "한OO", "데이터분석팀"),
    ("E03", "서OO", "모바일QA팀"),
    ("E04", "정OO", "모바일QA팀"),
    ("E05", "문OO", "데이터분석팀"),
    ("E06", "이OO", "PC QA팀"),
    ("E07", "최OO", "라이브QA팀"),
    ("E08", "김OO", "모바일QA팀"),
    ("E09", "박OO", "PC QA팀"),
]


def main():
    DATA.mkdir(exist_ok=True)
    days = list(workdays(START, TODAY))
    attendance = []
    for emp_id, _, _ in EMPLOYEES:
        for i, d in enumerate(days):
            iso = d.isoformat()
            if emp_id == "E01":  # 매일 10시간 근무 -> 연장근로 한도 근접
                attendance.append((emp_id, iso, "09:00", "20:00"))
            elif emp_id == "E02":  # 하루 빼고 7시간 근무 -> 미달 예상
                attendance.append((emp_id, iso, "09:00", "18:00" if i == 0 else "17:00"))
            elif emp_id == "E04" and iso == "2026-11-13":  # 출퇴근 기록 없음
                continue
            elif emp_id == "E05" and iso == "2026-11-19":  # 퇴근 기록 없음
                attendance.append((emp_id, iso, "09:00", ""))
            else:
                attendance.append((emp_id, iso, "09:00", "18:00"))

    leaves = [
        ("L1", "E03", "2026-11-18", "annual", "approved"),   # 연차 승인 + 출근 기록, 취소 기록 없음
        ("L2", "E06", "2026-11-17", "annual", "approved"),   # 연차 취소 기록 있음
        ("L3", "E07", "2026-11-19", "pm_half", "approved"),  # 오후 반차 취소 기록 있음
    ]
    cancellations = [("L2", "2026-11-17T08:40"), ("L3", "2026-11-19T12:10")]
    corrections = [("E04", "2026-11-13", "pending")]
    notifications = [("E05", "2026-11-20", "missing_record")]

    def write(name, header, rows):
        with open(DATA / name, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)

    write("employees.csv", ["emp_id", "name", "team"], EMPLOYEES)
    write("attendance.csv", ["emp_id", "date", "clock_in", "clock_out"], attendance)
    write("leaves.csv", ["leave_id", "emp_id", "date", "type", "status"], leaves)
    write("leave_cancellations.csv", ["leave_id", "cancelled_at"], cancellations)
    write("correction_requests.csv", ["emp_id", "date", "status"], corrections)
    write("notifications.csv", ["emp_id", "date", "kind"], notifications)


if __name__ == "__main__":
    main()
