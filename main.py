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
║       监管处罚应对命令行检索工具 v3.0                          ║
║       Penalty Retrieval CLI                                    ║
╠══════════════════════════════════════════════════════════════╣
║  常用命令：                                                     ║
║    search [关键词]     - 搜索案例（可纯筛选，不输入关键词）     ║
║    import <文件夹>     - 批量导入处罚文档（智能分组+预览）      ║
║    list                - 列出所有案例                           ║
║    view <编号>         - 查看案例详情                           ║
║    export <编号...>    - 导出参考清单（律师/业务/对比）          ║
║    check               - 资料库健康检查                        ║
║    stats               - 查看数据库统计                        ║
║    help <命令>         - 查看命令详细帮助                       ║
║    quit / exit         - 退出工具                               ║
╠══════════════════════════════════════════════════════════════╣
║  高级搜索示例：                                                 ║
║    search --min 10万 --max 50万 -r 市监局                      ║
║    search 广告 --from 2024-01-01 --save 广告类案件              ║
║    search --use 广告类案件                                      ║
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
        """搜索案例：search [关键词1 关键词2 ...] [选项]

不输入关键词时，可纯靠筛选条件返回结果。
支持保存和调用常用检索条件。

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
      --save <名称>          将本次检索条件保存为命名预设
      --use <名称>           调用已保存的检索条件
      --list-presets         列出所有已保存的检索条件
      --delete-preset <名称> 删除已保存的检索条件

示例：
  search                                    # 无条件，列出全部
  search --min 10万 --max 50万 -r 市监局     # 纯筛选
  search 广告绝对化用语
  search 个人信息 -t 数据合规 --save 数据合规案件
  search --use 数据合规案件
        """
        args = self._parse_search_args(arg)

        if args.get("list_presets"):
            self._show_saved_searches()
            return

        if args.get("delete_preset"):
            name = args["delete_preset"]
            if self.db.delete_saved_search(name):
                print(f"  ✓ 已删除检索预设 '{name}'")
            else:
                print(f"  ! 未找到检索预设 '{name}'")
            return

        if args.get("use_preset"):
            preset = self.db.load_search(args["use_preset"])
            if not preset:
                print(f"  ! 未找到检索预设 '{args['use_preset']}'")
                return
            self._apply_preset(preset, args)

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

        if args.get("save"):
            self._save_current_search(args)

        output = self.searcher.format_results_table(
            results, highlight=args["keywords"], show_snippets=True
        )
        print(output)

    def _apply_preset(self, preset: dict, args: dict):
        """将保存的检索条件合并到当前参数中（当前参数优先）"""
        if not args["keywords"] and preset.get("keywords"):
            args["keywords"] = preset["keywords"]
        if not args["company"] and preset.get("company"):
            args["company"] = preset["company"]
        if not args["regulator"] and preset.get("regulator"):
            args["regulator"] = preset["regulator"]
        if not args["business_line"] and preset.get("business_line"):
            args["business_line"] = preset["business_line"]
        if not args["tags"] and preset.get("tags"):
            args["tags"] = preset["tags"]
        if args["min_amount"] is None and preset.get("min_amount") is not None:
            args["min_amount"] = preset["min_amount"]
        if args["max_amount"] is None and preset.get("max_amount") is not None:
            args["max_amount"] = preset["max_amount"]
        if not args["from_date"] and preset.get("from_date"):
            args["from_date"] = preset["from_date"]
        if not args["to_date"] and preset.get("to_date"):
            args["to_date"] = preset["to_date"]
        print(f"  ✓ 已加载检索预设，条件已合并")

    def _save_current_search(self, args: dict):
        """保存当前检索条件"""
        name = args["save"]
        ok, msg = self.db.save_search(
            name=name,
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
        )
        print(f"  {msg}")

    def _show_saved_searches(self):
        """列出所有已保存的检索条件"""
        presets = self.db.list_saved_searches()
        if not presets:
            print("  暂无保存的检索条件")
            return

        print()
        print("=" * 60)
        print("  已保存的检索条件")
        print("=" * 60)
        for p in presets:
            parts = []
            if p.get("keywords"):
                parts.append(f"关键词: {' '.join(p['keywords'])}")
            if p.get("company"):
                parts.append(f"公司: {p['company']}")
            if p.get("regulator"):
                parts.append(f"部门: {p['regulator']}")
            if p.get("business_line"):
                parts.append(f"业务线: {p['business_line']}")
            if p.get("tags"):
                parts.append(f"标签: {','.join(p['tags'])}")
            if p.get("min_amount") is not None:
                parts.append(f"最低金额: {p['min_amount']}")
            if p.get("max_amount") is not None:
                parts.append(f"最高金额: {p['max_amount']}")
            if p.get("from_date"):
                parts.append(f"起始日期: {p['from_date']}")
            if p.get("to_date"):
                parts.append(f"结束日期: {p['to_date']}")

            desc = p.get("description", "")
            print(f"\n  [{p['name']}]")
            if desc:
                print(f"    说明: {desc}")
            print(f"    条件: {' | '.join(parts) if parts else '无条件'}")
            print(f"    创建: {p.get('created_at', '')}")
        print()
        print("=" * 60)

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
        save_name = use_preset = delete_preset = None
        list_presets = False

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
            elif p == "--save" and i + 1 < len(parts):
                save_name = parts[i + 1]
                i += 2
            elif p == "--use" and i + 1 < len(parts):
                use_preset = parts[i + 1]
                i += 2
            elif p == "--list-presets":
                list_presets = True
                i += 1
            elif p == "--delete-preset" and i + 1 < len(parts):
                delete_preset = parts[i + 1]
                i += 2
            elif not p.startswith("-"):
                keywords.append(p)
                i += 1
            else:
                i += 1

        has_filters = any([
            company, regulator, business_line, tags,
            min_amount is not None, max_amount is not None,
            from_date, to_date
        ])

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
            "limit": limit,
            "save": save_name,
            "use_preset": use_preset,
            "delete_preset": delete_preset,
            "list_presets": list_presets,
        }

    def _parse_amount(self, amount_str: str) -> Optional[float]:
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
支持分组预览和调整，每个分组可单独补信息。

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
                            lawyer    律师版（事实+申辩+整改+话术，详细）
                            business  业务版（事实+处理+话术，精简）
                            full      完整版（默认，含全部可导出字段）
                            compare   对比清单（多案例横向对比）

