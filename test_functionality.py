"""功能验证脚本 - 测试导入、搜索、导出功能"""

import os
import sys
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from penalty_tool.database import PenaltyDatabase
from penalty_tool.importer import DocumentImporter
from penalty_tool.searcher import CaseSearcher
from penalty_tool.exporter import CaseExporter


def test_database():
    """测试数据库基本功能"""
    print("=" * 60)
    print("[测试1] 数据库初始化与基础操作")
    print("=" * 60)

    test_db_path = os.path.join(os.path.dirname(__file__), "data", "test_penalty.db")
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    db = PenaltyDatabase(test_db_path)

    case_data = {
        "company": "XX科技有限公司",
        "regulator": "XX市市场监督管理局",
        "business_line": "广告业务",
        "tags": ["广告法", "绝对化用语"],
        "penalty_date": "2024-04-20",
        "penalty_amount": 200000,
        "result_summary": "因使用绝对化用语被处罚20万元，已整改完毕",
        "facts": "当事人在官网及电商平台使用'全网最低价'、'行业第一'等绝对化用语，违反广告法第九条。",
        "defense_content": "当事人主动下架广告，系初次违法，请求从轻处罚。",
        "rectification_report": "已建立三级审核制度，组织全员培训。",
        "reference_script": "参考话术：'我司高度重视广告合规问题，已第一时间下架全部涉嫌违规内容，并建立了严格的广告内容审查机制。'",
        "internal_amount_analysis": "内部测算：如从重处罚可能涉及80-120万，通过申辩降至20万，节省约60万。",
        "sensitive_contacts": "经办人：张XX 13800138000，对接律师：李律师 13900139000",
        "source_files": ["处罚决定书.txt"]
    }

    success, case_no, msg = db.insert_case(case_data)
    print(f"  插入案例: {msg}, 编号={case_no}")
    assert success, "插入失败"

    case_data2 = {
        "company": "XX数据服务有限公司",
        "regulator": "XX市互联网信息办公室",
        "business_line": "数据合规",
        "tags": ["个保法", "告知同意"],
        "penalty_date": "2024-05-15",
        "penalty_amount": 500000,
        "result_summary": "因个人信息告知不充分被处罚50万元",
        "facts": "APP未以显著方式告知个人信息处理规则，申请权限未说明目的，违反最小必要原则。",
        "reference_script": "话术：'关于个人信息保护，我司严格遵循告知同意原则，确保用户知情权和选择权。'",
        "source_files": ["网信处罚.txt"]
    }

    success2, case_no2, msg2 = db.insert_case(case_data2)
    print(f"  插入案例2: {msg2}, 编号={case_no2}")
    assert success2

    case_data3 = {
        "company": "XX商贸有限公司",
        "regulator": "XX市人社局",
        "business_line": "人力资源",
        "tags": ["劳动合同法", "书面合同"],
        "penalty_date": "2023-11-28",
        "penalty_amount": 385000,
        "result_summary": "17名员工未及时签劳动合同，处罚38.5万",
        "facts": "23名新员工中17人未在入职一月内签合同，8人超一年未签无固定期限合同。",
        "source_files": ["人社处罚.txt"]
    }
    success3, case_no3, msg3 = db.insert_case(case_data3)
    print(f"  插入案例3: {msg3}, 编号={case_no3}")

    stats = db.get_stats()
    print(f"  统计: 共{stats['total_cases']}个案例, 总金额{stats['total_penalty_amount']}元")
    assert stats["total_cases"] == 3

    print("  ✓ 数据库测试通过\n")
    return db, test_db_path, [case_no, case_no2, case_no3]


def test_search(db):
    """测试搜索功能"""
    print("=" * 60)
    print("[测试2] 关键词搜索功能")
    print("=" * 60)

    searcher = CaseSearcher(db)

    results = searcher.search(keywords=["广告", "绝对化用语"])
    print(f"  搜索'广告 绝对化用语': 找到{len(results)}个案例")
    for r in results:
        print(f"    - {r['case_no']} | {r['company']} | {r['penalty_amount_formatted']}")
    assert len(results) >= 1
    assert "广告法" in results[0].get("tags", []) or "广告业务" in results[0].get("business_line", "")

    results2 = searcher.search(keywords=["个人信息", "告知同意"])
    print(f"  搜索'个人信息 告知同意': 找到{len(results2)}个案例")
    for r in results2:
        print(f"    - {r['case_no']} | {r['company']} | {r['penalty_amount_formatted']}")
    assert len(results2) >= 1

    results3 = searcher.search(keywords=["劳动合同"])
    print(f"  搜索'劳动合同': 找到{len(results3)}个案例")
    for r in results3:
        print(f"    - {r['case_no']} | {r['company']} | {r['penalty_amount_formatted']}")
    assert len(results3) >= 1

    results4 = searcher.search(keyword_str="未及时签劳动合同")
    print(f"  模糊搜索'未及时签劳动合同': 找到{len(results4)}个案例")
    assert len(results4) >= 1

    results5 = searcher.search(keywords=["处罚"], business_line="人力资源")
    print(f"  按业务线筛选'人力资源': 找到{len(results5)}个案例")
    assert len(results5) >= 1 and results5[0]["business_line"] == "人力资源"

    results6 = searcher.search(keywords=[])
    print(f"  无关键词全量搜索: 找到{len(results6)}个案例")
    assert len(results6) == 3

    output = searcher.format_results_table(results, highlight=["绝对化用语"])
    assert "绝对化用语" in output

    print("  ✓ 搜索测试通过\n")
    return searcher


