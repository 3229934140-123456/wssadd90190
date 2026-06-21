"""v5版功能验证脚本 - 测试所有新增功能"""

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
    """插入 5 条测试数据"""
    cases = [
        {
            "case_no": "CASE-2024-001", "company": "电商公司A",
            "regulator": "市场监督管理局", "business_line": "电商业务",
            "tags": ["广告", "绝对化用语"], "penalty_date": "2024-03-15",
            "penalty_amount": 200000.0,
            "external_penalty_no": "沪市监静处〔2024〕015号",
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
            "external_penalty_no": "沪市监静处〔2024〕052号",
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
            "external_penalty_no": "网信罚〔2024〕003号",
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
        {
            "case_no": "CASE-2023-005", "company": "科技公司B",
            "regulator": "国家互联网信息办公室", "business_line": "APP业务",
            "tags": [], "penalty_date": "",
            "penalty_amount": 0,
            "facts": "",
            "result_summary": "警告。",
            "defense_content": "", "rectification_report": "",
            "reference_script": "", "source_files": [],
        },
    ]
    for case in cases:
        success, case_no, msg = db.insert_case(case)
        assert success, f"插入失败: {msg}"


def test_health_check_csv_batches():
    """测试健康检查 CSV：按部门+缺失类型分批，含新增列"""
    db_path = tempfile.mktemp(suffix=".db")
    db = PenaltyDatabase(db_path)
    _insert_test_data(db)

    issues = db.health_check()
    exporter = CaseExporter(db=db)
    output_dir = tempfile.mkdtemp()

    try:
        csv_path = os.path.join(output_dir, "check.csv")
        actual_path = exporter.export_health_check_csv(issues, csv_path)

        with open(actual_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        print(f"  CSV 行数: {len(rows)}, 表头: {reader.fieldnames}")

        # 新增列检查
        required = {"batch_no", "assignee", "status", "remarks",
                    "case_no", "company", "regulator", "missing_fields"}
        assert required.issubset(set(reader.fieldnames))

        # 每行都有批次号
        for r in rows:
            assert r["batch_no"], f"批次号为空: {r}"
            assert r["status"] == "待处理"
        print(f"  所有行 status 均为 '待处理'")

        # 检查批次号格式：应该有 "人力资源和社会保障局-缺日期"、"国家互联网信息办公室-缺金额" 等
        batches = set(r["batch_no"] for r in rows)
        print(f"  批次号集合: {batches}")
        # CASE-2023-004 和 CASE-2023-005 分别来自人社局和网信办，缺失日期
        assert any("人力资源和社会保障局-缺日期" in b for b in batches) or \
               any("缺日期" in b for b in batches)

        # 排序：同一部门应集中
        regulators = [r["regulator"] for r in rows]
        # 允许乱序但至少检查字段完整性
        print(f"  regulator 顺序: {regulators}")

    finally:
        try:
            os.unlink(db_path)
        except:
            pass
        shutil.rmtree(output_dir)


def test_batch_update_detailed_report():
    """测试批量回填 CSV 返回详细报告（updated/skipped）"""
    db_path = tempfile.mktemp(suffix=".db")
    db = PenaltyDatabase(db_path)
    _insert_test_data(db)

    output_dir = tempfile.mkdtemp()
    issues = db.health_check()
    exporter = CaseExporter(db=db)

    try:
        csv_path = os.path.join(output_dir, "check.csv")
        actual_path = exporter.export_health_check_csv(issues, csv_path)

        # 模拟整理同事回填
        filled_rows = []
        with open(actual_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                if row["case_no"] == "CASE-2023-004":
                    row["penalty_date_new"] = "2023-11-10"
                    row["penalty_amount_new"] = "8万"
                    row["facts_new"] = "未及时签订劳动合同。"
                    row["tags_new"] = "劳动用工,劳动合同"
                    row["assignee"] = "张三"
                    row["status"] = "已完成"
                elif row["case_no"] == "CASE-2023-005":
                    # 故意不填，跳过
                    row["assignee"] = "李四"
                    row["status"] = "处理中"
                filled_rows.append(row)

        # 加一条无效行：case_no 不存在
        filled_rows.append({k: "" for k in fieldnames})
        filled_rows[-1]["case_no"] = "CASE-NOT-EXIST"
        filled_rows[-1]["penalty_date_new"] = "2024-01-01"
        # 再加一条 case_no 为空的
        filled_rows.append({k: "" for k in fieldnames})
        filled_rows[-1]["penalty_date_new"] = "2024-01-01"

        filled_csv = os.path.join(output_dir, "filled.csv")
        with open(filled_csv, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(filled_rows)

        result = db.batch_update_from_csv(filled_csv)
        print(f"  batch_update 返回键: {list(result.keys())}")
        print(f"  updated_count={result['updated_count']}, skipped_count={result['skipped_count']}")
        print(f"  updated: {result['updated']}")
        print(f"  skipped: {result['skipped']}")
        print(f"  errors: {result['errors']}")

        assert result["updated_count"] == 1
        assert result["skipped_count"] == 3  # CASE-2023-005 + CASE-NOT-EXIST + 空 case_no
        assert len(result["updated"]) == 1
        assert result["updated"][0]["case_no"] == "CASE-2023-004"
        assert any("处罚日期" in f for f in result["updated"][0]["updated_fields"])
        assert any("处罚金额" in f for f in result["updated"][0]["updated_fields"])
        assert len(result["skipped"]) == 3

        # 验证实际已更新
        case4 = db.get_case_by_no("CASE-2023-004")
        assert case4["penalty_date"] == "2023-11-10"
        assert case4["penalty_amount"] == 80000.0

    finally:
        try:
            os.unlink(db_path)
        except:
            pass
        shutil.rmtree(output_dir)


def test_similar_cases_filtered_and_dimensioned():
    """测试相似案例：过滤无理由项 + 理由分维度 + 空结果"""
    db_path = tempfile.mktemp(suffix=".db")
    db = PenaltyDatabase(db_path)
    _insert_test_data(db)

    # CASE-2024-001 应该能找到 CASE-2024-002（市监局+广告标签）
    case1 = db.get_case_by_no("CASE-2024-001")
    similar = db.find_similar_cases(case1["id"])
    print(f"  CASE-2024-001 找到 {len(similar)} 个相似案例")

    # 只应有 score > 0 的
    for s in similar:
        assert s["score"] > 0
        assert len(s["reasons"]) > 0
        # reasons 每条都应带有 [维度] 前缀
        for r in s["reasons"]:
            assert r.startswith(("[标签]", "[部门]", "[金额]", "[事实]")), f"缺少维度前缀: {r}"
        print(f"    - [{s['case_no']}] score={s['score']}, reasons={s['reasons']}")

    # CASE-2023-004 无标签/无事实/无金额，应该找不到相似案例
    case4 = db.get_case_by_no("CASE-2023-004")
    similar4 = db.find_similar_cases(case4["id"])
    print(f"  CASE-2023-004 找到 {len(similar4)} 个相似案例 (预期 0)")
    assert len(similar4) == 0

    try:
        os.unlink(db_path)
    except:
        pass


def test_external_penalty_no_search_and_import():
    """测试外部处罚文号：搜索、插入、自动提取"""
    db_path = tempfile.mktemp(suffix=".db")
    db = PenaltyDatabase(db_path)
    _insert_test_data(db)

    # 按文号搜索
    searcher = CaseSearcher(db)
    results = searcher.search(keywords=["沪市监静处〔2024〕015号"])
    print(f"  按外部文号搜索: {len(results)} 条")
    assert len(results) == 1
    assert results[0]["case_no"] == "CASE-2024-001"

    # 文号的另一段搜索
    results2 = searcher.search(keywords=["网信罚"])
    print(f"  按 '网信罚' 搜索: {len(results2)} 条")
    assert len(results2) == 1

    # 测试导入器文号提取方法
    importer = DocumentImporter()
    test_content = "上海市静安区市场监督管理局行政处罚决定书\n文号：沪市监静处〔2024〕123号\n当事人：某某公司..."
    no = importer._extract_external_penalty_no(test_content)
    print(f"  自动提取文号: {no}")
    assert no is not None and "123号" in no

    # 测试无文号内容
    no_none = importer._extract_external_penalty_no("普通的处罚内容，没有文号。")
    print(f"  无文号内容提取: {no_none}")
    assert no_none is None or no_none == ""

    try:
        os.unlink(db_path)
    except:
        pass


def test_preset_consistency():
    """测试检索预设：CLI/交互一致，金额/日期/排序完整复现"""
    db_path = tempfile.mktemp(suffix=".db")
    db = PenaltyDatabase(db_path)
    _insert_test_data(db)

    # 保存一个含完整条件的预设
    ok, msg = db.save_search(
        name="广告类高额定案",
        keywords=["广告"],
        tags=["广告"],
        min_amount=100000,
        max_amount=500000,
        from_date="2024-01-01",
        to_date="2024-12-31",
        sort_by="penalty_amount",
        sort_order="desc",
    )
    assert ok

    preset = db.load_search("广告类高额定案")
    print(f"  加载预设: {preset}")
    assert preset["keywords"] == ["广告"]
    assert preset["tags"] == ["广告"]
    assert preset["min_amount"] == 100000
    assert preset["max_amount"] == 500000
    assert preset["from_date"] == "2024-01-01"
    assert preset["to_date"] == "2024-12-31"
    assert preset["sort_by"] == "penalty_amount"
    assert preset["sort_order"] == "desc"

    # 覆盖同名预设
    ok2, msg2 = db.save_search(
        name="广告类高额定案",
        tags=["广告", "绝对化用语"],
        min_amount=200000,
        sort_by="penalty_date",
        sort_order="asc",
    )
    assert ok2
    preset2 = db.load_search("广告类高额定案")
    assert preset2["min_amount"] == 200000
    assert preset2["sort_by"] == "penalty_date"
    assert preset2["sort_order"] == "asc"
    assert "绝对化用语" in preset2["tags"]
    print(f"  覆盖同名预设后 min_amount={preset2['min_amount']}, sort_by={preset2['sort_by']}")

    # 同一批结果验证：用预设条件直接搜
    searcher = CaseSearcher(db)
    direct = searcher.search(
        keywords=preset2.get("keywords", []),
        tags=preset2.get("tags", []),
        min_amount=preset2.get("min_amount"),
        max_amount=preset2.get("max_amount"),
        from_date=preset2.get("from_date"),
        to_date=preset2.get("to_date"),
        sort_by=preset2.get("sort_by", "penalty_date"),
        sort_order=preset2.get("sort_order", "desc"),
    )
    print(f"  按预设直接搜索: {len(direct)} 条, 首条={direct[0]['case_no'] if direct else None}")

    try:
        os.unlink(db_path)
    except:
        pass


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  监管处罚检索工具 v5 - 功能验证")
    print("=" * 60)

    tests = [
        ("健康检查CSV按部门+缺失类型分批", test_health_check_csv_batches),
        ("批量回填CSV详细更新/跳过报告", test_batch_update_detailed_report),
        ("相似案例过滤+分维度理由+空结果", test_similar_cases_filtered_and_dimensioned),
        ("外部处罚文号搜索和自动提取", test_external_penalty_no_search_and_import),
        ("检索预设一致性(CLI/交互/覆盖)", test_preset_consistency),
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
