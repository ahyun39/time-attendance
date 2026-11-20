"""근태 문의 에이전트 (Upstage Solar Pro).

구성원 질문을 받아 규정 문서를 근거로 직접 답할지, 인사팀에 넘길지 판단한다.
숫자는 rules.py가 계산한 값만 쓰고, LLM은 그 숫자를 설명만 한다.

실행: python3 agent.py "오후 반차 쓰면 몇 시간으로 인정돼?" [--asker E04]
"""
import argparse
import json
import os
import re
import urllib.request
from pathlib import Path

from rules import evaluate, hm

ROOT = Path(__file__).parent
REGS = ROOT / "regs"
HANDOFF_REASONS = ["승인과 결정", "재량 규정", "문서 간 충돌", "민감한 사안", "법적 분쟁 가능성", "근거 없음"]


def load_env(path=ROOT / ".env"):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def load_regs():
    """규정 문서 전체. 문서가 작아서 검색 없이 모두 넣고, 문서가 많아지면 조항 단위 검색으로 바꾼다."""
    return "\n\n".join(f"<문서 이름=\"{p.stem}\">\n{p.read_text(encoding='utf-8')}\n</문서>" for p in sorted(REGS.glob("*.md")))


def member_facts(emp_id):
    """질문한 구성원의 근태 숫자. 모두 rules.py 계산 결과다."""
    if not emp_id:
        return None
    r = evaluate()
    s = r["summaries"].get(emp_id)
    if not s:
        return None
    p = r["period"]
    remaining = p["remaining_workdays"]
    facts = {
        "이름": s["name"],
        "기준일": p["today"],
        "정산기간 기준 근로시간": f"{p['total_required']}시간",
        "기준일까지 기준 근로시간": f"{p['required_to_date']}시간",
        "기준일까지 인정된 근로시간": f"{hm(s['credited'])}",
        "남은 근무일": f"{remaining}일",
        "기록 누락일": s["missing_days"] or "없음",
    }
    gap = p["required_to_date"] - s["credited"]
    if gap > 0:
        facts["기준일 기준 부족한 시간"] = hm(gap)
    facts["남은 기간 하루 평균 필요 근무시간"] = hm((p["total_required"] - s["credited"]) / remaining)
    if s["missing_days"]:
        facts["누락일이 정정되면 인정 근로시간"] = hm(s["adjusted"])
        facts["누락일이 정정되면 남은 기간 하루 평균 필요 근무시간"] = hm((p["total_required"] - s["adjusted"]) / remaining)
    elif s["adjusted"] < p["required_to_date"]:
        facts["기준일 기준 부족한 시간"] = hm(p["required_to_date"] - s["adjusted"])
    facts["판정"] = [f"{f['reason']} {f['sub']}".strip() for f in r["flags"] if f["emp_id"] == emp_id] or "없음"
    return facts


SYSTEM = """너는 사내 근태 문의에 답하는 에이전트다. 아래 규칙을 반드시 지킨다.

1. 답의 근거는 <규정> 안의 문서뿐이다. 문서에 없는 내용은 추측하지 않는다.
2. 숫자(시간, 일수)는 <규정>이나 <계산 결과>에 있는 값만 쓴다. 직접 계산하거나 새 숫자를 만들지 않는다.
3. 다음 중 하나라도 해당하면 route를 "handoff"로 하고 이유를 하나 고른다.
   - 승인과 결정: 구성원이 승인, 반려, 정정 반영, 기한 예외를 에이전트에게 직접 요청함 ("해줄 수 있어?"). 절차를 묻는 질문은 나중에 리더 승인이 필요해도 auto로 절차를 안내한다
   - 재량 규정: 질문이 인정 여부나 가능 여부를 묻는데, 근거 조항이 "부득이한 사유", "검토해 결정", "리더와 협의"처럼 판단 기준 없이 사람에게 맡김 ("인정돼?", "괜찮아?")
   - 문서 간 충돌: 문서끼리 내용이 다르고 어느 쪽이 맞는지 문서만으로 확정할 수 없음
   - 민감한 사안: 괴롭힘, 건강, 임신과 육아, 징계, 퇴직 등
   - 법적 분쟁 가능성: 규정이 법에 맞는지 묻거나 신고, 소송을 언급
   - 근거 없음: 관련 조항을 찾지 못함
   handoff_reason은 위 6개 이름 중 하나를 글자 그대로 쓴다. 여러 개가 해당하면 민감한 사안, 법적 분쟁 가능성, 문서 간 충돌, 재량 규정, 승인과 결정, 근거 없음 순서로 앞에 있는 것을 고른다.
   문서끼리 내용이 다르면 어느 한쪽 내용을 답으로 안내하지 않는다.
   answer에서 담당자에게 넘긴다고 말한다면 route는 반드시 "handoff"다.
4. handoff여도 answer에는 구성원에게 보낼 짧은 안내를 쓴다. 찾은 조항이 있으면 알려주고, 담당자에게 넘겼다고 말한다.
5. sources에는 근거 조항을 "문서이름 제N조" 형식으로 쓴다. 문서 이름은 <문서 이름="..."> 값을 그대로 쓴다. 조항 번호가 없는 문서는 문서 이름만 쓴다.
6. 반드시 아래 JSON 하나만 출력한다.
{"route": "auto" 또는 "handoff", "handoff_reason": "이유 또는 빈 문자열", "sources": ["..."], "answer": "구성원에게 보낼 답변, 존댓말, 3문장 이내"}"""


