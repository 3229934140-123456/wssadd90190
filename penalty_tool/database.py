"""数据库模块 - SQLite存储层，管理处罚案例的CRUD操作"""

import sqlite3
import os
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple


class PenaltyDatabase:
    """处罚案例数据库管理类"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "penalty.db")

        self.db_path = db_path
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_database(self):
        """初始化数据库表结构"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS penalties (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_no TEXT UNIQUE NOT NULL,
                    company TEXT NOT NULL,
                    regulator TEXT NOT NULL,
                    business_line TEXT,
                    tags TEXT,
                    penalty_date TEXT,
                    penalty_amount REAL DEFAULT 0,
                    result_summary TEXT,
                    facts TEXT,
                    defense_content TEXT,
                    rectification_report TEXT,
                    reference_script TEXT,
                    internal_amount_analysis TEXT,
                    sensitive_contacts TEXT,
                    source_files TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS case_tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id INTEGER NOT NULL,
                    tag TEXT NOT NULL,
                    FOREIGN KEY (case_id) REFERENCES penalties(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_penalties_company ON penalties(company)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_penalties_regulator ON penalties(regulator)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_penalties_business_line ON penalties(business_line)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_case_tags_tag ON case_tags(tag)")

            conn.commit()

    def _generate_case_no(self, company: str, year: str) -> str:
        """生成案例编号：公司缩写-年份-序号"""
        company_short = "".join([c for c in company if c.isalnum()])[:4].upper()
        if not company_short:
            company_short = "CASE"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM penalties WHERE case_no LIKE ?",
                (f"{company_short}-{year}-%",)
            )
            count = cursor.fetchone()["cnt"] + 1
            return f"{company_short}-{year}-{count:04d}"

    def insert_case(self, case_data: Dict) -> Tuple[bool, str, str]:
        """
        插入新案例
        Returns: (成功状态, 案例编号, 消息)
        """
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            year = case_data.get("penalty_date", now[:4])[:4]
            case_no = case_data.get("case_no") or self._generate_case_no(
                case_data.get("company", "UNKNOWN"), year
            )

            tags = case_data.get("tags") or []
            if isinstance(tags, list):
                tags_json = json.dumps(tags, ensure_ascii=False)
            else:
                tags_json = tags
                tags = [t.strip() for t in tags.split(",") if t.strip()]

            source_files = case_data.get("source_files") or []
            if isinstance(source_files, list):
                source_files_json = json.dumps(source_files, ensure_ascii=False)
            else:
                source_files_json = json.dumps([source_files], ensure_ascii=False)

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO penalties (
                        case_no, company, regulator, business_line, tags,
                        penalty_date, penalty_amount, result_summary,
                        facts, defense_content, rectification_report,
                        reference_script, internal_amount_analysis,
                        sensitive_contacts, source_files, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    case_no,
                    case_data.get("company", ""),
                    case_data.get("regulator", ""),
                    case_data.get("business_line", ""),
                    tags_json,
                    case_data.get("penalty_date", ""),
                    float(case_data.get("penalty_amount", 0) or 0),
                    case_data.get("result_summary", ""),
                    case_data.get("facts", ""),
                    case_data.get("defense_content", ""),
                    case_data.get("rectification_report", ""),
                    case_data.get("reference_script", ""),
                    case_data.get("internal_amount_analysis", ""),
                    case_data.get("sensitive_contacts", ""),
                    source_files_json,
                    now, now
                ))

                case_id = cursor.lastrowid
                for tag in tags:
                    cursor.execute(
                        "INSERT INTO case_tags (case_id, tag) VALUES (?, ?)",
                        (case_id, tag)
                    )

                conn.commit()
                return True, case_no, f"案例 {case_no} 导入成功"

        except sqlite3.IntegrityError:
            return False, "", f"案例编号重复或数据不完整"
        except Exception as e:
            return False, "", f"导入失败: {str(e)}"

    def search_keywords(self, keywords: List[str],
                        company: Optional[str] = None,
                        regulator: Optional[str] = None,
                        business_line: Optional[str] = None,
                        tag: Optional[str] = None,
                        limit: int = 50) -> List[Dict]:
        """
        关键词搜索：在事实、申辩意见、整改报告、摘要、标签中模糊匹配
        支持多关键词（AND关系）
        """
        query_parts = []
        params = []

        if keywords:
            keyword_conditions = []
            for kw in keywords:
                like_kw = f"%{kw}%"
                keyword_conditions.append("""
                    (facts LIKE ? OR defense_content LIKE ? OR rectification_report LIKE ?
                     OR result_summary LIKE ? OR reference_script LIKE ? OR tags LIKE ?
                     OR case_no LIKE ? OR company LIKE ? OR regulator LIKE ?
                     OR business_line LIKE ?)
                """)
                params.extend([like_kw] * 10)
            query_parts.append("(" + " AND ".join(keyword_conditions) + ")")

        if company:
            query_parts.append("company LIKE ?")
            params.append(f"%{company}%")

        if regulator:
            query_parts.append("regulator LIKE ?")
            params.append(f"%{regulator}%")

        if business_line:
            query_parts.append("business_line LIKE ?")
            params.append(f"%{business_line}%")

        if tag:
            query_parts.append("""
                id IN (SELECT case_id FROM case_tags WHERE tag LIKE ?)
            """)
            params.append(f"%{tag}%")

        where_clause = " AND ".join(query_parts) if query_parts else "1=1"
        params.append(limit)

        sql = f"""
            SELECT id, case_no, company, regulator, business_line, tags,
                   penalty_date, penalty_amount, result_summary,
                   facts, reference_script, created_at
            FROM penalties
            WHERE {where_clause}
            ORDER BY penalty_date DESC, created_at DESC
            LIMIT ?
        """

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            results = []
            for row in rows:
                item = dict(row)
                if item.get("tags"):
                    try:
                        item["tags"] = json.loads(item["tags"])
                    except:
                        item["tags"] = []
                results.append(item)
            return results

    def get_case_by_id(self, case_id: int) -> Optional[Dict]:
        """根据ID获取完整案例信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM penalties WHERE id = ?", (case_id,))
            row = cursor.fetchone()
            if row:
                data = dict(row)
                for field in ["tags", "source_files"]:
                    if data.get(field):
                        try:
                            data[field] = json.loads(data[field])
                        except:
                            pass
                return data
        return None

    def get_case_by_no(self, case_no: str) -> Optional[Dict]:
        """根据案例编号获取完整案例信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM penalties WHERE case_no = ?", (case_no,))
            row = cursor.fetchone()
            if row:
                data = dict(row)
                for field in ["tags", "source_files"]:
                    if data.get(field):
                        try:
                            data[field] = json.loads(data[field])
                        except:
                            pass
                return data
        return None

    def get_cases_export(self, case_ids: List[int]) -> List[Dict]:
        """获取用于导出的案例数据（简版，自动脱敏）"""
        placeholders = ",".join(["?"] * len(case_ids))
        sql = f"""
            SELECT id, case_no, company, regulator, business_line, tags,
                   penalty_date, penalty_amount, result_summary,
                   facts, defense_content, rectification_report,
                   reference_script
            FROM penalties
            WHERE id IN ({placeholders})
            ORDER BY penalty_date DESC
        """

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, case_ids)
            rows = cursor.fetchall()
            results = []
            for row in rows:
                data = dict(row)
                if data.get("tags"):
                    try:
                        data["tags"] = json.loads(data["tags"])
                    except:
                        data["tags"] = []
                results.append(data)
        return results

    def list_all_cases(self, limit: int = 100) -> List[Dict]:
        """列出所有案例"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, case_no, company, regulator, business_line, tags,
                       penalty_date, penalty_amount, result_summary, created_at
                FROM penalties
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            results = []
            for row in rows:
                item = dict(row)
                if item.get("tags"):
                    try:
                        item["tags"] = json.loads(item["tags"])
                    except:
                        item["tags"] = []
                results.append(item)
            return results

    def list_companies(self) -> List[str]:
        """列出所有公司"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT company FROM penalties ORDER BY company")
            return [row["company"] for row in cursor.fetchall()]

    def list_regulators(self) -> List[str]:
        """列出所有监管部门"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT regulator FROM penalties ORDER BY regulator")
            return [row["regulator"] for row in cursor.fetchall()]

    def list_business_lines(self) -> List[str]:
        """列出所有业务线"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT DISTINCT business_line FROM penalties WHERE business_line IS NOT NULL AND business_line != '' ORDER BY business_line"
            )
            return [row["business_line"] for row in cursor.fetchall()]

    def list_tags(self) -> List[str]:
        """列出所有标签"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT tag FROM case_tags ORDER BY tag")
            return [row["tag"] for row in cursor.fetchall()]

    def delete_case(self, case_id: int) -> bool:
        """删除案例"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM case_tags WHERE case_id = ?", (case_id,))
                cursor.execute("DELETE FROM penalties WHERE id = ?", (case_id,))
                conn.commit()
                return True
        except:
            return False

    def get_stats(self) -> Dict:
        """获取数据库统计信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as total FROM penalties")
            total = cursor.fetchone()["total"]

            cursor.execute("SELECT COALESCE(SUM(penalty_amount), 0) as total_amount FROM penalties")
            total_amount = cursor.fetchone()["total_amount"]

            cursor.execute("SELECT COUNT(DISTINCT company) as cnt FROM penalties")
            company_count = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(DISTINCT regulator) as cnt FROM penalties")
            regulator_count = cursor.fetchone()["cnt"]

            return {
                "total_cases": total,
                "total_penalty_amount": total_amount,
                "company_count": company_count,
                "regulator_count": regulator_count,
            }
