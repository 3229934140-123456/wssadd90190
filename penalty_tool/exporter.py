"""导出模块 - 支持多模板导出（完整版/律师版/业务版），自动脱敏处理"""

import os
import json
import re
from datetime import datetime
from typing import List, Dict, Optional
from .database import PenaltyDatabase
from .utils import format_amount, mask_sensitive_info


VALID_TEMPLATES = {"full", "lawyer", "business"}

TEMPLATE_DESCRIPTIONS = {
    "full": "完整版 - 包含所有可对外披露的信息",
    "lawyer": "律师版 - 侧重事实、申辩意见、整改措施、处理结果，适合律师审阅",
    "business": "业务版 - 精简版，仅含事实、处理动作、可借鉴话术，适合业务部门参考",
}


class CaseExporter:
    """案例导出器"""

    def __init__(self, db: Optional[PenaltyDatabase] = None, db_path: Optional[str] = None):
        self.db = db or PenaltyDatabase(db_path)

    # ========== Markdown 导出 ==========

    def export_to_markdown(self, case_ids: List[int], output_path: str,
                           title: Optional[str] = None,
                           template: str = "full") -> str:
        """
        导出为 Markdown 格式

        Args:
            case_ids: 案例ID列表
            output_path: 输出文件路径
            title: 文档标题
            template: 模板类型：full / lawyer / business
        """
        if template not in VALID_TEMPLATES:
            raise ValueError(f"不支持的模板: {template}")

        cases = self.db.get_cases_export(case_ids)
        if not cases:
            raise ValueError("未找到可导出的案例")

        title = title or self._default_title(template)
        generated_at = datetime.now().strftime("%Y年%m月%d日 %H:%M")

        lines = []
        lines.append(f"# {title}")
        lines.append("")
        lines.append(f"> 生成时间：{generated_at}")
        lines.append(f"> 案例数量：{len(cases)} 个")
        lines.append(f"> 模板类型：{TEMPLATE_DESCRIPTIONS.get(template, template)}")
        lines.append(f"> 说明：本清单已脱敏处理，隐藏了内部敏感信息。")
        lines.append("")
        lines.append("---")
        lines.append("")

        lines.append("## 目录")
        lines.append("")
        for idx, case in enumerate(cases, 1):
            anchor = f"案例{idx}-{case.get('case_no', '')}"
            brief = self._get_case_brief(case, template)
            line = f"{idx}. [{case.get('case_no', '')} - {case.get('company', '')}](#{anchor})"
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

            lines.extend(self._render_md_basic_info(case))
            lines.append("")

            if template == "business":
                lines.extend(self._render_md_business(case))
            elif template == "lawyer":
                lines.extend(self._render_md_lawyer(case))
            else:
                lines.extend(self._render_md_full(case))

            lines.append("---")
            lines.append("")

        lines.append("*本清单仅供内部参考，请勿对外传播。*")
        lines.append("")

        self._write_file(output_path, "\n".join(lines))
        return os.path.abspath(output_path)

    def _render_md_basic_info(self, case: Dict) -> List[str]:
        """渲染基本信息块"""
        lines = []
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
        return lines

    def _render_md_full(self, case: Dict) -> List[str]:
        """完整版 Markdown 渲染"""
        lines = []

        facts = mask_sensitive_info(self._sanitize(case.get("facts", "")))
        if facts:
            lines.append("### 违法事实")
            lines.append("")
            lines.append(self._format_md_block(facts))
            lines.append("")

        result = mask_sensitive_info(self._sanitize(case.get("result_summary", "")))
        if result:
            lines.append("### 处理结果")
            lines.append("")
            lines.append(self._format_md_block(result))
            lines.append("")

        defense = mask_sensitive_info(self._sanitize(case.get("defense_content", "")))
        if defense:
            lines.append("### 申辩意见要点")
            lines.append("")
            lines.append(self._format_md_block(defense, 1500))
            lines.append("")

        rectification = mask_sensitive_info(self._sanitize(case.get("rectification_report", "")))
        if rectification:
            lines.append("### 整改措施")
            lines.append("")
            lines.append(self._format_md_block(rectification, 1500))
            lines.append("")

        script = mask_sensitive_info(self._sanitize(case.get("reference_script", "")))
        if script:
            lines.append("### 可借鉴话术")
            lines.append("")
            lines.append(self._format_md_block(script))
            lines.append("")

        return lines

    def _render_md_lawyer(self, case: Dict) -> List[str]:
        """律师版 Markdown 渲染（侧重事实、申辩、整改、处理）"""
        lines = []

        facts = mask_sensitive_info(self._sanitize(case.get("facts", "")))
        if facts:
            lines.append("### 一、违法事实")
            lines.append("")
            lines.append(self._format_md_block(facts, 2000))
            lines.append("")

        result = mask_sensitive_info(self._sanitize(case.get("result_summary", "")))
        if result:
            lines.append("### 二、处理结果")
            lines.append("")
            lines.append(self._format_md_block(result))
            lines.append("")

        defense = mask_sensitive_info(self._sanitize(case.get("defense_content", "")))
        if defense:
            lines.append("### 三、申辩意见及抗辩要点")
            lines.append("")
            lines.append(self._extract_key_points(defense, 1500))
            lines.append("")

        rectification = mask_sensitive_info(self._sanitize(case.get("rectification_report", "")))
        if rectification:
            lines.append("### 四、整改措施及合规启示")
            lines.append("")
            lines.append(self._extract_key_points(rectification, 1500))
            lines.append("")

        script = mask_sensitive_info(self._sanitize(case.get("reference_script", "")))
        if script:
            lines.append("### 五、参考表述")
            lines.append("")
            lines.append(self._format_md_block(script))
            lines.append("")

        return lines

    def _render_md_business(self, case: Dict) -> List[str]:
        """业务版 Markdown 渲染（精简：事实、处理、话术）"""
        lines = []

        facts = mask_sensitive_info(self._sanitize(case.get("facts", "")))
        if facts:
            lines.append("### 一、事实概要")
            lines.append("")
            lines.append(self._extract_brief_facts(facts))
            lines.append("")

        result = mask_sensitive_info(self._sanitize(case.get("result_summary", "")))
        if result:
            lines.append("### 二、处理结果及影响")
            lines.append("")
            lines.append(self._format_md_block(result))
            lines.append("")

        rectification = mask_sensitive_info(self._sanitize(case.get("rectification_report", "")))
        if rectification:
            lines.append("### 三、整改动作（供业务参考）")
            lines.append("")
            lines.append(self._extract_action_items(rectification))
            lines.append("")

        script = mask_sensitive_info(self._sanitize(case.get("reference_script", "")))
        if script:
            lines.append("### 四、可借鉴话术")
            lines.append("")
            lines.append(self._format_md_block(script))
            lines.append("")

        return lines

    # ========== TXT 导出 ==========

    def export_to_text(self, case_ids: List[int], output_path: str,
                       title: Optional[str] = None,
                       template: str = "full") -> str:
        """导出为纯文本格式"""
        if template not in VALID_TEMPLATES:
            raise ValueError(f"不支持的模板: {template}")

        cases = self.db.get_cases_export(case_ids)
        if not cases:
            raise ValueError("未找到可导出的案例")

        title = title or self._default_title(template)
        generated_at = datetime.now().strftime("%Y年%m月%d日 %H:%M")
        separator = "=" * 78

        lines = []
        lines.append(separator)
        lines.append(f"  {title}")
        lines.append(separator)
        lines.append(f"  生成时间：{generated_at}")
        lines.append(f"  案例数量：{len(cases)} 个")
        lines.append(f"  模板类型：{TEMPLATE_DESCRIPTIONS.get(template, template)}")
        lines.append("  说明：本清单已脱敏处理，隐藏了内部敏感信息。")
        lines.append(separator)
        lines.append("")

        for idx, case in enumerate(cases, 1):
            lines.extend(self._render_txt_case(idx, case, template))
            lines.append(separator)
            lines.append("")

        lines.append("【注意】本清单仅供内部参考，请勿对外传播。")

        self._write_file(output_path, "\n".join(lines))
        return os.path.abspath(output_path)

    def _render_txt_case(self, idx: int, case: Dict, template: str) -> List[str]:
        """渲染单个案例的TXT格式"""
        lines = []
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
        result = mask_sensitive_info(self._sanitize(case.get("result_summary", "")))
        defense = mask_sensitive_info(self._sanitize(case.get("defense_content", "")))
        rectification = mask_sensitive_info(self._sanitize(case.get("rectification_report", "")))
        script = mask_sensitive_info(self._sanitize(case.get("reference_script", "")))

        if template == "business":
            if facts:
                lines.append("  ▌ 事实概要")
                lines.append(self._indent_text(self._extract_brief_facts(facts), 4))
                lines.append("")
            if result:
                lines.append("  ▌ 处理结果")
                lines.append(self._indent_text(result, 4))
                lines.append("")
            if rectification:
                lines.append("  ▌ 整改动作")
                lines.append(self._indent_text(self._extract_action_items(rectification), 4))
                lines.append("")
            if script:
                lines.append("  ▌ 可借鉴话术")
                lines.append(self._indent_text(script, 4))
                lines.append("")

        elif template == "lawyer":
            if facts:
                lines.append("  ▌ 违法事实")
                lines.append(self._indent_text(facts[:2000], 4))
                lines.append("")
            if result:
                lines.append("  ▌ 处理结果")
                lines.append(self._indent_text(result, 4))
                lines.append("")
            if defense:
                lines.append("  ▌ 申辩要点")
                lines.append(self._indent_text(self._extract_key_points(defense, 1500), 4))
                lines.append("")
            if rectification:
                lines.append("  ▌ 整改措施")
                lines.append(self._indent_text(self._extract_key_points(rectification, 1500), 4))
                lines.append("")
            if script:
                lines.append("  ▌ 参考表述")
                lines.append(self._indent_text(script, 4))
                lines.append("")

        else:
            if facts:
                lines.append("  ▌ 违法事实")
                lines.append(self._indent_text(facts[:2000], 4))
                if len(facts) > 2000:
                    lines.append("  " + " " * 4 + "... (内容已截断)")
                lines.append("")
            if result:
                lines.append("  ▌ 处理结果")
                lines.append(self._indent_text(result, 4))
                lines.append("")
            if defense:
                lines.append("  ▌ 申辩意见")
                lines.append(self._indent_text(defense[:1500], 4))
                if len(defense) > 1500:
                    lines.append("  " + " " * 4 + "... (内容已截断)")
                lines.append("")
            if rectification:
                lines.append("  ▌ 整改报告")
                lines.append(self._indent_text(rectification[:1500], 4))
                if len(rectification) > 1500:
                    lines.append("  " + " " * 4 + "... (内容已截断)")
                lines.append("")
            if script:
                lines.append("  ▌ 可借鉴话术")
                lines.append(self._indent_text(script, 4))
                lines.append("")

        return lines

    # ========== JSON 导出 ==========

    def export_to_json(self, case_ids: List[int], output_path: str,
                       template: str = "full") -> str:
        """导出为JSON格式"""
        if template not in VALID_TEMPLATES:
            raise ValueError(f"不支持的模板: {template}")

        cases = self.db.get_cases_export(case_ids)
        if not cases:
            raise ValueError("未找到可导出的案例")

        export_data = {
            "title": self._default_title(template),
            "template": template,
            "template_description": TEMPLATE_DESCRIPTIONS.get(template, ""),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "case_count": len(cases),
            "cases": []
        }

        for case in cases:
            base_case = {
                "case_no": case.get("case_no", ""),
                "company": self._sanitize(case.get("company", "")),
                "regulator": self._sanitize(case.get("regulator", "")),
                "business_line": self._sanitize(case.get("business_line", "")),
                "tags": [self._sanitize(t) for t in case.get("tags", [])],
                "penalty_date": case.get("penalty_date", ""),
                "penalty_amount": case.get("penalty_amount", 0),
                "penalty_amount_formatted": format_amount(case.get("penalty_amount", 0)),
            }

            facts = mask_sensitive_info(self._sanitize(case.get("facts", "")))
            result = mask_sensitive_info(self._sanitize(case.get("result_summary", "")))
            defense = mask_sensitive_info(self._sanitize(case.get("defense_content", "")))
            rectification = mask_sensitive_info(self._sanitize(case.get("rectification_report", "")))
            script = mask_sensitive_info(self._sanitize(case.get("reference_script", "")))

            if template == "business":
                base_case.update({
                    "facts_brief": self._extract_brief_facts(facts) if facts else "",
                    "result_summary": result,
                    "action_items": self._extract_action_items_plain(rectification) if rectification else [],
                    "reference_script": script,
                })
            elif template == "lawyer":
                base_case.update({
                    "facts": facts,
                    "result_summary": result,
                    "defense_key_points": self._extract_key_points_plain(defense) if defense else [],
                    "rectification_key_points": self._extract_key_points_plain(rectification) if rectification else [],
                    "reference_script": script,
                })
            else:
                base_case.update({
                    "facts": facts,
                    "result_summary": result,
                    "defense_content": defense,
                    "rectification_report": rectification,
                    "reference_script": script,
                })

            export_data["cases"].append(base_case)

        self._write_file(output_path, json.dumps(export_data, ensure_ascii=False, indent=2))
        return os.path.abspath(output_path)

    # ========== 辅助方法 ==========

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

    def _default_title(self, template: str) -> str:
        """根据模板生成默认标题"""
        titles = {
            "full": "监管处罚案例参考清单（完整版）",
            "lawyer": "监管处罚案例参考清单（律师版）",
            "business": "监管处罚案例参考清单（业务版）",
        }
        return titles.get(template, "监管处罚案例参考清单")

    def _sanitize(self, text: str) -> str:
        """清理文本"""
        if not text:
            return ""
        return str(text).strip()

    def _get_case_brief(self, case: Dict, template: str) -> str:
        """获取案例简短描述"""
        summary = case.get("result_summary", "") or case.get("facts", "")
        if summary:
            summary = self._sanitize(summary)
            return summary[:60] + ("..." if len(summary) > 60 else "")
        return ""

    def _format_md_block(self, text: str, max_length: Optional[int] = None) -> str:
        """格式化文本块为Markdown引用样式"""
        if not text:
            return ""
        content = self._sanitize(text)
        if max_length and len(content) > max_length:
            content = content[:max_length] + "..."
        lines = content.split("\n")
        return "\n".join([f"> {line}" if line.strip() else ">" for line in lines])

    def _extract_key_points(self, text: str, max_length: int = 1500) -> str:
        """提取关键要点（保留列表结构，Markdown格式）"""
        if not text:
            return ""

        lines = text.split("\n")
        key_lines = []
        capture = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            is_list_item = (
                stripped.startswith(("1.", "2.", "3.", "4.", "5.",
                                       "一、", "二、", "三、", "四、", "五、",
                                       "（一）", "（二）", "（三）",
                                       "•", "·", "-", "*", "第"))
                or any(kw in stripped for kw in ["建立", "完善", "加强", "开展", "落实", "成立"])
            )

            if is_list_item:
                capture = True
                key_lines.append(stripped)
            elif capture and len(key_lines) < 15:
                key_lines.append(stripped)

            if len(key_lines) >= 15:
                break

        if key_lines:
            result = "\n".join([f"> {line}" for line in key_lines])
            return result
        else:
            content = text[:max_length] + ("..." if len(text) > max_length else "")
            return self._format_md_block(content)

    def _extract_key_points_plain(self, text: str) -> List[str]:
        """提取关键要点为列表"""
        if not text:
            return []

        lines = text.split("\n")
        key_lines = []

        for line in lines:
            stripped = line.strip()
            if not stripped or len(stripped) < 6:
                continue
            if any(stripped.startswith(prefix) for prefix in
                   ["1.", "2.", "3.", "4.", "5.", "一、", "二、", "三、",
                    "（一）", "（二）", "•", "·", "-", "*"]):
                key_lines.append(stripped)
                if len(key_lines) >= 15:
                    break

        if not key_lines:
            sentences = re.split(r"[。！？;；]", text)
            key_lines = [s.strip() for s in sentences[:5] if s.strip()]

        return key_lines

    def _extract_brief_facts(self, text: str) -> str:
        """提取事实概要（业务版用）"""
        if not text:
            return ""

        sentences = re.split(r"[。！？\n]", text)
        sentences = [s.strip() for s in sentences if s.strip()]

        brief_sentences = []
        total_len = 0

        for sent in sentences:
            if total_len + len(sent) > 300:
                break
            brief_sentences.append(sent)
            total_len += len(sent) + 1

        result = "。".join(brief_sentences)
        if not result.endswith(("。", "！", "？")):
            result += "。"
        return result

    def _extract_action_items(self, text: str) -> str:
        """提取整改动作项（业务版用，Markdown格式）"""
        items = self._extract_action_items_plain(text)
        if not items:
            return self._format_md_block(text[:500] + ("..." if len(text) > 500 else ""))

        lines = [f"> - {item}" for item in items]
        return "\n".join(lines)

    def _extract_action_items_plain(self, text: str) -> List[str]:
        """提取整改动作项为列表"""
        if not text:
            return []

        action_keywords = ["建立", "制定", "完善", "加强", "开展", "组织", "落实",
                           "设立", "成立", "优化", "新增", "规范", "强化", "改进"]

        lines = text.split("\n")
        actions = []

        for line in lines:
            stripped = line.strip()
            if not stripped or len(stripped) < 8:
                continue

            if any(stripped.startswith(prefix) for prefix in
                   ["1.", "2.", "3.", "4.", "5.", "一、", "二、", "三、",
                    "（一）", "（二）", "•", "·", "-", "*"]):
                if any(kw in stripped for kw in action_keywords):
                    clean = re.sub(r"^[\d\.\-·\s（）一二三四五六七八九十]+、?\s*", "", stripped)
                    if clean:
                        actions.append(clean)

        if not actions:
            sentences = re.split(r"[。；\n]", text)
            for s in sentences:
                s = s.strip()
                if any(kw in s for kw in action_keywords) and len(s) > 10:
                    actions.append(s)
                    if len(actions) >= 5:
                        break

        return actions[:10]

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

    def _write_file(self, path: str, content: str):
        """写入文件，自动创建目录"""
        output_dir = os.path.dirname(path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
