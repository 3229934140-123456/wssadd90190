"""v3版功能验证脚本 - 测试所有新增功能"""

import os
import sys
import tempfile
import shutil
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
    """插入3条测试数据"""
    cases = [
        {
            "case_no": "CASE-2024-001", "company": "测试公司A",
            "regulator": "市场监督管理局", "business_line": "电商业务",
            "tags": ["广告", "绝对化用语"], "penalty_date": "2024-03-15",
            "penalty_amount": 200000.0,
            "facts": "使用了绝对化用语'最佳''顶级'等词汇进行广告宣传。",
            "result_summary": "责令停止发布，罚款20万元。",
            "defense_content": "1. 违法行为轻微。\n2. 已主动整改。\n3. 没有造成危害后果。",
            "rectification_report": "1. 建立广告审核制度。\n2. 完善文案审核流程。\n3. 加强员工培训。",
            "reference_script": "我们已深刻认识到问题，立即采取整改措施。",
            "source_files": [],
        },
        {
            "case_no": "CASE-2024-002", "company": "测试公司B",
            "regulator": "网信办", "business_line": "APP业务",
            "tags": ["个人信息", "告知同意"], "penalty_date": "2024-06-01",
            "penalty_amount": 500000.0,
            "facts": "未按照规定充分告知用户个人信息处理方式。",
            "result_summary": "责令改正，罚款50万元。",
            "defense_content": "",
            "rectification_report": "1. 完善隐私政策。\n2. 优化同意流程。",
            "reference_script": "",
            "source_files": [],
        },
        {
            "case_no": "CASE-2023-003", "company": "测试公司C",
            "regulator": "人力资源和社会保障局", "business_line": "线下门店",
            "tags": ["劳动用工"], "penalty_date": "",
            "penalty_amount": 0,
            "facts": "",
            "result_summary": "责令改正。",
            "defense_content": "",
            "rectification_report": "",
            "reference_script": "",
            "source_files": [],
        },
    ]
    for case in cases:
        success, case_no, msg = db.insert_case(case)
        assert success, f"插入失败: {msg}"


def test_filter_only_search():
    """测试纯筛选搜索（不输入关键词）"""
    db_path = tempfile.mktemp(suffix=".db")
    db = PenaltyDatabase(db_path)
    _insert_test_data(db)

    results = db.search_keywords(min_amount=100000, max_amount=300000)
    print(f"  金额区间 10万-30万: {len(results)} 条")
    assert len(results) == 1

    results = db.search_keywords(regulator="市场")
    print(f"  监管部门'市场': {len(results)} 条")
    assert len(results) == 1

    results = db.search_keywords(from_date="2024-01-01", to_date="2024-12-31")
    print(f"  日期2024年: {len(results)} 条")
    assert len(results) == 2

    results = db.search_keywords(tags=["广告"])
    print(f"  标签'广告': {len(results)} 条")
    assert len(results) == 1

    try:
        os.unlink(db_path)
    except:
        pass


def test_saved_searches():
    """测试保存和调用检索条件"""
    db_path = tempfile.mktemp(suffix=".db")
    db = PenaltyDatabase(db_path)
    _insert_test_data(db)

    ok, msg = db.save_search(
        name="高额罚款",
        description="50万以上罚款",
        min_amount=500000,
    )
    print(f"  保存: {msg}")
    assert ok

    preset = db.load_search("高额罚款")
    assert preset is not None
    assert preset["min_amount"] == 500000
    print(f"  加载: name={preset['name']}, min_amount={preset['min_amount']}")

    presets = db.list_saved_searches()
    assert len(presets) >= 1
    print(f"  列出: {len(presets)} 个预设")

    ok = db.delete_saved_search("高额罚款")
    assert ok
    presets = db.list_saved_searches()
    assert len(presets) == 0
    print(f"  删除后: {len(presets)} 个预设")

    try:
        os.unlink(db_path)
    except:
        pass


