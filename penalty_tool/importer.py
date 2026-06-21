"""文档导入模块 - 支持文件夹批量导入，交互式录入元数据"""

import os
import re
from typing import List, Dict, Optional, Callable, Tuple
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

    # ========== v1 导入方法（保留兼容性） ==========

    def import_folder_interactive(self, folder_path: str,
                                  input_func: Optional[Callable] = None,
                                  print_func: Optional[Callable] = None) -> Dict:
        """
        交互式导入文件夹中的所有文档（v1 版本，简单分组）

        Args:
            folder_path: 文档文件夹路径
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

    # ========== v2 导入方法（智能分组 + 预览 + 交互式调整） ==========

    def import_folder_interactive_v2(self, folder_path: str,
                                     input_func: Optional[Callable] = None,
                                     print_func: Optional[Callable] = None) -> Dict:
        """
        v2 版交互式导入：智能分组 + 分组预览 + 交互式调整 + 批量入库

        改进点：
        - 更稳健的分组算法（文件名相似度 + 内容主题匹配）
        - 分组预览，确认前可看到每组包含哪些文件
        - 支持交互式调整：合并、拆分、重命名、移除、移动文件
        - 批量录入元数据，减少重复输入
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

        _print(f"\n{'=' * 60}")
        _print(f"  智能导入模式 - 发现 {len(files)} 个文档")
        _print(f"{'=' * 60}")
        for i, f in enumerate(files[:15], 1):
            _print(f"  {i:>2}. {os.path.basename(f)}")
        if len(files) > 15:
            _print(f"  ... 还有 {len(files) - 15} 个文件")
        _print()

        _print("  正在分析文档并自动分组...")
        groups = self._smart_group_files(files)
        _print(f"  ✓ 自动识别出 {len(groups)} 个案件分组\n")

        groups = self._interactive_review_groups(groups, _input, _print)

        if not groups:
            _print("  ! 没有待导入的案件分组，已取消")
            return {"success": False, "imported": 0, "failed": 0, "message": "用户取消导入"}

        common_data = self._collect_common_metadata(_input, _print)
        if not common_data:
            return {"success": False, "imported": 0, "failed": 0, "message": "元数据不完整"}

        return self._import_groups(groups, common_data, files, _input, _print)

    def _smart_group_files(self, file_paths: List[str]) -> List[Dict]:
        """
        智能分组算法：
        1. 先按文件名前缀（去除类型后缀）初分
        2. 再按内容相似度（关键词重叠）合并或拆分
        3. 生成分组名称和类型标记
        """
        groups_dict: Dict[str, Dict] = {}

        for file_path in file_paths:
            filename = os.path.basename(file_path)
            content = self.read_document_content(file_path)
            doc_type = self._classify_document(filename, content)

            group_key = self._extract_case_key(filename)

            if group_key not in groups_dict:
                display_name = self._generate_group_display_name(filename, group_key)
                groups_dict[group_key] = {
                    "key": group_key,
                    "display_name": display_name,
                    "files": [],
                    "doc_types": set(),
                    "has_penalty": False,
                    "has_defense": False,
                    "has_rectification": False,
                    "amount": None,
                    "summary": "",
                }

            file_info = {
                "path": file_path,
                "name": filename,
                "type": doc_type,
                "content": content,
            }
            groups_dict[group_key]["files"].append(file_info)
            groups_dict[group_key]["doc_types"].add(doc_type)

            if doc_type == "penalty":
                groups_dict[group_key]["has_penalty"] = True
                if not groups_dict[group_key]["amount"]:
                    amount = extract_amount_from_text(content)
                    if amount:
                        groups_dict[group_key]["amount"] = amount
                if not groups_dict[group_key]["summary"]:
                    groups_dict[group_key]["summary"] = generate_summary(content, 200)
            elif doc_type == "defense":
                groups_dict[group_key]["has_defense"] = True
            elif doc_type == "rectification":
                groups_dict[group_key]["has_rectification"] = True

        groups = list(groups_dict.values())

        if len(groups) > 1:
            groups = self._merge_similar_groups(groups)

        for i, g in enumerate(groups, 1):
            g["id"] = i

        return groups

    def _generate_group_display_name(self, filename: str, key: str) -> str:
        """生成用户友好的分组显示名称"""
        base = os.path.splitext(filename)[0]

        suffixes_to_remove = [
            "-处罚决定书", "_处罚决定书", "处罚决定书",
            "-申辩意见", "_申辩意见", "申辩意见",
            "-整改报告", "_整改报告", "整改报告",
            "-决定书", "_决定书",
            "-final", "_final", "-最终", "_最终",
            "-v1", "-v2", "-v3",
        ]

        name = base
        for suffix in suffixes_to_remove:
            if name.lower().endswith(suffix.lower()):
                name = name[:-len(suffix)]
                break

        return name.strip(" -_") or key

    def _merge_similar_groups(self, groups: List[Dict], threshold: float = 0.6) -> List[Dict]:
        """合并内容高度相似的分组"""
        if len(groups) < 2:
            return groups

        def get_group_keywords(group: Dict) -> set:
            """提取分组的关键词集合"""
            keywords = set()
            for f in group["files"]:
                content = f["content"][:2000]
                words = re.findall(r"[\u4e00-\u9fa5]{2,}|[a-zA-Z]{2,}", content)
                keywords.update(words[:50])
                name_words = re.findall(r"[\u4e00-\u9fa5]{2,}|[a-zA-Z]{2,}", f["name"])
                keywords.update(name_words)
            return keywords

        merged = True
        while merged and len(groups) > 1:
            merged = False
            for i in range(len(groups)):
                for j in range(i + 1, len(groups)):
                    kw_i = get_group_keywords(groups[i])
                    kw_j = get_group_keywords(groups[j])
                    if not kw_i or not kw_j:
                        continue

                    intersection = kw_i & kw_j
                    union = kw_i | kw_j
                    similarity = len(intersection) / len(union) if union else 0

                    if similarity >= threshold:
                        groups[i]["files"].extend(groups[j]["files"])
                        groups[i]["doc_types"].update(groups[j]["doc_types"])
                        groups[i]["has_penalty"] = groups[i]["has_penalty"] or groups[j]["has_penalty"]
                        groups[i]["has_defense"] = groups[i]["has_defense"] or groups[j]["has_defense"]
                        groups[i]["has_rectification"] = groups[i]["has_rectification"] or groups[j]["has_rectification"]
                        if not groups[i]["amount"] and groups[j]["amount"]:
                            groups[i]["amount"] = groups[j]["amount"]
                        if not groups[i]["summary"] and groups[j]["summary"]:
                            groups[i]["summary"] = groups[j]["summary"]
                        groups.pop(j)
                        merged = True
                        break
                if merged:
                    break

        return groups

    def _interactive_review_groups(self, groups: List[Dict],
                                    _input: Callable, _print: Callable) -> List[Dict]:
        """交互式分组预览和调整"""
        while True:
            _print("=" * 60)
            _print("  案件分组预览")
            _print("=" * 60)

            for g in groups:
                type_labels = []
                if g["has_penalty"]:
                    type_labels.append("处罚书")
                if g["has_defense"]:
                    type_labels.append("申辩")
                if g["has_rectification"]:
                    type_labels.append("整改")

                amount_str = ""
                if g.get("amount"):
                    from .utils import format_amount
                    amount_str = f" | 预估金额: {format_amount(g['amount'])}"

                _print(f"\n  [{g['id']:>2}] {g['display_name']}")
                _print(f"      类型: {'/'.join(type_labels) if type_labels else '未知'}{amount_str}")
                _print(f"      文件 ({len(g['files'])} 个):")
                for f in g["files"]:
                    type_icon = {"penalty": "📄", "defense": "💬", "rectification": "📋"}.get(f["type"], "📎")
                    _print(f"        {type_icon} {f['name']}")

            _print()
            _print("  操作选项:")
            _print("    c - 确认分组，继续导入")
            _print("    m <组1,组2> - 合并两个分组（如 m 1,2）")
            _print("    s <组号> - 拆分某个分组（每个文件独立成组）")
            _print("    r <组号> <新名称> - 重命名分组")
            _print("    d <组号> - 删除/跳过某个分组")
            _print("    mv <文件号> <目标组号> - 移动文件到另一组")
            _print("    q - 取消导入")
            _print()

            choice = _input("  请选择操作 [c]: ").strip().lower()

            if not choice or choice == "c":
                break

            elif choice.startswith("m "):
                parts = choice[2:].replace("，", ",").split(",")
                if len(parts) >= 2:
                    try:
                        id1, id2 = int(parts[0].strip()), int(parts[1].strip())
                        groups = self._merge_groups_by_id(groups, id1, id2)
                    except ValueError:
                        _print("  ! 请输入有效的组号，如 m 1,2")
                else:
                    _print("  ! 请输入两个组号，如 m 1,2")

            elif choice.startswith("s "):
                try:
                    group_id = int(choice[2:].strip())
                    groups = self._split_group(groups, group_id)
                except ValueError:
                    _print("  ! 请输入有效的组号")

            elif choice.startswith("r "):
                parts = choice[2:].split(None, 1)
                if len(parts) >= 2:
                    try:
                        group_id = int(parts[0])
                        new_name = parts[1].strip()
                        for g in groups:
                            if g["id"] == group_id:
                                g["display_name"] = new_name
                                break
                        _print(f"  ✓ 分组已重命名")
                    except ValueError:
                        _print("  ! 请输入有效的组号和名称")
                else:
                    _print("  ! 格式：r <组号> <新名称>")

            elif choice.startswith("d "):
                try:
                    group_id = int(choice[2:].strip())
                    groups = [g for g in groups if g["id"] != group_id]
                    groups = self._renumber_groups(groups)
                    _print(f"  ✓ 已删除分组 {group_id}")
                except ValueError:
                    _print("  ! 请输入有效的组号")

            elif choice.startswith("mv "):
                parts = choice[3:].split()
                if len(parts) >= 2:
                    try:
                        file_idx = int(parts[0])
                        target_id = int(parts[1])
                        groups = self._move_file_between_groups(groups, file_idx, target_id)
                    except ValueError:
                        _print("  ! 请输入有效的文件序号和目标组号")
                else:
                    _print("  ! 格式：mv <文件序号> <目标组号>")

            elif choice == "q":
                return []

            else:
                _print("  ! 无效选项，请重新输入")

        return groups

    def _merge_groups_by_id(self, groups: List[Dict], id1: int, id2: int) -> List[Dict]:
        """按ID合并两个分组"""
        g1 = next((g for g in groups if g["id"] == id1), None)
        g2 = next((g for g in groups if g["id"] == id2), None)

        if not g1 or not g2:
            return groups

        g1["files"].extend(g2["files"])
        g1["doc_types"].update(g2["doc_types"])
        g1["has_penalty"] = g1["has_penalty"] or g2["has_penalty"]
        g1["has_defense"] = g1["has_defense"] or g2["has_defense"]
        g1["has_rectification"] = g1["has_rectification"] or g2["has_rectification"]
        if not g1["amount"] and g2["amount"]:
            g1["amount"] = g2["amount"]
        if not g1["summary"] and g2["summary"]:
            g1["summary"] = g2["summary"]

        groups = [g for g in groups if g["id"] != id2]
        return self._renumber_groups(groups)

    def _split_group(self, groups: List[Dict], group_id: int) -> List[Dict]:
        """拆分分组为单个文件组"""
        target = next((g for g in groups if g["id"] == group_id), None)
        if not target:
            return groups

        groups = [g for g in groups if g["id"] != group_id]

        new_groups = []
        for i, f in enumerate(target["files"]):
            new_group = {
                "id": 0,
                "key": f"{target['key']}_split{i}",
                "display_name": f"{target['display_name']}-{i+1}",
                "files": [f],
                "doc_types": {f["type"]},
                "has_penalty": f["type"] == "penalty",
                "has_defense": f["type"] == "defense",
                "has_rectification": f["type"] == "rectification",
                "amount": target.get("amount") if i == 0 else None,
                "summary": target.get("summary") if i == 0 else "",
            }
            new_groups.append(new_group)

        groups.extend(new_groups)
        return self._renumber_groups(groups)

    def _move_file_between_groups(self, groups: List[Dict],
                                  file_global_idx: int, target_id: int) -> List[Dict]:
        """在分组间移动文件（按全局文件序号）"""
        all_files = []
        for g in groups:
            for f in g["files"]:
                all_files.append((g, f))

        if file_global_idx < 1 or file_global_idx > len(all_files):
            return groups

        src_group, file_info = all_files[file_global_idx - 1]
        tgt_group = next((g for g in groups if g["id"] == target_id), None)

        if not tgt_group or src_group is tgt_group:
            return groups

        src_group["files"].remove(file_info)
        if not src_group["files"]:
            groups = [g for g in groups if g["id"] != src_group["id"]]

        tgt_group["files"].append(file_info)
        tgt_group["doc_types"].add(file_info["type"])
        if file_info["type"] == "penalty":
            tgt_group["has_penalty"] = True
            if not tgt_group["amount"]:
                amount = extract_amount_from_text(file_info["content"])
                if amount:
                    tgt_group["amount"] = amount
        elif file_info["type"] == "defense":
            tgt_group["has_defense"] = True
        elif file_info["type"] == "rectification":
            tgt_group["has_rectification"] = True

        return self._renumber_groups(groups)

    def _renumber_groups(self, groups: List[Dict]) -> List[Dict]:
        """重新编号分组"""
        for i, g in enumerate(groups, 1):
            g["id"] = i
        return groups

    def _collect_common_metadata(self, _input: Callable, _print: Callable) -> Optional[Dict]:
        """收集通用元数据"""
        _print()
        _print("=" * 60)
        _print("  录入案件通用元数据")
        _print("=" * 60)

        data = {}
        data["company"] = _input("  所属公司 (必填): ").strip()
        if not data["company"]:
            _print("  ! 所属公司为必填项")
            return None

        data["regulator"] = _input("  监管部门 (必填): ").strip()
        if not data["regulator"]:
            _print("  ! 监管部门为必填项")
            return None

        data["business_line"] = _input("  业务线 (可选): ").strip()

        tags_input = _input("  案件标签 (逗号分隔，如：广告法,绝对化用语): ").strip()
        data["tags"] = parse_input_list(tags_input)

        penalty_date = _input("  处罚日期 (可选，YYYY-MM-DD): ").strip()
        data["penalty_date"] = penalty_date or None

        return data

    def _import_groups(self, groups: List[Dict], common_data: Dict,
                       all_files: List[str], _input: Callable, _print: Callable) -> Dict:
        """批量导入分组到数据库"""
        imported_count = 0
        failed_count = 0
        results = []

        _print()
        _print("=" * 60)
        _print(f"  开始导入 {len(groups)} 个案件")
        _print("=" * 60)
        _print()

        for idx, group in enumerate(groups, 1):
            _print(f"--- 案件 {idx}/{len(groups)}: {group['display_name']} ---")

            case_data = dict(common_data)
            case_data["source_files"] = [f["name"] for f in group["files"]]
            case_data["facts"] = ""
            case_data["defense_content"] = ""
            case_data["rectification_report"] = ""

            for f in group["files"]:
                content = f["content"]
                if f["type"] == "penalty":
                    existing = case_data.get("facts", "")
                    case_data["facts"] = existing + ("\n\n" if existing else "") + content[:5000]
                elif f["type"] == "defense":
                    existing = case_data.get("defense_content", "")
                    case_data["defense_content"] = existing + ("\n\n" if existing else "") + content[:5000]
                elif f["type"] == "rectification":
                    existing = case_data.get("rectification_report", "")
                    case_data["rectification_report"] = existing + ("\n\n" if existing else "") + content[:5000]

            case_data = self._auto_extract_fields(
                (group.get("files", [{}])[0].get("content", "") if group.get("files") else ""),
                case_data
            )

            if group.get("amount"):
                case_data["penalty_amount"] = group["amount"]

            _print(f"  关联文件: {', '.join(case_data['source_files'][:3])}"
                   + ("..." if len(case_data['source_files']) > 3 else ""))

            edit = _input("  编辑此案件的字段？(y/N): ").strip().lower()
            if edit == "y":
                case_data["company"] = _input(f"    所属公司 [{case_data['company']}]: ").strip() or case_data["company"]
                case_data["regulator"] = _input(f"    监管部门 [{case_data['regulator']}]: ").strip() or case_data["regulator"]
                new_biz = _input(f"    业务线 [{case_data.get('business_line', '')}]: ").strip()
                if new_biz:
                    case_data["business_line"] = new_biz

                new_tags = _input(f"    标签 [{', '.join(case_data.get('tags', []))}]: ").strip()
                if new_tags:
                    case_data["tags"] = parse_input_list(new_tags)

                new_date = _input(f"    处罚日期 [{case_data.get('penalty_date', '')}]: ").strip()
                if new_date:
                    case_data["penalty_date"] = new_date

                amount = case_data.get("penalty_amount", 0)
                new_amount = _input(f"    处罚金额 [{amount}元]: ").strip()
                if new_amount:
                    try:
                        case_data["penalty_amount"] = float(new_amount)
                    except ValueError:
                        pass

            reference = _input("  可借鉴话术 (可选): ").strip()
            if reference:
                case_data["reference_script"] = reference

            internal = _input("  内部金额测算 (可选，不对外导出): ").strip()
            if internal:
                case_data["internal_amount_analysis"] = internal

            contacts = _input("  敏感联系人 (可选，不对外导出): ").strip()
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
            _print()

        _print("=" * 60)
        _print(f"  导入完成: 成功 {imported_count} 个，失败 {failed_count} 个")
        _print("=" * 60)

        return {
            "success": True,
            "imported": imported_count,
            "failed": failed_count,
            "results": results
        }
