"""快速功能验证脚本 - 测试v2版所有新功能"""

import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from penalty_tool.database import PenaltyDatabase
from penalty_tool.importer import DocumentImporter
from penalty_tool.searcher import CaseSearcher
from penalty_tool.exporter import CaseExporter


def run_test(name, func):
    """运行单个测试"""
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


def test_smart_grouping():
    """测试智能文件分组"""
    test_docs = os.path.join(os.path.dirname(__file__), "test_docs")
    importer = DocumentImporter()

    file_list = [f for f in os.listdir(test_docs) if f.endswith('.txt')]
    file_paths = [os.path.join(test_docs, f) for f in file_list]

    groups = importer._smart_group_files(file_paths)

    print(f"  共发现 {len(file_paths)} 个文件，分为 {len(groups)} 组：")
    for i, g in enumerate(groups, 1):
        files_str = "\n      - ".join([f['name'] + f" ({f['type']})" for f in g["files"]])
        print(f"    组{i} [{g.get('display_name', g.get('key', ''))}]:")
        print(f"      - {files_str}")
        print(f"      包含类型: 处罚决定书={g.get('has_penalty', False)}, "
              f"申辩意见={g.get('has_defense', False)}, "
              f"整改报告={g.get('has_rectification', False)}")

    assert len(groups) == 3, f"应该有3组，实际{len(groups)}组"

    group_file_counts = sorted([len(g["files"]) for g in groups])
    assert group_file_counts == [1, 2, 3], f"文件数量分布不正确: {group_file_counts}"


