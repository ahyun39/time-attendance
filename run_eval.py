"""평가 세트(eval/questions.csv)를 에이전트에 돌려 결과와 리포트를 저장한다.

실행: python3 run_eval.py
결과: eval/results.json (질문별 응답), eval/report.md (요약)
"""
import csv
import json
import re
import sys
import time
from pathlib import Path

from agent import ask, load_regs, norm_source

ROOT = Path(__file__).parent
EVAL = ROOT / "eval"
NUM = re.compile(r"(\d+(?:\.\d+)?)\s*(시간|분|일)")


def source_hit(expected, got):
    exp = {norm_source(x) for x in expected.split(";") if x.strip()}
    if not exp:
        return None
    gotn = {norm_source(x) for x in got}
    return bool(exp & gotn)


DATE = re.compile(r"\d{4}년|\d{1,2}월\s*\d{1,2}일|\d{1,2}/\d{1,2}|\d{1,2}:\d{2}")


def unsupported_numbers(answer, allowed_text):
    """답변의 시간, 일수 중 규정, 계산 결과, 질문 어디에도 없는 숫자. 날짜와 시각은 제외한다."""
    answer = DATE.sub("", answer)
    allowed = {(n, u) for n, u in NUM.findall(allowed_text)}
    return [f"{n}{u}" for n, u in NUM.findall(answer) if (n, u) not in allowed]


def main(llm=None):
    rows = list(csv.DictReader(open(EVAL / "questions.csv", encoding="utf-8")))
    regs = load_regs()
    results = []
    for i, q in enumerate(rows, 1):
        kwargs = {"llm": llm} if llm else {}
        r = ask(q["question"], q["asker"] or None, **kwargs)
        allowed = regs + q["question"] + json.dumps(r["facts"] or {}, ensure_ascii=False)
        exp_nums = [x.strip() for x in q["expected_numbers"].split(";") if x.strip()]
        item = {
            **q,
            "route": r["route"],
            "got_reason": r["handoff_reason"],
            "sources": r["sources"],
            "answer": r["answer"],
            "model": r["model"],
            "route_ok": r["route"] == q["expected_route"],
            "reason_ok": (r["handoff_reason"] == q["handoff_reason"]) if q["expected_route"] == "handoff" else None,
            "source_ok": source_hit(q["expected_source"], r["sources"]),
            "numbers_ok": all(n.replace(" ", "") in r["answer"].replace(" ", "") for n in exp_nums) if exp_nums else None,
            "unsupported_numbers": unsupported_numbers(r["answer"], allowed),
            "parse_error": r["parse_error"],
            "guards": r["guards"],
        }
        results.append(item)
        print(f"[{i:>2}/{len(rows)}] {q['id']} {'O' if item['route_ok'] else 'X'} {r['route']:<7} {r['handoff_reason']}", flush=True)
        if not llm:
            time.sleep(0.5)

    (EVAL / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (EVAL / "report.md").write_text(report(results), encoding="utf-8")
    print("\n" + report(results).split("## 질문별 결과")[0])


def rate(items, key):
    vals = [x[key] for x in items if x[key] is not None]
    return f"{sum(vals)}/{len(vals)}" if vals else "-"


def report(results):
    auto = [x for x in results if x["expected_route"] == "auto"]
    hand = [x for x in results if x["expected_route"] == "handoff"]
    unsupported = [x for x in results if x["unsupported_numbers"]]
    model = next((x["model"] for x in results if x["model"]), "")
    lines = [
        "# 문의 처리 평가 결과", "",
        f"모델: `{model}`, 질문 {len(results)}개", "",
        "| 항목 | 결과 |", "|---|---|",
        f"| 처리 경로 정확도 (자동 답변과 넘김 구분) | {rate(results, 'route_ok')} |",
        f"| 자동 답변 질문을 자동으로 처리 | {rate(auto, 'route_ok')} |",
        f"| 넘길 질문을 넘김 | {rate(hand, 'route_ok')} |",
        f"| 넘기는 이유 일치 | {rate(hand, 'reason_ok')} |",
        f"| 근거 조항 일치 | {rate(results, 'source_ok')} |",
        f"| 필요한 숫자 포함 | {rate(results, 'numbers_ok')} |",
        f"| 근거 없는 숫자가 나온 답변 | {len(unsupported)}개 |",
        f"| JSON 형식 오류 | {sum(x['parse_error'] for x in results)}개 |",
        f"| 규칙으로 바로잡은 응답 | {sum(1 for x in results if x['guards'])}개 |", "",
        "## 질문별 결과", "",
        "| id | 질문 | 정답 | 응답 | 근거 조항 | 답변 |", "|---|---|---|---|---|---|",
    ]
    mark = lambda v: "" if v is None else ("O" if v else "X")
    for x in results:
        got = x["route"] + (f" ({x['got_reason']})" if x["got_reason"] else "")
        cells = [
            x["id"], x["question"],
            x["expected_route"] + (f" ({x['handoff_reason']})" if x["handoff_reason"] else ""),
            f"{mark(x['route_ok'])} {got}",
            f"{mark(x['source_ok'])} {', '.join(x['sources'])}",
            x["answer"].replace("\n", " ").replace("|", "\\|")
            + (f" (근거 없는 숫자: {', '.join(x['unsupported_numbers'])})" if x["unsupported_numbers"] else "")
            + (f" (보정: {'; '.join(x['guards'])})" if x["guards"] else ""),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    if "--mock" in sys.argv:
        # API 없이 흐름만 확인: 모든 질문을 근거 없음으로 넘기는 가짜 응답
        main(llm=lambda m: ('{"route":"handoff","handoff_reason":"근거 없음","sources":[],"answer":"담당자에게 전달했어요."}', "mock"))
    else:
        main()
