"""监管处罚应对命令行检索工具 - CLI主入口"""

import argparse
import sys
import os
import cmd
from typing import Optional, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from penalty_tool.database import PenaltyDatabase
from penalty_tool.importer import DocumentImporter
from penalty_tool.searcher import CaseSearcher
from penalty_tool.exporter import CaseExporter
from penalty_tool.utils import format_amount, parse_input_list


class PenaltyShell(cmd.Cmd):
    """交互式命令行Shell"""

    intro = """
╔══════════════════════════════════════════════════════════════╗
║       监管处罚应对命令行检索工具 v2.0                          ║
║       Penalty Retrieval CLI                                    ║
╠══════════════════════════════════════════════════════════════╣
║  常用命令：                                                     ║
║    search <关键词>    - 搜索案例（多关键词空格分隔）           ║
║    import <文件夹>    - 批量导入处罚文档（自动分组+预览）       ║
║    list               - 列出所有案例                           ║
║    view <编号>        - 查看案例详情                           ║
║    export <编号...>   - 导出参考清单（律师版/业务版）           ║
║    stats              - 查看数据库统计                         ║
║    help <命令>        - 查看命令详细帮助                       ║
║    quit / exit        - 退出工具                               ║
╠══════════════════════════════════════════════════════════════╣
║  高级搜索示例：                                                 ║
║    search 广告 -r 市监局 --min 10万 --max 50万                 ║
║    search 个人信息 -b 数据合规 --from 2024-01-01               ║
╚══════════════════════════════════════════════════════════════╝
    """

    prompt = "\n[penalty]> "

    def __init__(self, db_path: Optional[str] = None):
        super().__init__()
        self.db = PenaltyDatabase(db_path)
        self.importer = DocumentImporter(self.db)
        self.searcher = CaseSearcher(self.db)
        self.exporter = CaseExporter(self.db)
        self._last_results = []
        self._last_keywords = []

    # ============ search 命令 ============
    def do_search(self, arg: str):
        """搜索案例：search <关键词1> [关键词2] ... [选项]

选项：
  -c, --company <公司>       按所属公司过滤（模糊匹配）
  -r, --regulator <部门>     按监管部门过滤（模糊匹配）
  -b, --business <业务线>    按业务线过滤
  -t, --tags <标签>          按标签过滤（多个标签用逗号分隔，AND关系）
      --min <金额>           最低处罚金额（支持'10万'、'50000'等格式）
      --max <金额>           最高处罚金额
      --from <日期>          起始日期 YYYY-MM-DD
      --to   <日期>          结束日期 YYYY-MM-DD
      --sort <字段>          排序字段：date/amount/created（默认date）
      --order <方向>         排序方向：asc/desc（默认desc）
  -n, --limit <数量>         返回结果数量上限（默认50）

示例：
  search 广告绝对化用语
  search 个人信息 告知同意 -c 某科技公司
  search 劳动合同 -b 人力资源 --min 5万 --max 50万
  search 数据合规 --from 2024-01-01 --to 2024-12-31 --sort amount --order desc
        """
        args = self._parse_search_args(arg)
        if not args["keywords"] and not any([
            args["company"], args["regulator"], args["business_line"],
            args["tags"], args["min_amount"] is not None, args["max_amount"] is not None,
            args["from_date"], args["to_date"]
        ]):
            print("  ! 请输入搜索关键词或过滤条件（输入 'help search' 查看选项）")
            return

        results = self.searcher.search(
            keywords=args["keywords"],
            company=args["company"],
            regulator=args["regulator"],
            business_line=args["business_line"],
            tags=args["tags"],
            min_amount=args["min_amount"],
            max_amount=args["max_amount"],
            from_date=args["from_date"],
            to_date=args["to_date"],
            sort_by=args["sort_by"],
            sort_order=args["sort_order"],
            limit=args["limit"]
        )

        self._last_results = results
        self._last_keywords = args["keywords"]

        output = self.searcher.format_results_table(
            results, highlight=args["keywords"], show_snippets=True
        )
        print(output)

    def _parse_search_args(self, arg_str: str) -> dict:
        """解析search命令的参数"""
        parts = arg_str.split()
        keywords = []
        company = regulator = business_line = None
        tags = []
        min_amount = max_amount = None
        from_date = to_date = None
        sort_by = "penalty_date"
        sort_order = "desc"
        limit = 50

        i = 0
        while i < len(parts):
            p = parts[i]

            if p in ("-c", "--company") and i + 1 < len(parts):
                company = parts[i + 1]
                i += 2
            elif p in ("-r", "--regulator") and i + 1 < len(parts):
                regulator = parts[i + 1]
                i += 2
            elif p in ("-b", "--business") and i + 1 < len(parts):
                business_line = parts[i + 1]
                i += 2
            elif p in ("-t", "--tags") and i + 1 < len(parts):
                tags = parse_input_list(parts[i + 1])
                i += 2
            elif p == "--min" and i + 1 < len(parts):
                min_amount = self._parse_amount(parts[i + 1])
                i += 2
            elif p == "--max" and i + 1 < len(parts):
                max_amount = self._parse_amount(parts[i + 1])
                i += 2
            elif p == "--from" and i + 1 < len(parts):
                from_date = self._normalize_date(parts[i + 1])
                i += 2
            elif p == "--to" and i + 1 < len(parts):
                to_date = self._normalize_date(parts[i + 1])
                i += 2
            elif p == "--sort" and i + 1 < len(parts):
                sort_map = {
                    "date": "penalty_date", "amount": "penalty_amount",
                    "created": "created_at", "company": "company"
                }
                sort_by = sort_map.get(parts[i + 1].lower(), "penalty_date")
                i += 2
            elif p == "--order" and i + 1 < len(parts):
                sort_order = parts[i + 1].lower()
                i += 2
            elif p in ("-n", "--limit") and i + 1 < len(parts):
                try:
                    limit = int(parts[i + 1])
                except ValueError:
                    pass
                i += 2
            elif not p.startswith("-"):
                keywords.append(p)
                i += 1
            else:
                i += 1

        return {
            "keywords": keywords,
            "company": company,
            "regulator": regulator,
            "business_line": business_line,
            "tags": tags,
            "min_amount": min_amount,
            "max_amount": max_amount,
            "from_date": from_date,
            "to_date": to_date,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "limit": limit
        }

    def _parse_amount(self, amount_str: str) -> Optional[float]:
        """解析金额字符串，支持'10万'、'5万'、'50000'等格式"""
        if not amount_str:
            return None
        amount_str = amount_str.strip().replace(",", "").replace("元", "")
        try:
            if amount_str.endswith("万"):
                num = float(amount_str[:-1])
                return num * 10000
            else:
                return float(amount_str)
        except ValueError:
            return None

    def _normalize_date(self, date_str: str) -> str:
        """标准化日期格式为 YYYY-MM-DD"""
        import re
        date_str = date_str.strip()
        m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", date_str)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        return date_str

    # ============ import 命令 ============
    def do_import(self, arg: str):
        """导入文档：import <文件夹路径>

交互式批量导入处罚文档，自动识别案件并分组，
支持分组预览和调整，确认后再入库。

示例：
  import ./documents/2024_cases
  import D:/penalty_docs/广告类处罚
        """
        folder = arg.strip().strip('"').strip("'")
        if not folder:
            print("  ! 请指定要导入的文件夹路径")
            return

        if not os.path.isdir(folder):
            print(f"  ! 文件夹不存在: {folder}")
            return

        try:
            result = self.importer.import_folder_interactive_v2(folder)
            if not result.get("success", False):
                print(f"  ! {result.get('message', '导入失败')}")
            else:
                print(f"\n  ✓ 导入完成：成功 {result.get('imported', 0)} 个，失败 {result.get('failed', 0)} 个")
        except KeyboardInterrupt:
            print("\n  ! 导入已取消")
        except Exception as e:
            import traceback
            print(f"  ! 导入过程出错: {e}")
            traceback.print_exc()

    # ============ list 命令 ============
    def do_list(self, arg: str):
        """列出所有案例：list [-n 数量] [--sort 字段] [--order 方向]

选项：
  -n, --limit <数量>      返回数量上限（默认100）
      --sort <字段>       排序字段：date/amount/created
      --order <方向>      排序方向：asc/desc

示例：
  list
  list -n 20 --sort amount --order desc
        """
        args = self._parse_list_args(arg)

        results = self.searcher.search(
            keywords=[],
            sort_by=args["sort_by"],
            sort_order=args["sort_order"],
            limit=args["limit"]
        )

        self._last_results = results
        self._last_keywords = []

        output = self.searcher.format_results_table(results, show_snippets=False)
        print(output)

    def _parse_list_args(self, arg_str: str) -> dict:
        """解析list命令参数"""
        parts = arg_str.split()
        limit = 100
        sort_by = "penalty_date"
        sort_order = "desc"

        i = 0
        while i < len(parts):
            p = parts[i]
            if p in ("-n", "--limit") and i + 1 < len(parts):
                try:
                    limit = int(parts[i + 1])
                except ValueError:
                    pass
                i += 2
            elif p == "--sort" and i + 1 < len(parts):
                sort_map = {
                    "date": "penalty_date", "amount": "penalty_amount",
                    "created": "created_at", "company": "company"
                }
                sort_by = sort_map.get(parts[i + 1].lower(), "penalty_date")
                i += 2
            elif p == "--order" and i + 1 < len(parts):
                sort_order = parts[i + 1].lower()
                i += 2
            else:
                i += 1

        return {"limit": limit, "sort_by": sort_by, "sort_order": sort_order}

    # ============ view 命令 ============
    def do_view(self, arg: str):
        """查看案例详情：view <编号> 或 view <案例编号>

示例：
  view 1           （查看上次搜索/列表中第1条）
  view TECH-2024-0001  （按案例号查看）
        """
        target = arg.strip()
        if not target:
            print("  ! 请指定要查看的编号或案例号")
            return

        case_id = None
        try:
            idx = int(target)
            if 1 <= idx <= len(self._last_results):
                case_id = self._last_results[idx - 1]["id"]
            else:
                print(f"  ! 编号超出范围 (当前有 {len(self._last_results)} 条结果)")
                return
        except ValueError:
            case = self.db.get_case_by_no(target)
            if case:
                case_id = case["id"]
            else:
                print(f"  ! 未找到案例: {target}")
                return

        output = self.searcher.format_case_detail(case_id, highlight=self._last_keywords)
        print(output)

    # ============ export 命令 ============
    def do_export(self, arg: str):
        """导出案例：export <编号列表> [选项]

编号格式：1   1,3,5   2-6   CASE-001,CASE-002

选项：
  -f, --format <格式>     导出格式：md（默认）、txt、json
  -o, --output <路径>     输出文件路径（自动生成可不填）
  -t, --title <标题>      文档标题
      --template <模板>   导出模板：
                            lawyer  律师版（事实+申辩+整改+话术，详细）
                            business 业务版（事实+处理+话术，精简）
                            full    完整版（默认，含全部可导出字段）

示例：
  export 1,3,5
  export 2-4 --template business -f txt -o ./业务参考.txt
  export CASE-2024-001 --template lawyer -t "律师审阅参考"
        """
        args = self._parse_export_args(arg)
        if not args["selection"]:
            print("  ! 请指定要导出的案例编号（输入 'help export' 查看用法）")
            return

        case_ids, errors = self.searcher.get_case_ids_from_selection(
            args["selection"], self._last_results
        )

        if errors:
            for err in errors:
                print(f"  ! {err}")

        if not case_ids:
            print("  ! 没有可导出的有效案例")
            return

        fmt = args["format"].lower()
        if fmt not in ["md", "txt", "json"]:
            print(f"  ! 不支持的格式: {fmt} (支持: md, txt, json)")
            return

        template = args.get("template", "full")
        if template not in ["full", "lawyer", "business"]:
            print(f"  ! 不支持的模板: {template} (支持: full, lawyer, business)")
            return

        try:
            if args["output"]:
                output_path = args["output"]
            else:
                prefix = f"penalty_{template}" if template != "full" else "penalty_cases"
                output_path = self.exporter.auto_export_path(format_type=fmt, prefix=prefix)

            if fmt == "md":
                result_path = self.exporter.export_to_markdown(
                    case_ids, output_path,
                    title=args["title"],
                    template=template
                )
            elif fmt == "txt":
                result_path = self.exporter.export_to_text(
                    case_ids, output_path,
                    title=args["title"],
                    template=template
                )
            else:
                result_path = self.exporter.export_to_json(
                    case_ids, output_path,
                    template=template
                )

            template_names = {"full": "完整版", "lawyer": "律师版", "business": "业务版"}
            print(f"  ✓ 已导出 {len(case_ids)} 个案例 [{template_names.get(template, template)}]")
            print(f"  ✓ 文件路径: {result_path}")

        except Exception as e:
            import traceback
            print(f"  ! 导出失败: {e}")
            traceback.print_exc()

    def _parse_export_args(self, arg_str: str) -> dict:
        """解析export命令参数"""
        parts = arg_str.split()
        selection_parts = []
        fmt = "md"
        output = None
        title = None
        template = "full"

        i = 0
        while i < len(parts):
            p = parts[i]
            if p in ("-f", "--format") and i + 1 < len(parts):
                fmt = parts[i + 1]
                i += 2
            elif p in ("-o", "--output") and i + 1 < len(parts):
                output = parts[i + 1].strip('"').strip("'")
                i += 2
            elif p in ("-t", "--title") and i + 1 < len(parts):
                title_parts = []
                i += 1
                while i < len(parts) and not parts[i].startswith("-"):
                    title_parts.append(parts[i])
                    i += 1
                title = " ".join(title_parts) if title_parts else None
            elif p == "--template" and i + 1 < len(parts):
                template = parts[i + 1].lower()
                i += 2
            elif not p.startswith("-") and not selection_parts:
                while i < len(parts) and not parts[i].startswith("-"):
                    selection_parts.append(parts[i])
                    i += 1
            else:
                i += 1

        return {
            "selection": " ".join(selection_parts),
            "format": fmt,
            "output": output,
            "title": title,
            "template": template
        }

    # ============ stats 命令 ============
    def do_stats(self, arg: str):
        """查看数据库统计信息"""
        stats = self.db.get_stats()
        companies = self.db.list_companies()
        regulators = self.db.list_regulators()
        business_lines = self.db.list_business_lines()
        tags = self.db.list_tags()

        print()
        print("=" * 60)
        print("  数据库统计信息")
        print("=" * 60)
        print(f"  案例总数     : {stats['total_cases']} 个")
        print(f"  累计处罚金额 : {format_amount(stats['total_penalty_amount'])}")
        print(f"  涉及公司     : {stats['company_count']} 家")
        print(f"  监管部门     : {stats['regulator_count']} 个")
        print()

        if companies:
            print("  ┌ 公司列表")
            for c in companies:
                print(f"  │  • {c}")
            print("  └")
        if regulators:
            print("  ┌ 监管部门列表")
            for r in regulators:
                print(f"  │  • {r}")
            print("  └")
        if business_lines:
            print("  ┌ 业务线列表")
            for b in business_lines:
                print(f"  │  • {b}")
            print("  └")
        if tags:
            print("  ┌ 标签列表")
            tag_str = ", ".join(tags)
            print(f"  │  {tag_str}")
            print("  └")
        print("=" * 60)

    # ============ delete 命令 ============
    def do_delete(self, arg: str):
        """删除案例：delete <编号> （需要二次确认）

示例：
  delete 5
        """
        target = arg.strip()
        if not target:
            print("  ! 请指定要删除的编号")
            return

        case_id = None
        case_no = ""
        try:
            idx = int(target)
            if 1 <= idx <= len(self._last_results):
                case_id = self._last_results[idx - 1]["id"]
                case_no = self._last_results[idx - 1].get("case_no", "")
            else:
                print(f"  ! 编号超出范围")
                return
        except ValueError:
            case = self.db.get_case_by_no(target)
            if case:
                case_id = case["id"]
                case_no = case.get("case_no", "")
            else:
                print(f"  ! 未找到案例: {target}")
                return

        confirm = input(f"  ? 确认删除案例 {case_no}？此操作不可恢复 (yes/N): ").strip().lower()
        if confirm == "yes":
            if self.db.delete_case(case_id):
                print(f"  ✓ 案例 {case_no} 已删除")
                self._last_results = [r for r in self._last_results if r.get("id") != case_id]
            else:
                print(f"  ! 删除失败")
        else:
            print("  已取消删除")

    # ============ 退出命令 ============
    def do_quit(self, arg: str):
        """退出工具"""
        print("\n感谢使用，再见！")
        return True

    def do_exit(self, arg: str):
        """退出工具"""
        return self.do_quit(arg)

    def do_EOF(self, arg: str):
        """Ctrl+D退出"""
        print()
        return self.do_quit(arg)

    def emptyline(self):
        """空行不执行任何操作"""
        pass

    def default(self, line: str):
        """默认处理 - 自动识别数字编号作为view命令"""
        line = line.strip()
        try:
            idx = int(line)
            return self.do_view(line)
        except ValueError:
            print(f"  ! 未知命令: {line}（输入 help 查看命令列表）")


