"""工具函数模块"""

import os
import re
from typing import List, Optional


SUPPORTED_EXTENSIONS = [".txt", ".md", ".docx", ".pdf"]


def scan_document_folder(folder_path: str) -> List[str]:
    """扫描文件夹中的文档文件"""
    if not os.path.isdir(folder_path):
        raise FileNotFoundError(f"文件夹不存在: {folder_path}")

    files = []
    for root, _, filenames in os.walk(folder_path):
        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext in SUPPORTED_EXTENSIONS:
                files.append(os.path.join(root, filename))

    return sorted(files)


def read_text_file(file_path: str) -> str:
    """读取纯文本文件（.txt, .md）"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, "r", encoding="gbk") as f:
                return f.read()
        except:
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
            except Exception as e:
                return f"[读取失败: {str(e)}]"


def extract_amount_from_text(text: str) -> Optional[float]:
    """从文本中尝试提取罚款金额"""
    patterns = [
        (r"罚[：:\s]*([\d,\.]+)\s*(万)?元", True),
        (r"处罚金额[：:\s]*([\d,\.]+)\s*(万)?元", True),
        (r"没收违法所得[：:\s]*([\d,\.]+)\s*(万)?元", True),
        (r"合计[：:\s]*([\d,\.]+)\s*(万)?元", True),
        (r"共计[：:\s]*([\d,\.]+)\s*(万)?元", True),
        (r"([\d,\.]+)\s*(万)?元", False),
    ]

    for pattern, is_penalty in patterns:
        matches = re.findall(pattern, text)
        if matches:
            try:
                for match in reversed(matches):
                    num_str = match[0].replace(",", "")
                    if not num_str or num_str == '.':
                        continue
                    value = float(num_str)
                    if len(match) > 1 and match[1] == "万":
                        value = value * 10000
                    if value > 0:
                        return value
            except (ValueError, IndexError):
                continue
    return None


def generate_summary(text: str, max_length: int = 300) -> str:
    """从文档中自动生成摘要"""
    if not text:
        return ""

    clean_text = re.sub(r"\s+", " ", text).strip()

    if len(clean_text) <= max_length:
        return clean_text

    sentences = re.split(r"[。！？；\n]", clean_text)
    sentences = [s.strip() for s in sentences if s.strip()]

    summary = []
    current_length = 0
    for sentence in sentences:
        if current_length + len(sentence) + 1 <= max_length:
            summary.append(sentence)
            current_length += len(sentence) + 1
        else:
            break

    result = "。".join(summary)
    if result and not result.endswith(("。", "！", "？")):
        result += "。"
    return result + "..."


def parse_input_list(input_str: str, separator: str = ",") -> List[str]:
    """解析输入的列表字符串（支持逗号、分号、空格分隔）"""
    if not input_str or not input_str.strip():
        return []

    parts = re.split(r"[,，;；\s]+", input_str.strip())
    return [p.strip() for p in parts if p.strip()]


def format_amount(amount: float) -> str:
    """格式化金额显示"""
    if not amount:
        return "0元"

    if amount >= 10000:
        wan = amount / 10000
        if wan == int(wan):
            return f"{int(wan)}万元"
        return f"{wan:.2f}万元"
    return f"{int(amount)}元"


def mask_sensitive_info(text: str) -> str:
    """简单脱敏：隐藏手机号、邮箱、身份证号等"""
    if not text:
        return ""

    text = re.sub(r"1[3-9]\d{9}", "1**********", text)
    text = re.sub(r"[\w.-]+@[\w.-]+\.\w+", "***@***.***", text)
    text = re.sub(r"\d{17}[\dXx]", "******************", text)
    text = re.sub(r"\d{15}", "***************", text)

    return text