def build_messages(question, facts):
    user = f"<규정>\n{load_regs()}\n</규정>\n\n"
    if facts:
        user += f"<계산 결과>\n{json.dumps(facts, ensure_ascii=False, indent=1)}\n</계산 결과>\n\n"
    user += f"<질문>\n{question}\n</질문>"
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def call_solar(messages):
    load_env()
    key = os.environ.get("UPSTAGE_API_KEY")
    if not key:
        raise SystemExit(".env에 UPSTAGE_API_KEY를 넣어주세요.")
    body = {"model": os.environ.get("UPSTAGE_MODEL", "solar-pro4"), "messages": messages, "temperature": 0}
    req = urllib.request.Request(
        os.environ.get("UPSTAGE_BASE_URL", "https://api.upstage.ai/v1").rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as res:
        data = json.load(res)
    return data["choices"][0]["message"]["content"], data.get("model")


REASON_KEYWORDS = [("민감", "민감한 사안"), ("법", "법적 분쟁 가능성"), ("충돌", "문서 간 충돌"),
                   ("재량", "재량 규정"), ("승인", "승인과 결정"), ("결정", "승인과 결정")]
HANDOFF_WORDS = re.compile(r"담당자에게|인사팀에 (확인|전달|문의)|넘겨 ?드리|넘기겠|넘겼")


def parse(text):
    """LLM 응답을 읽고, 형식과 앞뒤가 맞지 않는 부분을 규칙으로 바로잡는다. 바로잡은 내용은 guards에 남긴다."""
    m = re.search(r"\{.*\}", text, re.S)
    try:
        out = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        out = {}
    guards = []
    route = out.get("route")
    if route not in ("auto", "handoff"):
        route = "handoff"
        guards.append("응답 형식 오류로 담당자에게 넘김")
    answer = out.get("answer") or ""
    if route == "auto" and HANDOFF_WORDS.search(answer):
        route = "handoff"
        guards.append("답변은 넘긴다고 말하는데 경로가 auto여서 handoff로 바꿈")
    reason = (out.get("handoff_reason") or "").strip() if route == "handoff" else ""
    if route == "handoff" and reason not in HANDOFF_REASONS:
        fixed = next((v for k, v in REASON_KEYWORDS if k in reason), "근거 없음")
        guards.append(f"넘기는 이유 '{reason or '없음'}'를 '{fixed}'로 맞춤")
        reason = fixed
    return {
        "route": route,
        "handoff_reason": reason,
        "sources": out.get("sources") or [],
        "answer": answer,
        "parse_error": not out,
        "guards": guards,
    }


def norm_source(s):
    """'01_근무시간_규정 제2조', '근무시간 규정 제2조 3항' 모두 '근무시간규정#2'로 맞춘다."""
    s = re.sub(r"^\d+_", "", s.strip())
    m = re.search(r"제\s*(\d+)\s*조", s)
    doc = re.sub(r"제\s*\d+\s*조.*$", "", s)
    doc = re.sub(r"[\s_\[\]]|공지", "", doc)
    return doc + ("#" + m.group(1) if m else "")


def known_conflict(question, sources):
    """인사팀이 등록한 문서 간 충돌(regs/conflicts.json) 중, 질문이 그 주제를 묻고 답변이 그 조항을 근거로 쓴 것을 찾는다."""
    path = REGS / "conflicts.json"
    if not path.exists():
        return None
    cited = {norm_source(x) for x in sources}
    for c in json.loads(path.read_text(encoding="utf-8")):
        if cited & {norm_source(x) for x in c["sources"]} and any(k in question for k in c["keywords"]):
            return c
    return None


# 민감한 주제는 LLM에 보내지 않고 바로 담당자에게 넘긴다. 목록은 인사팀이 관리한다.
SENSITIVE = re.compile(r"괴롭힘|성희롱|임신|출산|육아휴직|질병|진단서|징계|해고|퇴직|퇴사")
LOWER_THAN_CONFLICT = {"재량 규정", "승인과 결정", "근거 없음"}


def ask(question, asker=None, llm=call_solar):
    facts = member_facts(asker)
    if SENSITIVE.search(question):
        return {
            "route": "handoff", "handoff_reason": "민감한 사안", "sources": [],
            "answer": "말씀해 주신 내용은 인사팀 담당자가 직접 확인하는 것이 좋아서 담당자에게 전달했어요. 담당자가 따로 연락드릴게요.",
            "parse_error": False, "guards": ["민감한 주제라 LLM에 보내지 않고 담당자에게 넘김"],
            "model": None, "facts": facts, "raw": "",
        }
    raw, model = llm(build_messages(question, facts))
    result = parse(raw)
    conflict = known_conflict(question, result["sources"])
    if conflict and (result["route"] == "auto" or result["handoff_reason"] in LOWER_THAN_CONFLICT):
        result["guards"].append(f"등록된 문서 간 충돌 조항을 근거로 써서 담당자에게 넘김 ({conflict['note']})")
        result["route"], result["handoff_reason"] = "handoff", "문서 간 충돌"
        result["answer"] = "관련 규정과 공지의 내용이 서로 달라 지금 바로 안내드리기 어려워요. 인사팀 담당자에게 확인을 요청했고, 답변이 오면 알려드릴게요."
    result.update({"model": model, "facts": facts, "raw": raw})
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--asker", help="질문한 구성원 사번 (예: E04)")
    a = ap.parse_args()
    r = ask(a.question, a.asker)
    print(json.dumps({k: r[k] for k in ("route", "handoff_reason", "sources", "answer")}, ensure_ascii=False, indent=2))
