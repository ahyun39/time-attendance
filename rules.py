"""선택적 근로시간제 근태 확인 규칙.

근태 기록, 휴가 신청, 휴가 취소 기록을 대조해 인사팀이 확인할 구성원을 네 가지 유형으로 찾는다.
판단은 모두 규칙으로 하고, LLM은 쓰지 않는다. 규정 해석이 필요한 질문은 이 모듈의 범위 밖이다.

실행: python rules.py  -> results.json 생성
"""
import csv
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

DATA = Path(__file__).parent / "data"

# 회사 규정에 따라 바뀌는 값. 실제 규정을 확인해 채워야 한다.
CONFIG = {
    "period_start": date(2026, 11, 2),
    "period_end": date(2026, 11, 30),
    "today": date(2026, 11, 20),
    "daily_hours": 8,               # 소정근로 1일
    "break_hours": 1,               # 5시간 이상 근무 시 휴게
    "overtime_weekly_avg": 12,      # 연장근로 한도: 정산기간 평균 주 12시간으로 가정
    "overtime_near_ratio": 0.8,     # 예상 연장근로가 한도의 80% 이상이면 알림
    "short_daily_threshold": 9,     # 남은 기간 하루 평균 9시간 넘게 필요하면 미달 예상
}
LEAVE_HOURS = {"annual": 8, "official": 8, "am_half": 4, "pm_half": 4}
LEAVE_NAMES = {"annual": "연차", "official": "공가", "am_half": "오전 반차", "pm_half": "오후 반차"}
TOLERANCE = 0.5  # 시간


