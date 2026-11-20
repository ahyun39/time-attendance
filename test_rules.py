from rules import evaluate


def by_type(result, t):
    return {f["name"]: f for f in result["flags"] if f["type"] == t}


def test_overtime_near_limit_uses_period_projection():
    r = evaluate()
    ot = by_type(r, "overtime")
    assert set(ot) == {"윤OO"}
    assert ot["윤OO"]["detail"]["projected_overtime"] == 42.0


def test_short_flag_excludes_people_whose_gap_is_only_missing_records():
    r = evaluate()
    short = by_type(r, "short")
    assert set(short) == {"한OO"}           # 정OO, 문OO는 누락 보정 후 미달이 아니다
    assert short["한OO"]["reason"] == "금일 기준 14시간 부족"


def test_mismatch_checks_cancellation_first():
    r = evaluate()
    assert set(by_type(r, "mismatch")) == {"서OO"}
    assert len(r["auto_confirmed"]) == 2      # 이OO, 최OO는 취소 기록으로 자동 확인


def test_missing_status_reflects_existing_actions():
    r = evaluate()
    missing = by_type(r, "missing")
    assert missing["정OO"]["status"] == "본인이 정정 요청"
    assert missing["문OO"]["status"] == "본인에게 자동 안내"


def test_member_numbers_match_member_screen():
    r = evaluate()
    s = r["summaries"]["E04"]
    assert s["credited"] == 112 and s["adjusted"] == 120