def test_search_with_filters():
    """测试带筛选的搜索"""
    db_path = tempfile.mktemp(suffix=".db")
    db = PenaltyDatabase(db_path)

    test_cases = [
        {
            "case_no": "CASE-2024-001",
            "company": "测试公司A",
            "regulator": "市场监督管理局",
            "business_line": "电商业务",
            "tags": ["广告", "绝对化用语"],
            "penalty_date": "2024-03-15",
            "penalty_amount": 200000.0,
            "facts": "使用了绝对化用语'最佳''顶级'等词汇进行广告宣传。",
            "result_summary": "责令停止发布，罚款20万元。",
            "defense_content": "1. 违法行为轻微。\n2. 已主动整改。\n3. 没有造成危害后果。",
            "rectification_report": "1. 建立广告审核制度。\n2. 完善文案审核流程。\n3. 加强员工培训。",
            "reference_script": "我们已深刻认识到问题，立即采取整改措施。",
            "source_files": [],
        },
        {
            "case_no": "CASE-2024-002",
            "company": "测试公司B",
            "regulator": "网信办",
            "business_line": "APP业务",
            "tags": ["个人信息", "告知同意"],
            "penalty_date": "2024-06-01",
            "penalty_amount": 500000.0,
            "facts": "未按照规定充分告知用户个人信息处理方式。",
            "result_summary": "责令改正，罚款50万元。",
            "defense_content": "",
            "rectification_report": "1. 完善隐私政策。\n2. 优化同意流程。",
            "reference_script": "",
            "source_files": [],
        },
        {
            "case_no": "CASE-2023-003",
            "company": "测试公司C",
            "regulator": "人力资源和社会保障局",
            "business_line": "线下门店",
            "tags": ["劳动用工", "劳动合同"],
            "penalty_date": "2023-11-20",
            "penalty_amount": 80000.0,
            "facts": "未及时与员工签订书面劳动合同。",
            "result_summary": "责令改正，罚款8万元。",
            "defense_content": "",
            "rectification_report": "",
            "reference_script": "",
            "source_files": [],
        },
    ]

    case_ids = []
    for case in test_cases:
        success, case_no, msg = db.insert_case(case)
        assert success, f"插入失败: {msg}"
        # 获取case_id
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM penalties WHERE case_no = ?", (case_no,))
            row = cursor.fetchone()
            case_ids.append(row[0])

    print(f"  已插入 {len(case_ids)} 条测试数据")

    # 测试1: 关键词搜索 + 命中片段
    results = db.search_keywords(keywords=["绝对化用语"])
    print(f"\n  测试1: 关键词搜索 '绝对化用语' → {len(results)} 条结果")
    assert len(results) == 1
    assert "snippets" in results[0]
    print(f"    命中片段数量: {len(results[0].get('snippets', []))}")
    for snip in results[0].get("snippets", []):
        print(f"    [{snip['field']}] ...{snip['text']}...")
    assert len(results[0].get("snippets", [])) > 0

    # 测试2: 金额区间筛选
    results = db.search_keywords(min_amount=100000, max_amount=300000)
    print(f"\n  测试2: 金额区间 10万-30万 → {len(results)} 条结果")
    assert len(results) == 1

    # 测试3: 日期范围筛选
    results = db.search_keywords(from_date="2024-01-01", to_date="2024-12-31")
    print(f"\n  测试3: 日期范围 2024年 → {len(results)} 条结果")
    assert len(results) == 2

    # 测试4: 监管部门筛选
    results = db.search_keywords(regulator="市场")
    print(f"\n  测试4: 监管部门 '市场' → {len(results)} 条结果")
    assert len(results) == 1

    # 测试5: 标签筛选
    results = db.search_keywords(tags=["个人信息"])
    print(f"\n  测试5: 标签 '个人信息' → {len(results)} 条结果")
    assert len(results) == 1

    # 测试6: 多标签AND筛选
    results = db.search_keywords(tags=["广告", "绝对化用语"])
    print(f"\n  测试6: 多标签AND '广告'+'绝对化用语' → {len(results)} 条结果")
    assert len(results) == 1

    # 测试7: 组合筛选
    results = db.search_keywords(
        keywords=["罚款"],
        min_amount=100000,
        from_date="2024-01-01",
        tags=["广告"],
    )
    print(f"\n  测试7: 组合筛选(关键词+金额+日期+标签) → {len(results)} 条结果")
    assert len(results) == 1

    # 测试8: 排序
    results = db.search_keywords(sort_by="penalty_amount", sort_order="desc")
    amounts = [r["penalty_amount"] for r in results]
    print(f"\n  测试8: 按金额降序 → {amounts}")
    assert amounts == sorted(amounts, reverse=True)

    # 测试9: 公司筛选
    results = db.search_keywords(company="测试公司A")
    print(f"\n  测试9: 公司筛选 → {len(results)} 条结果")
    assert len(results) == 1

    # 测试10: 业务线筛选
    results = db.search_keywords(business_line="电商")
    print(f"\n  测试10: 业务线筛选 → {len(results)} 条结果")
    assert len(results) == 1

    try:
        os.unlink(db_path)
    except Exception:
        pass  # Windows上有时SQLite文件锁定，忽略删除错误


