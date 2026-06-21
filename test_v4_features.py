"""v4版功能验证脚本 - 测试所有新增功能"""

import os
import sys
import tempfile
import shutil
import csv
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from penalty_tool.database import PenaltyDatabase
from penalty_tool.importer import DocumentImporter
from penalty_tool.searcher import CaseSearcher
from penalty_tool.exporter import CaseExporter


def run_test(name, func):
    print(f"\n{'='*60}")
    print(f"  测试: {name}")
    print(f"{'='*60}")
    try:
        func()
        print(f"  ✓ 测试通过")
        return True
    except Exception as e:
        print(f"  ✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def _insert_test_data(db):
    """插入 4 条测试数据（含各种维度组合）"""
    cases = [
        {
            "case_no": "CASE-2024-001", "company": "电商公司A",
            "regulator": "市场监督管理局", "business_line": "电商业务",
            "tags": ["广告", "绝对化用语"], "penalty_date": "2024-03-15",
            "penalty_amount": 200000.0,
            "facts": "使用了绝对化用语'最佳''顶级'等词汇进行广告宣传，违反广告法第九条。",
            "result_summary": "责令停止发布，罚款20万元。",
            "defense_content": "1. 违法行为轻微。\n2. 已主动整改。\n3. 没有造成危害后果。",
            "rectification_report": "1. 建立广告审核制度。\n2. 完善文案审核流程。",
            "reference_script": "", "source_files": [],
        },
        {
            "case_no": "CASE-2024-002", "company": "电商公司A",
            "regulator": "市场监督管理局", "business_line": "电商业务",
            "tags": ["广告", "虚假宣传"], "penalty_date": "2024-05-20",
            "penalty_amount": 300000.0,
            "facts": "在电商平台宣传产品时使用虚假数据，欺骗消费者，违反广告法第二十八条。",
            "result_summary": "责令改正，罚款30万元。",
            "defense_content": "", "rectification_report": "",
            "reference_script": "", "source_files": [],
        },
        {
            "case_no": "CASE-2024-003", "company": "科技公司B",
            "regulator": "国家互联网信息办公室", "business_line": "APP业务",
            "tags": ["个人信息", "告知同意"], "penalty_date": "2024-06-01",
            "penalty_amount": 500000.0,
            "facts": "未按照规定充分告知用户个人信息处理方式，未获得有效同意，违反个人信息保护法。",
            "result_summary": "责令改正，罚款50万元。",
            "defense_content": "", "rectification_report": "1. 完善隐私政策。",
            "reference_script": "", "source_files": [],
        },
        {
            "case_no": "CASE-2023-004", "company": "零售公司C",
            "regulator": "人力资源和社会保障局", "business_line": "线下门店",
            "tags": [], "penalty_date": "",
            "penalty_amount": 0,
            "facts": "",
            "result_summary": "责令改正。",
            "defense_content": "", "rectification_report": "",
            "reference_script": "", "source_files": [],
        },
    ]
    for case in cases:
        success, case_no, msg = db.insert_case(case)
        assert success, f"插入失败: {msg}"


def test_short_params():
    """测试短参数别名统一（通过 CLI 模块验证参数映射即可）"""
    db_path = tempfile.mktemp(suffix=".db")
    db = PenaltyDatabase(db_path)
    _insert_test_data(db)

    searcher = CaseSearcher(db)

    r1 = searcher.search(min_amount=100000, max_amount=300000)
    print(f"  金额区间(10万-30万): {len(r1)} 条")
    assert len(r1) == 2

    r2 = searcher.search(from_date="2024-01-01", to_date="2024-12-31")
    print(f"  日期区间(2024全年): {len(r2)} 条")
    assert len(r2) == 3

    try:
        os.unlink(db_path)
    except:
        pass


def test_saved_search_preset_full():
    """测试保存的预设完整加载（含金额/日期/排序）"""
    db_path = tempfile.mktemp(suffix=".db")
    db = PenaltyDatabase(db_path)
    _insert_test_data(db)

    ok, msg = db.save_search(
        name="市监局广告案",
        regulator="市场监督管理局",
        tags=["广告"],
        min_amount=100000,
        max_amount=500000,
        from_date="2024-01-01",
        to_date="2024-12-31",
        sort_by="penalty_amount",
        sort_order="desc",
    )
    assert ok

    preset = db.load_search("市监局广告案")
    print(f"  加载预设: {preset['name']}")
    assert preset["regulator"] == "市场监督管理局"
    assert preset["min_amount"] == 100000
    assert preset["max_amount"] == 500000
    assert preset["from_date"] == "2024-01-01"
    assert preset["to_date"] == "2024-12-31"
    assert preset["sort_by"] == "penalty_amount"
    assert preset["sort_order"] == "desc"
    print(f"  sort_by={preset['sort_by']}, sort_order={preset['sort_order']}")
    print(f"  金额/日期条件均正确加载")

    try:
        os.unlink(db_path)
    except:
        pass


def test_importer_regulator_extraction():
    """测试从文档内容自动识别监管部门"""
    importer = DocumentImporter()

    test_cases = [
        ("市监局处罚决定：\n当事人违反广告法。", "市场监督管理局"),
        ("国家互联网信息办公室行政处罚决定书\n当事人违反个人信息保护法。", "国家互联网信息办公室"),
        ("人社局处罚\n当事人未及时签订劳动合同。", "人力资源和社会保障局"),
        ("某某无关内容的处罚决定书\n没有提到任何具体部门。", None),
    ]

    for content, expected in test_cases:
        result = importer._extract_regulator_from_content(content)
        print(f"  输入: {content[:30]}... -> {result} (预期: {expected})")
        assert result == expected, f"期望 {expected} 实际 {result}"

    print("  所有监管部门自动识别均正确")


def test_similar_cases():
    """测试相似案例查找"""
    db_path = tempfile.mktemp(suffix=".db")
    db = PenaltyDatabase(db_path)
    _insert_test_data(db)

    # 获取 CASE-2024-001（市监局广告绝对化用语）的 ID
    case1 = db.get_case_by_no("CASE-2024-001")
    assert case1 is not None

    similar = db.find_similar_cases(case1["id"], limit=10)
    print(f"  CASE-2024-001 找到 {len(similar)} 个相似案例")
    for s in similar:
        print(f"    - [{s['case_no']}] {s['company']} 分数={s['score']} 原因={s['reasons']}")

    assert len(similar) >= 1
    # CASE-2024-002 应该最相似（同市监局+同广告标签）
    top = similar[0]
    assert top["case_no"] == "CASE-2024-002", f"期望最相似的是 CASE-2024-002，实际是 {top['case_no']}"
    assert any("标签" in r for r in top["reasons"]) or any("部门" in r for r in top["reasons"])

    try:
        os.unlink(db_path)
    except:
        pass


def test_health_check_csv_export_and_import():
    """测试健康检查 CSV 导出 + 批量回填更新"""
    db_path = tempfile.mktemp(suffix=".db")
    db = PenaltyDatabase(db_path)
    _insert_test_data(db)

    issues = db.health_check()
    print(f"  缺失日期: {issues['summary']['missing_date_count']}")
    print(f"  缺失金额: {issues['summary']['missing_amount_count']}")
    print(f"  缺失事实: {issues['summary']['missing_facts_count']}")

    exporter = CaseExporter(db=db)
    output_dir = tempfile.mkdtemp()

    try:
        csv_path = os.path.join(output_dir, "check.csv")
        actual_path = exporter.export_health_check_csv(issues, csv_path)
        print(f"  CSV导出: {actual_path}")

        with open(actual_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        print(f"  CSV 行数: {len(rows)}")
        assert len(rows) >= 1
        # 检查表头
        expected_fields = {"case_no", "company", "regulator", "missing_fields",
                           "penalty_date_new", "penalty_amount_new",
                           "facts_new", "tags_new"}
        assert expected_fields.issubset(set(reader.fieldnames))

        # CASE-2023-004 应该出现在缺失列表中，模拟回填
        filled_rows = []
        for row in rows:
            if row["case_no"] == "CASE-2023-004":
                row["penalty_date_new"] = "2023-11-10"
                row["penalty_amount_new"] = "8万"
                row["facts_new"] = "未及时与员工签订劳动合同，违反劳动合同法。"
                row["tags_new"] = "劳动用工,劳动合同"
            filled_rows.append(row)

        filled_csv = os.path.join(output_dir, "check_filled.csv")
        with open(filled_csv, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=reader.fieldnames)
            writer.writeheader()
            writer.writerows(filled_rows)

        # 批量导入回填
        updated, errors = db.batch_update_from_csv(filled_csv)
        print(f"  批量更新: {updated} 条, 错误: {errors}")
        assert updated == 1
        assert len(errors) == 0

        # 验证字段已更新
        updated_case = db.get_case_by_no("CASE-2023-004")
        assert updated_case["penalty_date"] == "2023-11-10"
        assert updated_case["penalty_amount"] == 80000.0
        assert "劳动合同" in updated_case["facts"]
        assert isinstance(updated_case["tags"], list)
        assert "劳动用工" in updated_case["tags"]
        print(f"  回填验证通过: 日期={updated_case['penalty_date']}, 金额={updated_case['penalty_amount']}")

    finally:
        try:
            os.unlink(db_path)
        except:
            pass
        shutil.rmtree(output_dir)


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  监管处罚检索工具 v4 - 功能验证")
    print("=" * 60)

    tests = [
        ("短参数金额/日期筛选", test_short_params),
        ("检索预设完整加载(金额/日期/排序)", test_saved_search_preset_full),
        ("导入分组自动识别监管部门", test_importer_regulator_extraction),
        ("相似案例查找", test_similar_cases),
        ("健康检查CSV导出+批量回填", test_health_check_csv_export_and_import),
    ]

    passed = 0
    failed = 0
    for name, func in tests:
        if run_test(name, func):
            passed += 1
        else:
            failed += 1

    print("\n" + "=" * 60)
    print(f"  测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
    sys.exit(0 if failed == 0 else 1)
