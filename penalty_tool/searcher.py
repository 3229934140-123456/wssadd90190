"""搜索模块 - 支持多关键词搜索、结果展示和高亮"""

from typing import List, Dict, Optional, Tuple
from .database import PenaltyDatabase
from .utils import parse_input_list, format_amount


class CaseSearcher:
    """案例搜索器"""

    def __init__(self, db: Optional[PenaltyDatabase] = None, db_path: Optional[str] = None):
        self.db = db or PenaltyDatabase(db_path)

    def search(self,
               keywords: Optional[List[str]] = None,
               keyword_str: Optional[str] = None,
               company: Optional[str] = None,
               regulator: Optional[str] = None,
               business_line: Optional[str] = None,
               tag: Optional[str] = None,
               limit: int = 50) -> List[Dict]:
        """
        搜索案例

        Args:
            keywords: 关键词列表（AND关系）
            keyword_str: 关键词字符串，会自动解析为列表
            company: 按公司过滤
            regulator: 按监管部门过滤
            business_line: 按业务线过滤
            tag: 按标签过滤
            limit: 返回结果数上限
        """
        if keyword_str:
            keywords = parse_input_list(keyword_str)

        keywords = keywords or []

        results = self.db.search_keywords(
            keywords=keywords,
            company=company,
            regulator=regulator,
            business_line=business_line,
            tag=tag,
            limit=limit
        )

        for item in results:
            item["penalty_amount_formatted"] = format_amount(item.get("penalty_amount", 0))

        return results

    def format_results_table(self, results: List[Dict], highlight: Optional[List[str]] = None) -> str:
        """格式化搜索结果为表格显示"""
        if not results:
            return "未找到匹配的案例。请尝试调整关键词或过滤条件。"

        lines = []
        lines.append("=" * 100)
        lines.append(f"  共找到 {len(results)} 个匹配案例")
        lines.append("=" * 100)

        for idx, item in enumerate(results, 1):
            lines.append("")
            lines.append(f"  [{idx:>3}]  案例编号: {item.get('case_no', 'N/A')}")
            lines.append(f"         所属公司: {item.get('company', '')}")
            lines.append(f"         监管部门: {item.get('regulator', '')}")

            if item.get("business_line"):
                lines.append(f"         业务线  : {item['business_line']}")

            if item.get("tags"):
                tags_str = ", ".join(item["tags"])
                lines.append(f"         标签    : {tags_str}")

            lines.append(f"         处罚日期: {item.get('penalty_date', '未知')}")
            lines.append(f"         处罚金额: {item.get('penalty_amount_formatted', '0元')}")

            summary = item.get("result_summary", "") or item.get("facts", "")
            if summary:
                if highlight:
                    summary = self._highlight_text(summary, highlight)
                summary_display = (summary[:200] + "...") if len(summary) > 200 else summary
                lines.append(f"         摘要    : {summary_display}")

            lines.append("  " + "-" * 96)

        lines.append("\n  提示: 使用 'view <编号>' 查看详情，使用 'export <编号1,编号2...>' 导出")

        return "\n".join(lines)

    def format_case_detail(self, case_id: int, highlight: Optional[List[str]] = None) -> str:
        """格式化单个案例的详细信息"""
        case = self.db.get_case_by_id(case_id)
        if not case:
            return f"未找到ID为 {case_id} 的案例"

        lines = []
        lines.append("=" * 100)
        lines.append("  案例详情")
        lines.append("=" * 100)
        lines.append(f"  案例编号   : {case.get('case_no', 'N/A')}")
        lines.append(f"  所属公司   : {case.get('company', '')}")
        lines.append(f"  监管部门   : {case.get('regulator', '')}")
        lines.append(f"  业务线     : {case.get('business_line', '未分类')}")

        tags = case.get("tags", [])
        if tags:
            lines.append(f"  标签       : {', '.join(tags)}")

        lines.append(f"  处罚日期   : {case.get('penalty_date', '未知')}")
        lines.append(f"  处罚金额   : {format_amount(case.get('penalty_amount', 0))}")

        if case.get("result_summary"):
            summary = case["result_summary"]
            if highlight:
                summary = self._highlight_text(summary, highlight)
            lines.append("")
            lines.append("  ┌─ 处理结果 ────────────────────────────────────────────────────────┐")
            lines.append(self._wrap_text(summary, 68, "  │ "))
            lines.append("  └───────────────────────────────────────────────────────────────────┘")

        if case.get("facts"):
            facts = case["facts"]
            if highlight:
                facts = self._highlight_text(facts, highlight)
            lines.append("")
            lines.append("  ┌─ 违法事实 ────────────────────────────────────────────────────────┐")
            lines.append(self._wrap_text(facts[:2000], 68, "  │ "))
            if len(facts) > 2000:
                lines.append("  │ ... (内容已截断)")
            lines.append("  └───────────────────────────────────────────────────────────────────┘")

        if case.get("defense_content"):
            lines.append("")
            lines.append("  ┌─ 申辩意见 ────────────────────────────────────────────────────────┐")
            lines.append(self._wrap_text(case["defense_content"][:2000], 68, "  │ "))
            if len(case["defense_content"]) > 2000:
                lines.append("  │ ... (内容已截断)")
            lines.append("  └───────────────────────────────────────────────────────────────────┘")

        if case.get("rectification_report"):
            lines.append("")
            lines.append("  ┌─ 整改报告 ────────────────────────────────────────────────────────┐")
            lines.append(self._wrap_text(case["rectification_report"][:2000], 68, "  │ "))
            if len(case["rectification_report"]) > 2000:
                lines.append("  │ ... (内容已截断)")
            lines.append("  └───────────────────────────────────────────────────────────────────┘")

        if case.get("reference_script"):
            lines.append("")
            lines.append("  ┌─ 可借鉴话术 ──────────────────────────────────────────────────────┐")
            lines.append(self._wrap_text(case["reference_script"], 68, "  │ "))
            lines.append("  └───────────────────────────────────────────────────────────────────┘")

        if case.get("source_files"):
            lines.append("")
            lines.append(f"  来源文件  : {', '.join(case['source_files'])}")

        lines.append(f"  创建时间   : {case.get('created_at', '')}")
        lines.append("=" * 100)

        return "\n".join(lines)

    def _highlight_text(self, text: str, keywords: List[str]) -> str:
        """简单文本高亮（使用大写标记或特殊符号）"""
        import re
        result = text
        for kw in keywords:
            if not kw:
                continue
            pattern = re.compile(re.escape(kw), re.IGNORECASE)
            result = pattern.sub(lambda m: f"【{m.group()}】", result)
        return result

    def _wrap_text(self, text: str, width: int, prefix: str = "") -> str:
        """文本换行格式化"""
        lines = []
        paragraphs = text.split("\n")
        for para in paragraphs:
            if not para.strip():
                lines.append(prefix.rstrip())
                continue

            current = ""
            for char in para:
                if len(current) >= width:
                    lines.append(prefix + current)
                    current = ""
                current += char
            if current:
                lines.append(prefix + current)

        return "\n".join(lines)

    def get_case_ids_from_selection(self, selection_str: str, search_results: List[Dict]) -> Tuple[List[int], List[str]]:
        """
        从选择字符串中解析案例ID列表

        Args:
            selection_str: 选择字符串，如 "1,3,5-8" 或 "CASE001,CASE003"
            search_results: 当前搜索结果列表（用于编号到ID的映射）

        Returns:
            (案例ID列表, 错误信息列表)
        """
        errors = []
        ids = []
        no_to_id = {item["case_no"]: item["id"] for item in search_results}

        parts = [p.strip() for p in selection_str.replace("，", ",").split(",") if p.strip()]

        for part in parts:
            if "-" in part and not part.startswith("-"):
                try:
                    start_str, end_str = part.split("-", 1)
                    start = int(start_str)
                    end = int(end_str)
                    if start > end:
                        start, end = end, start
                    for num in range(start, end + 1):
                        if 1 <= num <= len(search_results):
                            ids.append(search_results[num - 1]["id"])
                        else:
                            errors.append(f"编号超出范围: {num}")
                except ValueError:
                    if part in no_to_id:
                        ids.append(no_to_id[part])
                    else:
                        errors.append(f"无效的编号范围: {part}")
            else:
                try:
                    num = int(part)
                    if 1 <= num <= len(search_results):
                        ids.append(search_results[num - 1]["id"])
                    else:
                        errors.append(f"编号超出范围: {num}")
                except ValueError:
                    if part in no_to_id:
                        ids.append(no_to_id[part])
                    else:
                        case = self.db.get_case_by_no(part)
                        if case:
                            ids.append(case["id"])
                        else:
                            errors.append(f"未找到案例: {part}")

        unique_ids = list(dict.fromkeys(ids))
        return unique_ids, errors
