import argparse
import csv
import math
from datetime import datetime
from pathlib import Path

# 本專案採用的檢查範圍，不代表完整 ATX 合規判定。
LOWER_V = 11.40
UPPER_V = 12.60

BASE = Path(__file__).resolve().parent
FIELDS = [
    "sample_id", "elapsed_s", "dut_id", "scenario",
    "connector", "voltage_v", "notes"
]
RESULT_FIELDS = FIELDS + [
    "lower_limit_v", "upper_limit_v", "result", "reason"
]


def classify(raw):
    """回傳：(結果、原因、有效數值或 None)。"""
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return "INVALID", "Missing or non-numeric voltage", None

    if not math.isfinite(value):
        return "INVALID", "Non-finite voltage", None
    if value < LOWER_V:
        return "FAIL", "Below lower limit", value
    if value > UPPER_V:
        return "FAIL", "Above upper limit", value
    return "PASS", "Within limits", value


def self_test():
    cases = [
        ("12.00", "PASS"),
        ("11.40", "PASS"),
        ("12.60", "PASS"),
        ("11.39", "FAIL"),
        ("12.61", "FAIL"),
        ("", "INVALID"),
        ("abc", "INVALID"),
        ("NaN", "INVALID"),
        ("inf", "INVALID"),
    ]
    for raw, expected in cases:
        actual = classify(raw)[0]
        if actual != expected:
            raise RuntimeError(
                f"Self-test failed: {raw!r}: {actual} != {expected}"
            )
    print(f"Software self-test: {len(cases)}/{len(cases)} PASS")
    return len(cases)


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def create_template():
    path = BASE / "measurements.csv"
    if path.exists():
        return
    rows = []
    for i in range(6):
        rows.append({
            "sample_id": i + 1,
            "elapsed_s": i * 30,
            "dut_id": "PSU001",
            "scenario": "BIOS",
            "connector": "",
            "voltage_v": "",
            "notes": "",
        })
    write_csv(path, FIELDS, rows)
    print("Created blank template: measurements.csv")


def create_demo():
    path = BASE / "demo_cases.csv"
    values = ["12.00", "11.40", "12.60", "11.39", "12.61", "", "abc", "NaN"]
    rows = []
    for i, value in enumerate(values, start=1):
        rows.append({
            "sample_id": i,
            "elapsed_s": "",
            "dut_id": "DEMO_ONLY",
            "scenario": "SOFTWARE_TEST",
            "connector": "NOT_CONNECTED",
            "voltage_v": value,
            "notes": "Synthetic data; not a PSU measurement",
        })
    # 示範模式只重建示範檔，不覆寫 measurements.csv。
    write_csv(path, FIELDS, rows)
    return path


def analyze(input_path, is_demo, test_count):
    with input_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = set(FIELDS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError("Missing CSV columns: " + ", ".join(sorted(missing)))
        rows = list(reader)

    if not rows:
        raise ValueError("CSV contains no data rows.")

    results = []
    values = []
    counts = {"PASS": 0, "FAIL": 0, "INVALID": 0}

    for line_no, row in enumerate(rows, start=2):
        if None in row:
            raise ValueError(f"Extra CSV fields at line {line_no}.")
        result, reason, value = classify(row.get("voltage_v"))
        counts[result] += 1
        if value is not None:
            values.append(value)

        output = {key: row.get(key, "") for key in FIELDS}
        output.update({
            "lower_limit_v": LOWER_V,
            "upper_limit_v": UPPER_V,
            "result": result,
            "reason": reason,
        })
        results.append(output)

    # 每次分析獨立存檔，避免覆蓋前一次結果。
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    mode = "demo" if is_demo else "input"
    out_dir = BASE / "outputs" / f"{mode}_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=False)
    write_csv(out_dir / "results.csv", RESULT_FIELDS, results)

    # 保存本次輸入副本，便於追溯。
    (out_dir / "source.csv").write_bytes(input_path.read_bytes())

    if counts["FAIL"]:
        conclusion = "有超限讀值，需檢查與複測。"
    elif counts["INVALID"]:
        conclusion = "資料不完整或無效，不可判定全部通過。"
    else:
        conclusion = "所有提供的有效讀值均位於設定範圍內。"

    data_type = "模擬資料：僅驗證軟體，不可用於 PSU 結論。" if is_demo else (
        "使用者提供資料：請確認為實測資料，並補齊測試條件。"
    )

    stats = ["- 無有效電壓資料。"]
    if values:
        stats = [
            f"- 最小值：{min(values):.3f} V",
            f"- 最大值：{max(values):.3f} V",
            f"- 平均值：{sum(values) / len(values):.3f} V",
            "- 統計顯示位數不代表儀器精度。",
        ]

    report = [
        "# ATX +12V DC 電壓檢查報告",
        "",
        f"- 產生時間：{datetime.now().isoformat(timespec='seconds')}",
        f"- 輸入檔：{input_path.name}",
        f"- 資料性質：{data_type}",
        f"- 專案限制：{LOWER_V:.2f}～{UPPER_V:.2f} V（含邊界）",
        f"- 軟體自我測試：{test_count}/{test_count} PASS",
        "",
        "## 資料摘要",
        f"- 總筆數：{len(results)}",
        f"- PASS：{counts['PASS']}",
        f"- FAIL：{counts['FAIL']}",
        f"- INVALID：{counts['INVALID']}",
        *stats,
        "",
        "## 資料判定",
        conclusion,
        "",
        "## 人員補填",
        "- 電表型號／檔位：",
        "- PSU 與主機板資訊：",
        "- 量測接頭與照片檔名：",
        "- 測試情境及等待時間：",
        "- 異常現象、複測方式與結果：",
        "",
        "## 限制",
        "- 本工具僅檢查 voltage_v，不驗證接線、儀器準確度或資料真實性。",
        "- 尚未自動檢查取樣間隔、必要筆數與情境是否符合測試計畫。",
        "- 未納入量測不確定度；接近邊界時應檢查儀器規格並複測。",
        "- 不涵蓋電流、功率、Ripple、暫態、保護功能與可靠度。",
        "- 單點或稀疏 DC 取樣不能證明整顆 PSU 正常或符合完整 ATX 規範。",
    ]
    (out_dir / "report.md").write_text("\n".join(report), encoding="utf-8")

    print(f"Data rows: {len(results)}")
    print(" | ".join(f"{key}: {value}" for key, value in counts.items()))
    print(f"Output folder: {out_dir}")
    if is_demo:
        print("DEMO ONLY: These results do not describe the physical PSU.")


def main():
    parser = argparse.ArgumentParser(description="ATX +12V DC data checker")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true", help="Run synthetic cases")
    group.add_argument("--input", type=Path, help="Analyze a measurement CSV")
    args = parser.parse_args()

    test_count = self_test()
    create_template()
    input_path = create_demo() if args.demo else args.input.resolve()
    analyze(input_path, args.demo, test_count)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, csv.Error) as exc:
        raise SystemExit(f"ERROR: {exc}")
