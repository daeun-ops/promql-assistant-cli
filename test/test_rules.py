from promql_assistant_cli.rules import nl_to_promql


def test_latency_rule_generates_valid_promql():
    """
    GIVEN????!!! 자연어로 된 latency 쿼리
    WHEN??!!!!! PromQL로 변환할 때
    THEN ????!??? histogram_quantile() 이 포함되어야험
    """

    # 준비 (arrange)
    query = "p95 latency of checkout_service last 1h"

    # 실행 (act)
    promql, explanation = nl_to_promql(query)

    # 검증 (assert)
    # promql 함수이름 확인 — 안들어가면 너가 책임져 나늠몰라... 몰루
    assert "histogram_quantile" in promql, "histogram_quantile 빠짐;;"
    # 서비스명 확인
    assert "checkout_service" in promql, "서비스누락ㄱ 아아아다ㅓ큨ㅠ"
    # 시간 범위 확인
    assert "[1h]" in promql or "1h" in promql, "시간단위 고쳐텨..."
    # 설명 문자열 검증ㅏ
    assert "p95 latency" in explanation.lower(), "설명에 p95 latency 어딧니!"

    # 디버그 출력 (CI에서 로그 보기 좋게)
    print("\n--- 생성된 PromQL ---")
    print(promql)
    print("--- 설명 ---")
    print(explanation)