示例：
  export 1,3,5
  export 2-4 --template business -f txt -o ./业务参考.txt
  export 1,2,3 --template compare -o ./对比分析.md
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
        valid_templates = ["full", "lawyer", "business", "compare"]
        if template not in valid_templates:
            print(f"  ! 不支持的模板: {template} (支持: {', '.join(valid_templates)})")
            return

        if template == "compare" and len(case_ids) < 2:
            print("  ! 对比清单需要至少2个案例")
            return

        try:
            if args["output"]:
                output_path = args["output"]
            else:
                prefix = f"penalty_{template}" if template != "full" else "penalty_cases"
                output_path = self.exporter.auto_export_path(format_type=fmt, prefix=prefix)

            if template == "compare":
                result_path = self.exporter.export_comparison(
                    case_ids, output_path,
                    title=args.get("title"),
                    format_type=fmt
                )
            elif fmt == "md":
                result_path = self.exporter.export_to_markdown(
                    case_ids, output_path,
                    title=args.get("title"),
                    template=template
                )
            elif fmt == "txt":
                result_path = self.exporter.export_to_text(
                    case_ids, output_path,
                    title=args.get("title"),
                    template=template
                )
            else:
                result_path = self.exporter.export_to_json(
                    case_ids, output_path,
                    template=template
                )

            template_names = {"full": "完整版", "lawyer": "律师版",
                              "business": "业务版", "compare": "对比清单"}
            print(f"  ✓ 已导出 {len(case_ids)} 个案例 [{template_names.get(template, template)}]")
            print(f"  ✓ 文件路径: {result_path}")

        except Exception as e:
            import traceback
            print(f"  ! 导出失败: {e}")
            traceback.print_exc()

    def _parse_export_args(self, arg_str: str) -> dict:
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

    # ============ check 命令（资料库健康检查） ============
    def do_check(self, arg: str):
        """资料库健康检查：check [选项]

检查资料库中缺失关键字段的案例，帮助发现数据空白。

选项：
  -o, --output <路径>     将检查结果导出为文件（支持.md/.txt/.json）
  -f, --fix               交互式修复缺失字段

示例：
  check
  check -o ./数据质量检查.md
  check -f
        """
        issues = self.db.health_check()
        summary = issues["summary"]

        print()
        print("=" * 60)
        print("  资料库健康检查报告")
        print("=" * 60)
        print(f"  案例总数: {summary['total_cases']}")
        print()

        categories = [
            ("缺失处罚日期", "missing_date", "missing_date_count"),
            ("缺失处罚金额", "missing_amount", "missing_amount_count"),
            ("缺失事实正文", "missing_facts", "missing_facts_count"),
            ("缺失标签", "missing_tags", "missing_tags_count"),
        ]

        has_issues = False
        for label, key, count_key in categories:
            count = summary[count_key]
            if count > 0:
                has_issues = True
                print(f"  ⚠ {label}: {count} 个案例")
                for item in issues[key][:10]:
                    print(f"      - [{item.get('case_no', '')}] {item.get('company', '')} / {item.get('regulator', '')}")
                if count > 10:
                    print(f"      ... 还有 {count - 10} 个")
                print()

        if not has_issues:
            print("  ✓ 所有案例数据完整，未发现缺失字段")
        print("=" * 60)

        # 导出选项
        parts = arg.strip().split()
        output_path = None
        fix_mode = False

        i = 0
        while i < len(parts):
            p = parts[i]
            if p in ("-o", "--output") and i + 1 < len(parts):
                output_path = parts[i + 1]
                i += 2
            elif p in ("-f", "--fix"):
                fix_mode = True
                i += 1
            else:
                i += 1

        if output_path:
            self._export_check_results(issues, output_path)

        if fix_mode and has_issues:
            self._interactive_fix_issues(issues)

    def _export_check_results(self, issues: dict, output_path: str):
        """导出健康检查结果"""
        try:
            ext = os.path.splitext(output_path)[1].lower()
            summary = issues["summary"]

            if ext == ".json":
                import json
                export_data = {
                    "title": "资料库健康检查报告",
                    "generated_at": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "summary": summary,
                    "issues": {k: v for k, v in issues.items() if k != "summary"},
                }
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=2)
            else:
                lines = []
                lines.append("# 资料库健康检查报告")
                lines.append("")
                lines.append(f"- 案例总数: {summary['total_cases']}")
                lines.append(f"- 缺失处罚日期: {summary['missing_date_count']}")
                lines.append(f"- 缺失处罚金额: {summary['missing_amount_count']}")
                lines.append(f"- 缺失事实正文: {summary['missing_facts_count']}")
                lines.append(f"- 缺失标签: {summary['missing_tags_count']}")
                lines.append("")

                categories = [
                    ("缺失处罚日期", "missing_date"),
                    ("缺失处罚金额", "missing_amount"),
                    ("缺失事实正文", "missing_facts"),
                    ("缺失标签", "missing_tags"),
                ]

                for label, key in categories:
                    items = issues.get(key, [])
                    if items:
                        lines.append(f"## {label} ({len(items)} 个)")
                        lines.append("")
                        lines.append("| 案例编号 | 公司 | 监管部门 |")
                        lines.append("|----------|------|----------|")
                        for item in items:
                            lines.append(f"| {item.get('case_no', '')} | {item.get('company', '')} | {item.get('regulator', '')} |")
                        lines.append("")

                content = "\n".join(lines)
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(content)

            print(f"  ✓ 检查结果已导出: {os.path.abspath(output_path)}")
        except Exception as e:
            print(f"  ! 导出失败: {e}")

    def _interactive_fix_issues(self, issues: dict):
        """交互式修复缺失字段"""
        all_problem_cases = {}

        for key in ["missing_date", "missing_amount", "missing_facts", "missing_tags"]:
            for item in issues.get(key, []):
                cid = item["id"]
                if cid not in all_problem_cases:
                    all_problem_cases[cid] = {
                        "case_no": item["case_no"],
                        "company": item["company"],
                        "regulator": item["regulator"],
                        "missing": set(),
                    }
                label_map = {
                    "missing_date": "处罚日期",
                    "missing_amount": "处罚金额",
                    "missing_facts": "事实正文",
                    "missing_tags": "标签",
                }
                all_problem_cases[cid]["missing"].add(label_map[key])

        if not all_problem_cases:
            return

        print()
        print("  进入交互式修复模式（输入 q 跳过）")
        print("-" * 40)

        for cid, info in all_problem_cases.items():
            print(f"\n  [{info['case_no']}] {info['company']} / {info['regulator']}")
            print(f"    缺失: {', '.join(info['missing'])}")

            case = self.db.get_case_by_id(cid)
            if not case:
                continue

            updates = {}
            if "处罚日期" in info["missing"]:
                val = input(f"    处罚日期 (YYYY-MM-DD, 回车跳过): ").strip()
                if val.lower() == "q":
                    break
                if val:
                    updates["penalty_date"] = val

            if "处罚金额" in info["missing"]:
                val = input(f"    处罚金额 (元, 回车跳过): ").strip()
                if val.lower() == "q":
                    break
                if val:
                    try:
                        if val.endswith("万"):
                            updates["penalty_amount"] = float(val[:-1]) * 10000
                        else:
                            updates["penalty_amount"] = float(val)
                    except ValueError:
                        print("      ! 金额格式错误，跳过")

            if "事实正文" in info["missing"]:
                val = input(f"    事实正文 (回车跳过): ").strip()
                if val.lower() == "q":
                    break
                if val:
                    updates["facts"] = val

            if "标签" in info["missing"]:
                val = input(f"    标签 (逗号分隔, 回车跳过): ").strip()
                if val.lower() == "q":
                    break
                if val:
                    updates["tags"] = parse_input_list(val)

            if updates:
                self._update_case_fields(cid, updates)
                print(f"    ✓ 已更新")

    def _update_case_fields(self, case_id: int, updates: dict):
        """更新案例的部分字段"""
        import json as json_mod
        set_parts = []
        params = []

        for field, value in updates.items():
            if field == "tags":
                if isinstance(value, list):
                    tags_json = json_mod.dumps(value, ensure_ascii=False)
                    set_parts.append("tags = ?")
                    params.append(tags_json)
                    # Also update case_tags table
                    with self.db._get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM case_tags WHERE case_id = ?", (case_id,))
                        for tag in value:
                            cursor.execute("INSERT INTO case_tags (case_id, tag) VALUES (?, ?)", (case_id, tag))
                        conn.commit()
                continue
            set_parts.append(f"{field} = ?")
            params.append(value)

        if not set_parts:
            return

        set_parts.append("updated_at = ?")
        params.append(__import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        params.append(case_id)

        sql = f"UPDATE penalties SET {', '.join(set_parts)} WHERE id = ?"
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()

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
        pass

    def default(self, line: str):
        line = line.strip()
        try:
            idx = int(line)
            return self.do_view(line)
        except ValueError:
            print(f"  ! 未知命令: {line}（输入 help 查看命令列表）")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="penalty-retrieval",
        description="监管处罚应对命令行检索工具 - 供法务人员快速查询内部处罚口径",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例：
  python main.py                          # 启动交互式模式
  python main.py search "广告绝对化用语"   # 直接搜索
  python main.py search --min 10万 -r 市监局  # 纯筛选搜索
  python main.py import ./cases_folder    # 直接导入
  python main.py export 1,3 -o out.md     # 直接导出
  python main.py check                    # 资料库健康检查
        """
    )

    parser.add_argument("-d", "--db", help="指定数据库文件路径", default=None)

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    subparsers.add_parser("shell", help="启动交互式命令行（默认模式）")

    search_parser = subparsers.add_parser("search", help="搜索案例")
    search_parser.add_argument("keywords", nargs="*", help="搜索关键词（可选）")
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
    search_parser.add_argument("--save", help="保存本次检索条件为命名预设")
    search_parser.add_argument("--use", help="使用已保存的检索条件")
    search_parser.add_argument("--list-presets", action="store_true", help="列出已保存的检索条件")
    search_parser.add_argument("--delete-preset", help="删除已保存的检索条件")

    import_parser = subparsers.add_parser("import", help="导入文档")
    import_parser.add_argument("folder", help="包含文档的文件夹路径")

    list_parser = subparsers.add_parser("list", help="列出所有案例")
    list_parser.add_argument("-n", "--limit", type=int, default=100, help="数量上限")
    list_parser.add_argument("--sort", default="date",
                             choices=["date", "amount", "created", "company"],
                             help="排序字段")
    list_parser.add_argument("--order", default="desc", choices=["asc", "desc"],
                             help="排序方向")

    view_parser = subparsers.add_parser("view", help="查看案例详情")
    view_parser.add_argument("target", help="编号或案例号")

    export_parser = subparsers.add_parser("export", help="导出案例")
    export_parser.add_argument("selection", help="案例编号（如 1,3 或 2-5 或 CASE001）")
    export_parser.add_argument("-f", "--format", default="md",
                               choices=["md", "txt", "json"], help="导出格式（默认md）")
    export_parser.add_argument("-o", "--output", help="输出文件路径")
    export_parser.add_argument("-t", "--title", help="文档标题")
    export_parser.add_argument("--template", default="full",
                               choices=["full", "lawyer", "business", "compare"],
                               help="导出模板（默认full完整版）")

    subparsers.add_parser("stats", help="查看数据库统计")

    check_parser = subparsers.add_parser("check", help="资料库健康检查")
    check_parser.add_argument("-o", "--output", help="导出检查结果文件路径")
    check_parser.add_argument("-f", "--fix", action="store_true", help="交互式修复缺失字段")

    return parser


def _parse_amount_arg(amount_str: str) -> Optional[float]:
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
    if not date_str:
        return None
    import re
    m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", date_str.strip())
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return date_str


def run_cli():
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
        db = PenaltyDatabase(db_path)
        searcher = CaseSearcher(db)
        tags = parse_input_list(args.tags) if args.tags else []
        keywords = args.keywords or []

        if args.use:
            preset = db.load_search(args.use)
            if preset:
                if not keywords and preset.get("keywords"):
                    keywords = preset["keywords"]
                if not args.company and preset.get("company"):
                    args.company = preset["company"]
                if not args.regulator and preset.get("regulator"):
                    args.regulator = preset["regulator"]
                if not args.business and preset.get("business_line"):
                    args.business = preset["business_line"]
                if not tags and preset.get("tags"):
                    tags = preset["tags"]
                print(f"  ✓ 已加载检索预设 '{args.use}'")

        if args.list_presets:
            presets = db.list_saved_searches()
            if not presets:
                print("  暂无保存的检索条件")
            else:
                for p in presets:
                    print(f"  [{p['name']}] 创建于 {p.get('created_at', '')}")
            return

        if args.delete_preset:
            if db.delete_saved_search(args.delete_preset):
                print(f"  ✓ 已删除检索预设 '{args.delete_preset}'")
            else:
                print(f"  ! 未找到检索预设 '{args.delete_preset}'")
            return

        results = searcher.search(
            keywords=keywords,
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

        if args.save:
            db.save_search(
                name=args.save,
                keywords=keywords,
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
            )
            print(f"  ✓ 检索条件已保存为 '{args.save}'")

        output = searcher.format_results_table(results, highlight=keywords)
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
        template = args.template

        if template == "compare" and len(case_ids) < 2:
            print("错误：对比清单需要至少2个案例")
            sys.exit(1)

        if args.output:
            output_path = args.output
        else:
            prefix = f"penalty_{template}" if template != "full" else "penalty_cases"
            output_path = exporter.auto_export_path(format_type=fmt, prefix=prefix)

        try:
            if template == "compare":
                result_path = exporter.export_comparison(
                    case_ids, output_path,
                    title=args.title,
                    format_type=fmt
                )
            elif fmt == "md":
                result_path = exporter.export_to_markdown(
                    case_ids, output_path,
                    title=args.title,
                    template=template
                )
            elif fmt == "txt":
                result_path = exporter.export_to_text(
                    case_ids, output_path,
                    title=args.title,
                    template=template
                )
            else:
                result_path = exporter.export_to_json(
                    case_ids, output_path,
                    template=template
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

    elif command == "check":
        db = PenaltyDatabase(db_path)
        issues = db.health_check()
        summary = issues["summary"]

        print(f"\n资料库健康检查")
        print(f"  案例总数: {summary['total_cases']}")
        print(f"  缺失处罚日期: {summary['missing_date_count']}")
        print(f"  缺失处罚金额: {summary['missing_amount_count']}")
        print(f"  缺失事实正文: {summary['missing_facts_count']}")
        print(f"  缺失标签: {summary['missing_tags_count']}")

        if args.output:
            shell_ref = PenaltyShell(db_path)
            shell_ref._export_check_results(issues, args.output)


if __name__ == "__main__":
    run_cli()