def load(name):
    with open(DATA / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def workdays(start, end):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def worked_hours(clock_in, clock_out, break_hours):
    if not clock_in or not clock_out:
        return None  # 기록이 불완전하면 계산하지 않는다
    t = lambda s: datetime.strptime(s, "%H:%M")
    span = (t(clock_out) - t(clock_in)).seconds / 3600
    return span - break_hours if span >= 5 else span


def md(d):
    return f"{d.month}/{d.day}"


def hm(hours):
    h = int(hours)
    m = round((hours - h) * 60)
    return f"{h}시간" + (f" {m}분" if m else "")


@dataclass
class Flag:
    type: str
    emp_id: str
    name: str
    team: str
    reason: str
    sub: str = ""
    status: str = "안내 전"
    action: str = ""
    detail: dict = field(default_factory=dict)


def evaluate(cfg=CONFIG):
    employees = {e["emp_id"]: e for e in load("employees.csv")}
    attendance = {(a["emp_id"], a["date"]): a for a in load("attendance.csv")}
    cancelled = {c["leave_id"] for c in load("leave_cancellations.csv")}
    leaves = {}
    for l in load("leaves.csv"):
        if l["status"] == "approved":
            leaves[(l["emp_id"], l["date"])] = l
    corrections = {(c["emp_id"], c["date"]) for c in load("correction_requests.csv") if c["status"] == "pending"}
    notified = {n["emp_id"] for n in load("notifications.csv")}

    all_days = list(workdays(cfg["period_start"], cfg["period_end"]))
    elapsed = [d for d in all_days if d <= cfg["today"]]
    remaining = len(all_days) - len(elapsed)
    total_required = cfg["daily_hours"] * len(all_days)
    required_to_date = cfg["daily_hours"] * len(elapsed)
    period_weeks = ((cfg["period_end"] - cfg["period_start"]).days + 1) / 7
    overtime_limit = cfg["overtime_weekly_avg"] * period_weeks

    flags, auto_confirmed, summaries = [], [], {}

    for emp_id, emp in employees.items():
        credited, missing_days = 0.0, []
        for d in elapsed:
            iso = d.isoformat()
            rec = attendance.get((emp_id, iso))
            hours = worked_hours(rec["clock_in"], rec["clock_out"], cfg["break_hours"]) if rec else None
            leave = leaves.get((emp_id, iso))
            leave_active = leave and leave["leave_id"] not in cancelled
            leave_hours = LEAVE_HOURS[leave["type"]] if leave_active else 0

            # 1) 휴가와 기록 불일치: 휴가가 있는 날 휴가 시간 외 근무 기록이 있음
            if leave and hours is not None and hours > cfg["daily_hours"] - LEAVE_HOURS[leave["type"]] + TOLERANCE:
                label = LEAVE_NAMES[leave["type"]]
                if leave["leave_id"] in cancelled:
                    # 취소 기록을 먼저 찾고, 있으면 사람에게 넘기지 않는다
                    kind = "퇴근" if leave["type"] == "pm_half" else "출근"
                    auto_confirmed.append(f"{emp['name']} ({emp['team']}) {md(d)} {label} 취소 기록 확인, {kind} 기록과 일치")
                else:
                    flags.append(Flag("mismatch", emp_id, emp["name"], emp["team"],
                                      f"{label}({md(d)}) 승인 후 출퇴근 기록 확인",
                                      f"({label} 취소 기록이 없어서 본인 확인 필요)",
                                      action="본인 안내"))

            # 2) 기록 누락: 휴가로 하루가 다 채워지지 않는데 완전한 근무 기록이 없음
            if hours is None and leave_hours < cfg["daily_hours"]:
                missing_days.append(d)
                if rec and rec["clock_in"] and not rec["clock_out"]:
                    reason, sub = f"{md(d)} 퇴근 기록 없음", ""
                else:
                    reason, sub = "휴가 신청 없음", f"({md(d)} 출퇴근 기록 X)"
                if (emp_id, iso) in corrections:
                    status, action = "본인이 정정 요청", ""
                elif emp_id in notified:
                    status, action = "본인에게 자동 안내", ""
                else:
                    status, action = "안내 전", "본인 안내"
                flags.append(Flag("missing", emp_id, emp["name"], emp["team"], reason, sub, status, action))

            credited += max(hours or 0, leave_hours)

        # 누락된 날은 정정될 것으로 보고 보정한 뒤 미달과 연장근로를 판단한다
        adjusted = credited + cfg["daily_hours"] * len(missing_days)
        summaries[emp_id] = {"name": emp["name"], "credited": credited, "adjusted": adjusted,
                             "required_to_date": required_to_date, "missing_days": [md(d) for d in missing_days]}

        # 3) 근태 미달 예상
        if remaining and adjusted < required_to_date:
            need_per_day = (total_required - adjusted) / remaining
            if need_per_day > cfg["short_daily_threshold"]:
                flags.append(Flag("short", emp_id, emp["name"], emp["team"],
                                  f"금일 기준 {hm(required_to_date - adjusted)} 부족",
                                  f"(이후 일 평균 {hm(need_per_day)} 필요)", action="본인 안내",
                                  detail={"need_per_day": round(need_per_day, 2)}))

        # 4) 연장근로 한도 근접: 지금 추세가 이어지면 정산기간 연장근로가 한도에 가까워짐
        pace = adjusted / len(elapsed)
        projected_overtime = adjusted + pace * remaining - total_required
        if projected_overtime >= overtime_limit * cfg["overtime_near_ratio"]:
            ratio = projected_overtime / overtime_limit
            flags.append(Flag("overtime", emp_id, emp["name"], emp["team"],
                              f"정산기간 누적 {hm(adjusted)}",
                              f"(현재 추세면 연장근로 약 {round(projected_overtime)}시간, 한도 {overtime_limit:.1f}시간의 {ratio:.0%})",
                              action="리더에게 알림",
                              detail={"projected_overtime": round(projected_overtime, 1),
                                      "limit": round(overtime_limit, 1)}))

    order = {"overtime": 0, "short": 1, "mismatch": 2, "missing": 3}
    flags.sort(key=lambda f: order[f.type])
    return {
        "period": {"start": cfg["period_start"].isoformat(), "end": cfg["period_end"].isoformat(),
                   "today": cfg["today"].isoformat(), "total_required": total_required,
                   "required_to_date": required_to_date, "remaining_workdays": remaining,
                   "overtime_limit": round(overtime_limit, 1)},
        "flags": [f.__dict__ for f in flags],
        "auto_confirmed": auto_confirmed,
        "summaries": summaries,
    }


if __name__ == "__main__":
    result = evaluate()
    (Path(__file__).parent / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for f in result["flags"]:
        print(f"[{f['type']:>8}] {f['name']} {f['team']}: {f['reason']} {f['sub']} -> {f['status']}")
    print("자동 확인:", *result["auto_confirmed"], sep="\n  ")