def test_importer(db):
    """测试导入模块（文件读取+自动分类）"""
    print("=" * 60)
    print("[测试3] 文档导入模块")
    print("=" * 60)

    importer = DocumentImporter(db)
    test_folder = os.path.join(os.path.dirname(__file__), "test_docs")

    files = []
    if os.path.isdir(test_folder):
        from penalty_tool.utils import scan_document_folder
        files = scan_document_folder(test_folder)
        print(f"  扫描测试文件夹: 找到{len(files)}个文档")
        for f in files:
            print(f"    - {os.path.basename(f)}")

    assert len(files) >= 5, f"测试文档数量不足: {len(files)}"

    for f in files:
        content = importer.read_document_content(f)
        filename = os.path.basename(f)
        doc_type = importer._classify_document(filename, content)
        print(f"  分类: {filename[:30]}... -> {doc_type}")
        assert len(content) > 50, f"文档读取失败: {filename}"

    from penalty_tool.utils import extract_amount_from_text
    sample_content = "处罚款人民币20万元整"
    amount = extract_amount_from_text(sample_content)
    print(f"  金额提取测试: '处罚款人民币20万元整' -> {amount}")
    assert amount and amount > 0

    from penalty_tool.utils import generate_summary
    sample = "这是一段测试文字。它包含多个句子。用于测试摘要生成功能是否正常工作。" * 10
    summary = generate_summary(sample, 100)
    print(f"  摘要生成测试: 生成{len(summary)}字摘要")
    assert 0 < len(summary) <= 150

    print("  ✓ 导入模块测试通过\n")


def test_exporter(db):
    """测试导出功能"""
    print("=" * 60)
    print("[测试4] 案例导出与脱敏")
    print("=" * 60)

    exporter = CaseExporter(db)

    all_cases = db.list_all_cases(limit=10)
    case_ids = [c["id"] for c in all_cases]
    print(f"  待导出案例数: {len(case_ids)}")

    export_dir = os.path.join(os.path.dirname(__file__), "test_exports")
    os.makedirs(export_dir, exist_ok=True)

    md_path = exporter.export_to_markdown(
        case_ids,
        os.path.join(export_dir, "test_export.md"),
        title="测试导出参考清单"
    )
    print(f"  Markdown导出: {md_path}")
    assert os.path.exists(md_path)

    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    assert "测试导出参考清单" in md_content
    assert "违法事实" in md_content
    assert "处理结果" in md_content
    assert "可借鉴话术" in md_content
    assert "20万元" in md_content or "200000" in md_content

    assert "13800138000" not in md_content, "手机号未脱敏"
    assert "13900139000" not in md_content, "手机号未脱敏"
    assert "内部测算" not in md_content, "内部金额测算未隐藏"
    assert "张XX" not in md_content or "对接律师" not in md_content, "敏感联系人未隐藏"
    print("  ✓ 脱敏检查通过（手机号、内部测算已隐藏）")

    txt_path = exporter.export_to_text(
        case_ids,
        os.path.join(export_dir, "test_export.txt"),
        title="测试导出参考清单(TXT)"
    )
    print(f"  TXT导出: {txt_path}")
    assert os.path.exists(txt_path)

    json_path = exporter.export_to_json(
        case_ids,
        os.path.join(export_dir, "test_export.json")
    )
    print(f"  JSON导出: {json_path}")
    assert os.path.exists(json_path)

    import json
    with open(json_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)
    assert json_data["case_count"] == len(case_ids)
    assert "cases" in json_data
    assert "internal_amount_analysis" not in json_data["cases"][0]
    assert "sensitive_contacts" not in json_data["cases"][0]
    print("  ✓ JSON导出字段检查通过（敏感字段已排除）")

    auto_path = exporter.auto_export_path(format_type="md")
    print(f"  自动路径生成: {os.path.basename(auto_path)}")
    assert auto_path.endswith(".md")

    print("  ✓ 导出测试通过\n")
    return export_dir


