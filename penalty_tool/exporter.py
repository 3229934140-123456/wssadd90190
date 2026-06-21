"""导出模块 - 导出简版参考清单，自动脱敏处理"""

import os
import json
from datetime import datetime
from typing import List, Dict, Optional
from .database import PenaltyDatabase
from .utils import format_amount, mask_sensitive_info


class CaseExporter:
    """案例导出器"""

    def __init__(self, db: Optional[PenaltyDatabase] = None, db_path: Optional[str] = None):
        self.db = db or PenaltyDatabase(db_path)

    def export_to_markdown(self, case_ids: List[int], output_path: str,
                           title: Optional[str] = None) -> str:
        """
        导出为 Markdown 格式的简版参考清单

        Args:
            case_ids: 案例ID列表
            output_path: 输出文件路径
            title: 文档标题

        Returns:
            输出文件的完整路径
        """
        cases = self.db.get_cases_export(case_ids)
        if not cases:
            raise ValueError("未找到可导出的案例")

        title = title or "监管处罚案例参考清单"
        generated_at = datetime.now().strftime("%Y年%m月%d日 %H:%M")

        lines = []
        lines.append(f"# {title}")
        lines.append("")
        lines.append(f"> 生成时间：{generated_at}")
        lines.append(f"> 案例数量：{len(cases)} 个")
        lines.append(f"> 说明：本清单已脱敏处理，隐藏了内部敏感信息。")
        lines.append("")
        lines.append("---")
        lines.append("")

        lines.append("## 目录")
        lines.append("")
        for idx, case in enumerate(cases, 1):
            anchor = f"案例{idx}-{case.get('case_no', '')}"
            line = f"{idx}. [{case.get('case_no', '')} - {case.get('company', '')}](#{anchor})"
            brief = self._get_case_brief(case)
            if brief:
                line += f"：{brief}"
            lines.append(line)
        lines.append("")
        lines.append("---")
        lines.append("")

        for idx, case in enumerate(cases, 1):
            anchor = f"案例{idx}-{case.get('case_no', '')}"
            lines.append(f"## {idx}. <a id='{anchor}'></a>{case.get('case_no', '')}")
            lines.append("")

            lines.append("### 基本信息")
            lines.append("")
            lines.append(f"- **所属公司**：{self._sanitize(case.get('company', ''))}")
            lines.append(f"- **监管部门**：{self._sanitize(case.get('regulator', ''))}")
            if case.get("business_line"):
                lines.append(f"- **业务线**：{self._sanitize(case['business_line'])}")
            if case.get("tags"):
                lines.append(f"- **案件标签**：{', '.join([self._sanitize(t) for t in case['tags']])}")
            lines.append(f"- **处罚日期**：{case.get('penalty_date', '未公开')}")
            lines.append(f"- **处罚金额**：{format_amount(case.get('penalty_amount', 0))}")
            lines.append("")

            facts = mask_sensitive_info(self._sanitize(case.get("facts", "")))
            if facts:
                lines.append("### 违法事实")
                lines.append("")
                lines.append(self._format_block(facts))
                lines.append("")

            result = mask_sensitive_info(self._sanitize(case.get("result_summary", "")))
            if result:
                lines.append("### 处理结果")
                lines.append("")
                lines.append(self._format_block(result))
                lines.append("")

            defense = mask_sensitive_info(self._sanitize(case.get("defense_content", "")))
            if defense:
                lines.append("### 申辩意见要点")
                lines.append("")
                lines.append(self._format_block(defense, 1000))
                lines.append("")

            rectification = mask_sensitive_info(self._sanitize(case.get("rectification_report", "")))
            if rectification:
                lines.append("### 整改措施")
                lines.append("")
                lines.append(self._format_block(rectification, 1000))
                lines.append("")

            script = mask_sensitive_info(self._sanitize(case.get("reference_script", "")))
            if script:
                lines.append("### 可借鉴话术")
                lines.append("")
                lines.append(self._format_block(script))
                lines.append("")

            lines.append("---")
            lines.append("")

        lines.append("*本清单仅供内部参考，请勿对外传播。*")
        lines.append("")

        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return os.path.abspath(output_path)

    def export_to_text(self, case_ids: List[int], output_path: str,
                       title: Optional[str] = None) -> str:
        """导出为纯文本格式"""
        cases = self.db.get_cases_export(case_ids)
        if not cases:
            raise ValueError("未找到可导出的案例")

        title = title or "监管处罚案例参考清单"
        generated_at = datetime.now().strftime("%Y年%m月%d日 %H:%M")
        separator = "=" * 80

        lines = []
        lines.append(separator)
        lines.append(f"  {title}")
        lines.append(separator)
        lines.append(f"  生成时间：{generated_at}")
        lines.append(f"  案例数量：{len(cases)} 个")
        lines.append("  说明：本清单已脱敏处理，隐藏了内部敏感信息。")
        lines.append(separator)
        lines.append("")

        for idx, case in enumerate(cases, 1):
            lines.append(f"【案例 {idx}】 {case.get('case_no', '')}")
            lines.append("-" * 60)
            lines.append(f"  所属公司：{self._sanitize(case.get('company', ''))}")
            lines.append(f"  监管部门：{self._sanitize(case.get('regulator', ''))}")
            if case.get("business_line"):
                lines.append(f"  业务线  ：{self._sanitize(case['business_line'])}")
            if case.get("tags"):
                lines.append(f"  案标签  ：{', '.join([self._sanitize(t) for t in case['tags']])}")
            lines.append(f"  处罚日期：{case.get('penalty_date', '未公开')}")
            lines.append(f"  处罚金额：{format_amount(case.get('penalty_amount', 0))}")
            lines.append("")

            facts = mask_sensitive_info(self._sanitize(case.get("facts", "")))
            if facts:
                lines.append("  ▌ 违法事实")
                lines.append(self._indent_text(facts, 4))
                lines.append("")

            result = mask_sensitive_info(self._sanitize(case.get("result_summary", "")))
            if result:
                lines.append("  ▌ 处理结果")
                lines.append(self._indent_text(result, 4))
                lines.append("")

            defense = mask_sensitive_info(self._sanitize(case.get("defense_content", "")))
            if defense:
                lines.append("  ▌ 申辩意见要点")
                lines.append(self._indent_text(defense, 4, 1000))
                lines.append("")

            rectification = mask_sensitive_info(self._sanitize(case.get("rectification_report", "")))
            if rectification:
                lines.append("  ▌ 整改措施")
                lines.append(self._indent_text(rectification, 4, 1000))
                lines.append("")

            script = mask_sensitive_info(self._sanitize(case.get("reference_script", "")))
            if script:
                lines.append("  ▌ 可借鉴话术")
                lines.append(self._indent_text(script, 4))
                lines.append("")

            lines.append(separator)
            lines.append("")

        lines.append("【注意】本清单仅供内部参考，请勿对外传播。")

        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return os.path.abspath(output_path)

    def export_to_json(self, case_ids: List[int], output_path: str) -> str:
        """导出为JSON格式（便于程序处理）"""
        cases = self.db.get_cases_export(case_ids)
        if not cases:
            raise ValueError("未找到可导出的案例")

        export_data = {
            "title": "监管处罚案例参考清单",
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "case_count": len(cases),
            "cases": []
        }

        for case in cases:
            case_export = {
                "case_no": case.get("case_no", ""),
                "company": self._sanitize(case.get("company", "")),
                "regulator": self._sanitize(case.get("regulator", "")),
                "business_line": self._sanitize(case.get("business_line", "")),
                "tags": [self._sanitize(t) for t in case.get("tags", [])],
                "penalty_date": case.get("penalty_date", ""),
                "penalty_amount": case.get("penalty_amount", 0),
                "penalty_amount_formatted": format_amount(case.get("penalty_amount", 0)),
                "facts": mask_sensitive_info(self._sanitize(case.get("facts", ""))),
                "result_summary": mask_sensitive_info(self._sanitize(case.get("result_summary", ""))),
                "defense_content": mask_sensitive_info(self._sanitize(case.get("defense_content", ""))),
                "rectification_report": mask_sensitive_info(self._sanitize(case.get("rectification_report", ""))),
                "reference_script": mask_sensitive_info(self._sanitize(case.get("reference_script", ""))),
            }
            export_data["cases"].append(case_export)

        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        return os.path.abspath(output_path)

    def auto_export_path(self, output_dir: Optional[str] = None,
                         format_type: str = "md",
                         prefix: str = "penalty_cases") -> str:
        """自动生成导出文件路径"""
        if not output_dir:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            output_dir = os.path.join(base_dir, "exports")

        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{timestamp}.{format_type}"
        return os.path.join(output_dir, filename)

    def _sanitize(self, text: str) -> str:
        """清理文本（移除明显的内部标注等）"""
        if not text:
            return ""
        return str(text).strip()

    def _get_case_brief(self, case: Dict) -> str:
        """获取案例简短描述"""
        summary = case.get("result_summary", "") or case.get("facts", "")
        if summary:
            summary = self._sanitize(summary)
            return summary[:50] + ("..." if len(summary) > 50 else "")
        return ""

    def _format_block(self, text: str, max_length: Optional[int] = None) -> str:
        """格式化文本块为Markdown引用样式"""
        if not text:
            return ""
        content = self._sanitize(text)
        if max_length and len(content) > max_length:
            content = content[:max_length] + "..."
        lines = content.split("\n")
        return "\n".join([f"> {line}" if line else ">" for line in lines])

    def _indent_text(self, text: str, indent: int = 4,
                     max_length: Optional[int] = None) -> str:
        """文本缩进"""
        if not text:
            return ""
        content = self._sanitize(text)
        if max_length and len(content) > max_length:
            content = content[:max_length] + "..."
        prefix = " " * indent
        lines = content.split("\n")
        return "\n".join([(prefix + line) if line else "" for line in lines])
