"""文档导入模块 - 支持文件夹批量导入，交互式录入元数据"""

import os
from typing import List, Dict, Optional, Callable
from .database import PenaltyDatabase
from .utils import (
    scan_document_folder,
    read_text_file,
    extract_amount_from_text,
    generate_summary,
    parse_input_list,
    SUPPORTED_EXTENSIONS,
)


class DocumentImporter:
    """文档导入器"""

    def __init__(self, db: Optional[PenaltyDatabase] = None, db_path: Optional[str] = None):
        self.db = db or PenaltyDatabase(db_path)

    def read_document_content(self, file_path: str) -> str:
        """读取文档内容（当前支持txt/md，doc/pdf可后续扩展）"""
        ext = os.path.splitext(file_path)[1].lower()
        if ext in [".txt", ".md"]:
            return read_text_file(file_path)
        elif ext == ".docx":
            return self._read_docx(file_path)
        elif ext == ".pdf":
            return self._read_pdf(file_path)
        else:
            return f"[暂不支持的文件格式: {ext}]"

    def _read_docx(self, file_path: str) -> str:
        """读取docx文件"""
        try:
            from docx import Document
            doc = Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs]
            return "\n".join(paragraphs)
        except ImportError:
            return f"[需要安装python-docx才能读取docx文件: {os.path.basename(file_path)}]"
        except Exception as e:
            return f"[读取docx失败: {str(e)}]"

    def _read_pdf(self, file_path: str) -> str:
        """读取pdf文件"""
        try:
            import pdfplumber
            text_parts = []
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            return "\n".join(text_parts)
        except ImportError:
            return f"[需要安装pdfplumber才能读取pdf文件: {os.path.basename(file_path)}]"
        except Exception as e:
            return f"[读取pdf失败: {str(e)}]"

    def _classify_document(self, filename: str, content: str) -> str:
        """自动判断文档类型：处罚决定书、申辩意见、整改报告"""
        name_lower = filename.lower()
        content_lower = content[:2000].lower() if content else ""

        if any(kw in name_lower for kw in ["申辩", "陈述", "异议", "defense", "objection"]):
            return "defense"
        elif any(kw in name_lower for kw in ["整改", "复查", "rectif", "improve"]):
            return "rectification"
        elif any(kw in name_lower for kw in ["处罚", "决定书", "罚单", "penalty", "decision"]):
            return "penalty"

        if any(kw in content_lower for kw in ["申辩意见", "陈述意见", "异议书"]):
            return "defense"
        elif any(kw in content_lower for kw in ["整改报告", "整改方案", "整改情况"]):
            return "rectification"
        elif any(kw in content_lower for kw in ["行政处罚决定书", "处罚决定书", "罚款"]):
            return "penalty"

        return "penalty"

    def _auto_extract_fields(self, content: str, existing_data: Dict) -> Dict:
        """从文档内容中自动提取字段"""
        data = dict(existing_data)

        if not data.get("penalty_amount"):
            amount = extract_amount_from_text(content)
            if amount:
                data["penalty_amount"] = amount

        if not data.get("result_summary"):
            summary = generate_summary(content, 300)
            if summary:
                data["result_summary"] = summary

        return data

    def import_folder_interactive(self, folder_path: str,
                                  input_func: Optional[Callable] = None,
                                  print_func: Optional[Callable] = None) -> Dict:
        """
        交互式导入文件夹中的所有文档
        input_func: 替代input()的函数，便于测试
        print_func: 替代print()的函数，便于测试
        """
        _input = input_func or input
        _print = print_func or print

        try:
            files = scan_document_folder(folder_path)
        except FileNotFoundError as e:
            return {"success": False, "imported": 0, "failed": 0, "message": str(e)}

        if not files:
            return {
                "success": False,
                "imported": 0,
                "failed": 0,
                "message": f"文件夹中未找到支持的文档 (支持: {', '.join(SUPPORTED_EXTENSIONS)})"
            }

        _print(f"\n{'='*60}")
        _print(f"  发现 {len(files)} 个文档文件")
        _print(f"{'='*60}")
        for i, f in enumerate(files[:20], 1):
            _print(f"  {i:>2}. {os.path.basename(f)}")
        if len(files) > 20:
            _print(f"  ... 还有 {len(files) - 20} 个文件")
        _print(f"{'='*60}\n")

        _print("请输入这批案例的通用元数据信息：")
        _print("-" * 40)

        common_data = {}
        common_data["company"] = _input("  所属公司 (必填): ").strip()
        if not common_data["company"]:
            return {"success": False, "imported": 0, "failed": 0, "message": "所属公司为必填项"}

        common_data["regulator"] = _input("  监管部门 (必填): ").strip()
        if not common_data["regulator"]:
            return {"success": False, "imported": 0, "failed": 0, "message": "监管部门为必填项"}

        common_data["business_line"] = _input("  业务线 (可选，如：广告业务/人力资源/数据合规): ").strip()

        tags_input = _input("  案件标签 (多个标签用逗号分隔，如：广告法,绝对化用语): ").strip()
        common_data["tags"] = parse_input_list(tags_input)

        penalty_date = _input("  处罚日期 (可选，格式YYYY-MM-DD): ").strip()
        common_data["penalty_date"] = penalty_date or None

        _print("\n开始逐个处理文档...\n")

        imported_count = 0
        failed_count = 0
        results = []
        pending_cases: Dict[str, Dict] = {}

        for file_path in files:
            filename = os.path.basename(file_path)
            _print(f"  处理: {filename}")

            content = self.read_document_content(file_path)
            doc_type = self._classify_document(filename, content)

            case_key = self._extract_case_key(filename)

            if case_key not in pending_cases:
                case_data = dict(common_data)
                case_data["source_files"] = []
                case_data = self._auto_extract_fields(content, case_data)
                pending_cases[case_key] = case_data

            pending_cases[case_key]["source_files"].append(filename)

            if doc_type == "penalty":
                existing = pending_cases[case_key].get("facts", "")
                pending_cases[case_key]["facts"] = existing + ("\n\n" if existing else "") + content[:5000]
                pending_cases[case_key] = self._auto_extract_fields(
                    content, pending_cases[case_key]
                )
            elif doc_type == "defense":
                existing = pending_cases[case_key].get("defense_content", "")
                pending_cases[case_key]["defense_content"] = existing + ("\n\n" if existing else "") + content[:5000]
            elif doc_type == "rectification":
                existing = pending_cases[case_key].get("rectification_report", "")
                pending_cases[case_key]["rectification_report"] = existing + ("\n\n" if existing else "") + content[:5000]

        _print(f"\n检测到 {len(pending_cases)} 个独立案件，开始确认入库...\n")

        for idx, (case_key, case_data) in enumerate(pending_cases.items(), 1):
            _print(f"\n--- 案件 {idx}/{len(pending_cases)} ---")
            _print(f"  关联文件: {', '.join(case_data['source_files'][:3])}"
                   + ("..." if len(case_data['source_files']) > 3 else ""))

            overwrite = _input(f"  是否覆盖通用字段？(y/N): ").strip().lower()
            if overwrite == "y":
                case_data["company"] = _input(f"  所属公司 [{case_data['company']}]: ").strip() or case_data["company"]
                case_data["regulator"] = _input(f"  监管部门 [{case_data['regulator']}]: ").strip() or case_data["regulator"]
                new_biz = _input(f"  业务线 [{case_data.get('business_line', '')}]: ").strip()
                if new_biz:
                    case_data["business_line"] = new_biz

                new_tags = _input(f"  标签 [{', '.join(case_data.get('tags', []))}]: ").strip()
                if new_tags:
                    case_data["tags"] = parse_input_list(new_tags)

                new_date = _input(f"  处罚日期 [{case_data.get('penalty_date', '')}]: ").strip()
                if new_date:
                    case_data["penalty_date"] = new_date

                amount = case_data.get("penalty_amount", 0)
                new_amount = _input(f"  处罚金额 [{amount}元]: ").strip()
                if new_amount:
                    try:
                        case_data["penalty_amount"] = float(new_amount)
                    except ValueError:
                        pass

            reference = _input(f"  可借鉴话术 (可选): ").strip()
            if reference:
                case_data["reference_script"] = reference

            internal_analysis = _input(f"  内部金额测算 (可选，不对外导出): ").strip()
            if internal_analysis:
                case_data["internal_amount_analysis"] = internal_analysis

            contacts = _input(f"  敏感联系人信息 (可选，不对外导出): ").strip()
            if contacts:
                case_data["sensitive_contacts"] = contacts

            success, case_no, message = self.db.insert_case(case_data)
            if success:
                imported_count += 1
                _print(f"  ✓ {message}")
                results.append({"case_no": case_no, "files": case_data["source_files"], "status": "success"})
            else:
                failed_count += 1
                _print(f"  ✗ {message}")
                results.append({"files": case_data["source_files"], "status": "failed", "error": message})

        _print(f"\n{'='*60}")
        _print(f"  导入完成: 成功 {imported_count} 个，失败 {failed_count} 个")
        _print(f"{'='*60}")

        return {
            "success": True,
            "imported": imported_count,
            "failed": failed_count,
            "results": results
        }

    def _extract_case_key(self, filename: str) -> str:
        """从文件名提取案件识别键（用于合并关联文档）"""
        base = os.path.splitext(filename)[0]

        patterns_to_strip = [
            r"[ _\-]*(处罚决定书|决定书|处罚通知|罚单)$",
            r"[ _\-]*(申辩意见|陈述意见|申辩书|异议书)$",
            r"[ _\-]*(整改报告|整改方案|整改情况|复查报告)$",
            r"[ _\-]*(final|最终|定稿|v\d+)$",
        ]

        result = base
        for pattern in patterns_to_strip:
            result = re.sub(pattern, "", result, flags=re.IGNORECASE)

        if len(result) < 2:
            result = base

        return result.lower()

    def import_single_manual(self, case_data: Dict) -> Tuple[bool, str, str]:
        """手动单条导入案例"""
        return self.db.insert_case(case_data)


import re