def build_arg_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        prog="penalty-retrieval",
        description="监管处罚应对命令行检索工具 - 供法务人员快速查询内部处罚口径",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例：
  python main.py                          # 启动交互式模式
  python main.py search "广告绝对化用语"   # 直接搜索
  python main.py import ./cases_folder    # 直接导入
  python main.py export 1,3 -o out.md     # 直接导出
        """
    )

    parser.add_argument("-d", "--db", help="指定数据库文件路径", default=None)

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    subparsers.add_parser("shell", help="启动交互式命令行（默认模式）")

    # search
    search_parser = subparsers.add_parser("search", help="搜索案例")
    search_parser.add_argument("keywords", nargs="+", help="搜索关键词")
    search_parser.add_argument("-c", "--company", help="按公司过滤")
    search_parser.add_argument("-r", "--regulator", help="按监管部门过滤")
    search_parser.add_argument("-b", "--business", help="按业务线过滤")
    search_parser.add_argument("-t", "--tags", help="按标签过滤（逗号分隔）")
    search_parser.add_argument("--min-amount", help="最低处罚金额（元）")
    search_parser.add_argument("--max-amount", help="最高处罚金额（元）")
    search_parser.add_argument("--from-date", help="起始日期 YYYY-MM-DD")
    search_parser.add_argument("--to-date", help="结束日期 YYYY-MM-DD")
    search_parser.add_argument("--sort", default="date",
                               choices=["date", "amount", "created", "company"],
                               help="排序字段（默认date）")
    search_parser.add_argument("--order", default="desc", choices=["asc", "desc"],
                               help="排序方向（默认desc）")
    search_parser.add_argument("-n", "--limit", type=int, default=50, help="结果数量上限")

    # import
    import_parser = subparsers.add_parser("import", help="导入文档")
    import_parser.add_argument("folder", help="包含文档的文件夹路径")

    # list
    list_parser = subparsers.add_parser("list", help="列出所有案例")
    list_parser.add_argument("-n", "--limit", type=int, default=100, help="数量上限")
    list_parser.add_argument("--sort", default="date",
                             choices=["date", "amount", "created", "company"],
                             help="排序字段")
    list_parser.add_argument("--order", default="desc", choices=["asc", "desc"],
                             help="排序方向")

    # view
    view_parser = subparsers.add_parser("view", help="查看案例详情")
    view_parser.add_argument("target", help="编号或案例号")

    # export
    export_parser = subparsers.add_parser("export", help="导出案例")
    export_parser.add_argument("selection", help="案例编号（如 1,3 或 2-5 或 CASE001）")
    export_parser.add_argument("-f", "--format", default="md",
                               choices=["md", "txt", "json"], help="导出格式（默认md）")
    export_parser.add_argument("-o", "--output", help="输出文件路径")
    export_parser.add_argument("-t", "--title", help="文档标题")
    export_parser.add_argument("--template", default="full",
                               choices=["full", "lawyer", "business"],
                               help="导出模板（默认full完整版）")

    # stats
    subparsers.add_parser("stats", help="查看数据库统计")

    return parser


def _parse_amount_arg(amount_str: str) -> Optional[float]:
    """解析金额参数"""
    if not amount_str:
        return None
    amount_str = amount_str.strip().replace(",", "").replace("元", "")
    try:
        if amount_str.endswith("万"):
            return float(amount_str[:-1]) * 10000
        return float(amount_str)
    except ValueError:
        return None


def _normalize_date_arg(date_str: str) -> Optional[str]:
    """标准化日期参数"""
    if not date_str:
        return None
    import re
    m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", date_str.strip())
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return date_str


def run_cli():
    """运行命令行界面"""
    parser = build_arg_parser()
    args = parser.parse_args()

    db_path = args.db
    command = args.command or "shell"

    sort_map = {
        "date": "penalty_date", "amount": "penalty_amount",
        "created": "created_at", "company": "company"
    }

    if command == "shell":
        shell = PenaltyShell(db_path)
        try:
            shell.cmdloop()
        except KeyboardInterrupt:
            print("\n\n感谢使用，再见！")

    elif command == "search":
        searcher = CaseSearcher(db_path=db_path)
        tags = parse_input_list(args.tags) if args.tags else []

        results = searcher.search(
            keywords=args.keywords,
            company=args.company,
            regulator=args.regulator,
            business_line=args.business,
            tags=tags,
            min_amount=_parse_amount_arg(args.min_amount),
            max_amount=_parse_amount_arg(args.max_amount),
            from_date=_normalize_date_arg(args.from_date),
            to_date=_normalize_date_arg(args.to_date),
            sort_by=sort_map.get(args.sort, "penalty_date"),
            sort_order=args.order,
            limit=args.limit
        )
        output = searcher.format_results_table(results, highlight=args.keywords)
        print(output)

    elif command == "import":
        importer = DocumentImporter(db_path=db_path)
        folder = args.folder.strip().strip('"').strip("'")
        if not os.path.isdir(folder):
            print(f"错误：文件夹不存在: {folder}")
            sys.exit(1)
        result = importer.import_folder_interactive_v2(folder)
        if not result.get("success", False):
            print(f"错误：{result.get('message', '导入失败')}")
            sys.exit(1)

    elif command == "list":
        searcher = CaseSearcher(db_path=db_path)
        results = searcher.search(
            keywords=[],
            sort_by=sort_map.get(args.sort, "penalty_date"),
            sort_order=args.order,
            limit=args.limit
        )
        output = searcher.format_results_table(results, show_snippets=False)
        print(output)

    elif command == "view":
        db = PenaltyDatabase(db_path)
        searcher = CaseSearcher(db)
        target = args.target
        case = db.get_case_by_no(target)
        if case:
            output = searcher.format_case_detail(case["id"])
            print(output)
        else:
            print(f"错误：未找到案例 {target}")
            sys.exit(1)

    elif command == "export":
        db = PenaltyDatabase(db_path)
        exporter = CaseExporter(db)
        searcher = CaseSearcher(db)

        results = db.list_all_cases(limit=10000)
        case_ids, errors = searcher.get_case_ids_from_selection(args.selection, results)

        if errors:
            for err in errors:
                print(f"警告：{err}", file=sys.stderr)

        if not case_ids:
            print("错误：没有可导出的有效案例")
            sys.exit(1)

        fmt = args.format
        if args.output:
            output_path = args.output
        else:
            prefix = f"penalty_{args.template}" if args.template != "full" else "penalty_cases"
            output_path = exporter.auto_export_path(format_type=fmt, prefix=prefix)

        try:
            if fmt == "md":
                result_path = exporter.export_to_markdown(
                    case_ids, output_path,
                    title=args.title,
                    template=args.template
                )
            elif fmt == "txt":
                result_path = exporter.export_to_text(
                    case_ids, output_path,
                    title=args.title,
                    template=args.template
                )
            else:
                result_path = exporter.export_to_json(
                    case_ids, output_path,
                    template=args.template
                )

            print(f"已导出 {len(case_ids)} 个案例: {result_path}")
        except Exception as e:
            print(f"错误：导出失败 - {e}")
            sys.exit(1)

    elif command == "stats":
        db = PenaltyDatabase(db_path)
        stats = db.get_stats()
        print(f"案例总数: {stats['total_cases']}")
        print(f"累计金额: {format_amount(stats['total_penalty_amount'])}")
        print(f"涉及公司: {stats['company_count']} 家")
        print(f"监管部门: {stats['regulator_count']} 个")
        companies = db.list_companies()
        if companies:
            print(f"公司列表: {', '.join(companies)}")
        tags = db.list_tags()
        if tags:
            print(f"标签列表: {', '.join(tags)}")


if __name__ == "__main__":
    run_cli()