def test_export_templates():
    """测试三种导出模板"""
    db_path = tempfile.mktemp(suffix=".db")
    db = PenaltyDatabase(db_path)

    case_data = {
        "case_no": "CASE-TEST-001",
        "company": "测试公司",
        "regulator": "市场监管局",
        "business_line": "电商业务",
        "tags": ["广告", "绝对化用语"],
        "penalty_date": "2024-03-15",
        "penalty_amount": 200000.0,
        "facts": "使用了绝对化用语'最佳''顶级'等词汇进行广告宣传。该行为违反了广告法相关规定。",
        "result_summary": "责令停止发布违法广告，罚款人民币20万元整。",
        "defense_content": "1. 违法行为轻微，持续时间短。\n2. 已主动整改，删除相关内容。\n3. 没有造成实际危害后果。",
        "rectification_report": "1. 建立广告内容审核制度。\n2. 完善文案三级审核流程。\n3. 加强员工合规培训。\n4. 定期开展广告合规自查。",
        "reference_script": "我们已深刻认识到问题的严重性，立即采取了整改措施。",
        "source_files": [],
    }

    success, case_no, msg = db.insert_case(case_data)
    assert success

    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM penalties WHERE case_no = ?", (case_no,))
        case_id = cursor.fetchone()[0]

    exporter = CaseExporter(db=db)
    output_dir = tempfile.mkdtemp()

    try:
        # 测试完整版
        md_full = exporter.export_to_markdown(
            [case_id],
            os.path.join(output_dir, "full.md"),
            template="full",
        )
        print(f"  完整版导出: {md_full}")
        with open(md_full, "r", encoding="utf-8") as f:
            content_full = f.read()
        assert "违法事实" in content_full
        assert "申辩意见" in content_full
        assert "整改措施" in content_full
        assert "可借鉴话术" in content_full

        # 测试律师版
        md_lawyer = exporter.export_to_markdown(
            [case_id],
            os.path.join(output_dir, "lawyer.md"),
            template="lawyer",
        )
        print(f"  律师版导出: {md_lawyer}")
        with open(md_lawyer, "r", encoding="utf-8") as f:
            content_lawyer = f.read()
        assert "申辩意见及抗辩要点" in content_lawyer
        assert "整改措施及合规启示" in content_lawyer
        assert "参考表述" in content_lawyer

        # 测试业务版
        md_business = exporter.export_to_markdown(
            [case_id],
            os.path.join(output_dir, "business.md"),
            template="business",
        )
        print(f"  业务版导出: {md_business}")
        with open(md_business, "r", encoding="utf-8") as f:
            content_business = f.read()
        assert "事实概要" in content_business
        assert "处理结果及影响" in content_business
        assert "整改动作" in content_business
        assert "可借鉴话术" in content_business
        assert "申辩意见" not in content_business

        # 测试TXT导出
        txt_path = exporter.export_to_text(
            [case_id],
            os.path.join(output_dir, "business.txt"),
            template="business",
        )
        print(f"  TXT导出: {txt_path}")

        # 测试JSON导出
        json_path = exporter.export_to_json(
            [case_id],
            os.path.join(output_dir, "lawyer.json"),
            template="lawyer",
        )
        print(f"  JSON导出: {json_path}")
        import json
        with open(json_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)
        assert "defense_key_points" in json_data["cases"][0]
        assert "rectification_key_points" in json_data["cases"][0]
        assert len(json_data["cases"][0]["defense_key_points"]) > 0
        assert len(json_data["cases"][0]["rectification_key_points"]) > 0

        print(f"\n  共生成 {len(os.listdir(output_dir))} 个导出文件")

    finally:
        try:
            os.unlink(db_path)
        except Exception:
            pass
        shutil.rmtree(output_dir)


def test_search_formatter():
    """测试搜索结果格式化（带命中片段）"""
    db_path = tempfile.mktemp(suffix=".db")
    db = PenaltyDatabase(db_path)

    case_data = {
        "case_no": "CASE-FMT-001",
        "company": "演示公司",
        "regulator": "市场监管局",
        "business_line": "电商",
        "tags": ["广告", "绝对化用语"],
        "penalty_date": "2024-01-15",
        "penalty_amount": 200000,
        "facts": "当事人在其官方网站上使用了最佳、顶级等绝对化用语进行产品宣传。",
        "result_summary": "责令停止发布，罚款20万元。",
        "defense_content": "",
        "rectification_report": "",
        "reference_script": "",
        "source_files": [],
    }

    success, case_no, msg = db.insert_case(case_data)
    assert success

    results = db.search_keywords(keywords=["绝对化用语"])
    assert len(results) == 1

    searcher = CaseSearcher(db=db)
    table_str = searcher.format_results_table(results, show_snippets=True)
    print(table_str)
    assert len(table_str) > 100
    assert "『" in table_str or "绝对化用语" in table_str

    try:
        os.unlink(db_path)
    except Exception:
        pass  # Windows上有时SQLite文件锁定，忽略删除错误


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  监管处罚检索工具 v2 - 功能验证")
    print("=" * 60)

    tests = [
        ("智能文件分组", test_smart_grouping),
        ("搜索筛选+命中片段", test_search_with_filters),
        ("导出三模板", test_export_templates),
        ("搜索结果格式化", test_search_formatter),
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