def test_cli_commands():
    """测试CLI直接命令模式"""
    print("=" * 60)
    print("[测试5] CLI直接命令模式")
    print("=" * 60)

    import subprocess

    main_py = os.path.join(os.path.dirname(__file__), "main.py")
    test_db = os.path.join(os.path.dirname(__file__), "data", "test_penalty.db")

    def _run(args):
        """安全运行子进程并处理编码"""
        result = subprocess.run(
            args,
            capture_output=True,
            timeout=30
        )
        stdout = ""
        for enc in ["utf-8", "gbk", "mbcs"]:
            try:
                stdout = result.stdout.decode(enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if not stdout:
            stdout = result.stdout.decode("utf-8", errors="ignore")
        stderr = ""
        for enc in ["utf-8", "gbk", "mbcs"]:
            try:
                stderr = result.stderr.decode(enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        result.stdout = stdout
        result.stderr = stderr
        return result

    result = _run(
        [sys.executable, main_py, "-d", test_db, "stats"]
    )
    print(f"  stats命令输出 (长度={len(result.stdout)}):")
    lines = result.stdout.strip().split("\n")
    for line in lines[:8]:
        print(f"    {line}")
    assert result.returncode == 0, f"stats命令失败: {result.stderr}"
    assert "案例总数" in result.stdout or "3" in result.stdout

    result2 = _run(
        [sys.executable, main_py, "-d", test_db, "search", "广告", "绝对化用语"]
    )
    print(f"  search命令输出 (长度={len(result2.stdout)}):")
    lines = result2.stdout.strip().split("\n")
    for line in lines[:10]:
        print(f"    {line}")
    assert result2.returncode == 0, f"search命令失败: {result2.stderr}"
    assert "找到" in result2.stdout or "匹配" in result2.stdout or "XX科技" in result2.stdout

    result3 = _run(
        [sys.executable, main_py, "-d", test_db, "list", "-n", "5"]
    )
    assert result3.returncode == 0, f"list命令失败: {result3.stderr}"
    print(f"  list命令执行成功 (输出长度={len(result3.stdout)})")

    print("  ✓ CLI命令测试通过\n")


def test_view_and_delete(db):
    """测试详情查看和删除功能"""
    print("=" * 60)
    print("[测试6] 详情查看与删除功能")
    print("=" * 60)

    searcher = CaseSearcher(db)
    all_cases = db.list_all_cases(limit=10)
    assert len(all_cases) > 0

    first_case = all_cases[0]
    detail = searcher.format_case_detail(first_case["id"])
    print(f"  案例详情输出 (长度={len(detail)}):")
    print(f"    包含案例编号: {first_case['case_no'] in detail}")
    print(f"    包含违法事实: {'违法事实' in detail}")
    print(f"    包含可借鉴话术: {'可借鉴话术' in detail}")
    assert first_case["case_no"] in detail
    assert "违法事实" in detail

    detail_by_no = db.get_case_by_no(first_case["case_no"])
    assert detail_by_no is not None
    assert detail_by_no["company"] == first_case["company"]
    print(f"  通过案例号查询: OK")

    companies = db.list_companies()
    regulators = db.list_regulators()
    tags = db.list_tags()
    print(f"  公司列表: {len(companies)}家, 监管列表: {len(regulators)}个, 标签: {len(tags)}个")
    assert len(companies) >= 2

    non_existent = db.get_case_by_id(99999)
    assert non_existent is None
    print(f"  不存在ID返回None: OK")

    print("  ✓ 详情与查询测试通过\n")


def main():
    print("\n" + "╔" + "═" * 58 + "╗")
    print("║" + " " * 15 + "监管处罚检索工具 - 功能验证" + " " * 18 + "║")
    print("╚" + "═" * 58 + "╝")
    print()

    try:
        db, db_path, case_nos = test_database()
        test_view_and_delete(db)
        test_search(db)
        test_importer(db)
        test_exporter(db)
        test_cli_commands()

        print("╔" + "═" * 58 + "╗")
        print("║" + " " * 20 + "✓ 全部测试通过!" + " " * 22 + "║")
        print("╚" + "═" * 58 + "╝")
        print()
        print(f"  测试数据库: {db_path}")
        print(f"  导入的案例号: {', '.join(case_nos)}")
        print(f"  导出文件: {os.path.join(os.path.dirname(__file__), 'test_exports')}/")
        print()
        print("  下一步:")
        print("    1. 运行 'python main.py' 启动交互式界面")
        print("    2. 尝试 'search 广告绝对化用语' 等命令")
        print("    3. 使用 'export 1,2' 导出参考清单")
        print()

        return True

    except AssertionError as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"\n✗ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