def test_import_group_numbering():
    """测试导入分组的文件编号"""
    test_docs = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_docs")
    importer = DocumentImporter()

    file_list = [f for f in os.listdir(test_docs) if f.endswith('.txt')]
    file_paths = [os.path.join(test_docs, f) for f in file_list]

    groups = importer._smart_group_files(file_paths)

    total_files = sum(len(g["files"]) for g in groups)
    print(f"  分组数: {len(groups)}, 文件总数: {total_files}")
    assert total_files == 6
    assert len(groups) == 3

    # 测试 _refresh_group_stats 存在
    assert hasattr(importer, '_refresh_group_stats')
    print(f"  _refresh_group_stats 方法存在: True")


def test_comparison_export():
    """测试对比清单导出"""
    db_path = tempfile.mktemp(suffix=".db")
    db = PenaltyDatabase(db_path)
    _insert_test_data(db)

    case_ids = []
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM penalties ORDER BY id")
        for row in cursor.fetchall():
            case_ids.append(row[0])

    exporter = CaseExporter(db=db)
    output_dir = tempfile.mkdtemp()

    try:
        # 测试 MD 格式对比
        md_path = exporter.export_comparison(
            case_ids[:2], os.path.join(output_dir, "compare.md"),
            title="案例对比测试", format_type="md"
        )
        print(f"  MD对比导出: {md_path}")
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "监管部门" in content
        assert "违法事实" in content
        assert "申辩要点" in content
        assert "整改动作" in content
        assert "处罚金额" in content

        # 测试 TXT 格式对比
        txt_path = exporter.export_comparison(
            case_ids[:2], os.path.join(output_dir, "compare.txt"),
            format_type="txt"
        )
        print(f"  TXT对比导出: {txt_path}")
        with open(txt_path, "r", encoding="utf-8") as f:
            txt_content = f.read()
        assert "监管部门" in txt_content

        # 测试 JSON 格式对比
        json_path = exporter.export_comparison(
            case_ids[:2], os.path.join(output_dir, "compare.json"),
            format_type="json"
        )
        print(f"  JSON对比导出: {json_path}")
        with open(json_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)
        assert "cases" in json_data
        assert len(json_data["cases"]) == 2
        assert "comparison_dimensions" in json_data["cases"][0]
        assert "regulator" in json_data["cases"][0]["comparison_dimensions"]

        print(f"  生成 {len(os.listdir(output_dir))} 个导出文件")

    finally:
        try:
            os.unlink(db_path)
        except:
            pass
        shutil.rmtree(output_dir)


def test_health_check():
    """测试资料库健康检查"""
    db_path = tempfile.mktemp(suffix=".db")
    db = PenaltyDatabase(db_path)
    _insert_test_data(db)

    issues = db.health_check()
    summary = issues["summary"]

    print(f"  总案例: {summary['total_cases']}")
    print(f"  缺失日期: {summary['missing_date_count']}")
    print(f"  缺失金额: {summary['missing_amount_count']}")
    print(f"  缺失事实: {summary['missing_facts_count']}")
    print(f"  缺失标签: {summary['missing_tags_count']}")

    assert summary["total_cases"] == 3
    assert summary["missing_date_count"] == 1  # CASE-2023-003 没有日期
    assert summary["missing_amount_count"] == 1  # CASE-2023-003 金额为0
    assert summary["missing_facts_count"] == 1  # CASE-2023-003 事实为空

    # 验证检查结果可导出
    exporter = CaseExporter(db=db)
    output_dir = tempfile.mkdtemp()

    try:
        # 导出为 JSON
        json_path = os.path.join(output_dir, "check.json")
        export_data = {
            "title": "健康检查报告",
            "summary": summary,
            "issues": {k: v for k, v in issues.items() if k != "summary"},
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        print(f"  检查结果已导出: {json_path}")

        # 导出为 MD
        md_path = os.path.join(output_dir, "check.md")
        lines = ["# 健康检查报告", f"- 案例总数: {summary['total_cases']}"]
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"  检查结果MD导出: {md_path}")

    finally:
        try:
            os.unlink(db_path)
        except:
            pass
        shutil.rmtree(output_dir)


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  监管处罚检索工具 v3 - 功能验证")
    print("=" * 60)

    tests = [
        ("纯筛选搜索（无需关键词）", test_filter_only_search),
        ("保存/调用检索条件", test_saved_searches),
        ("导入分组编号与刷新", test_import_group_numbering),
        ("对比清单导出", test_comparison_export),
        ("资料库健康检查", test_health_check),
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
