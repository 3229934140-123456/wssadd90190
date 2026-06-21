"""数据库模块 - SQLite存储层，管理处罚案例的CRUD操作"""

import sqlite3
import os
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple


class _BackwardCompatDict(dict):
    """支持 dict 访问和 tuple 解包的兼容类，用于 batch_update_from_csv"""

    def __init__(self, data: dict, legacy_tuple: Tuple):
        super().__init__(data)
        self._legacy_tuple = legacy_tuple

    def __iter__(self):
        return iter(self._legacy_tuple)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._legacy_tuple[key]
        return super().__getitem__(key)

    def __len__(self):
        return len(self._legacy_tuple)


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
                    external_penalty_no TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            try:
                cursor.execute("ALTER TABLE penalties ADD COLUMN external_penalty_no TEXT")
            except sqlite3.OperationalError:
                pass

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS case_tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id INTEGER NOT NULL,
                    tag TEXT NOT NULL,
                    FOREIGN KEY (case_id) REFERENCES penalties(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS saved_searches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    keywords TEXT,
                    company TEXT,
                    regulator TEXT,
                    business_line TEXT,
                    tags TEXT,
                    min_amount REAL,
                    max_amount REAL,
                    from_date TEXT,
                    to_date TEXT,
                    sort_by TEXT DEFAULT 'penalty_date',
                    sort_order TEXT DEFAULT 'desc',
                    created_at TEXT NOT NULL
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
                        case_no, external_penalty_no, company, regulator, business_line, tags,
                        penalty_date, penalty_amount, result_summary,
                        facts, defense_content, rectification_report,
                        reference_script, internal_amount_analysis,
                        sensitive_contacts, source_files, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    case_no,
                    case_data.get("external_penalty_no", ""),
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

    def search_keywords(self, keywords: Optional[List[str]] = None,
                        company: Optional[str] = None,
                        regulator: Optional[str] = None,
                        business_line: Optional[str] = None,
                        tags: Optional[List[str]] = None,
                        min_amount: Optional[float] = None,
                        max_amount: Optional[float] = None,
                        from_date: Optional[str] = None,
                        to_date: Optional[str] = None,
                        sort_by: str = "penalty_date",
                        sort_order: str = "desc",
                        limit: int = 50,
                        extract_snippets: bool = True) -> List[Dict]:
        """
        关键词搜索：在事实、申辩意见、整改报告、摘要、标签中模糊匹配
        支持多关键词（AND关系）、金额区间、日期范围、多标签筛选

        Args:
            keywords: 关键词列表（AND关系）
            company: 按公司过滤（模糊）
            regulator: 按监管部门过滤（模糊）
            business_line: 按业务线过滤（模糊）
            tags: 标签列表（AND关系，模糊匹配）
            min_amount: 最低处罚金额
            max_amount: 最高处罚金额
            from_date: 起始日期 YYYY-MM-DD
            to_date: 结束日期 YYYY-MM-DD
            sort_by: 排序字段 penalty_date/penalty_amount/created_at
            sort_order: 排序方向 asc/desc
            limit: 返回数量上限
            extract_snippets: 是否提取命中片段
        """
        keywords = keywords or []
        tags = tags or []
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
                     OR business_line LIKE ? OR external_penalty_no LIKE ?)
                """)
                params.extend([like_kw] * 11)
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

        if tags:
            for tag in tags:
                query_parts.append("""
                    id IN (SELECT case_id FROM case_tags WHERE tag LIKE ?)
                """)
                params.append(f"%{tag}%")

        if min_amount is not None:
            query_parts.append("penalty_amount >= ?")
            params.append(float(min_amount))

        if max_amount is not None:
            query_parts.append("penalty_amount <= ?")
            params.append(float(max_amount))

        if from_date:
            query_parts.append("penalty_date >= ?")
            params.append(from_date)

        if to_date:
            query_parts.append("penalty_date <= ?")
            params.append(to_date)

        where_clause = " AND ".join(query_parts) if query_parts else "1=1"

        sort_fields = {
            "penalty_date": "penalty_date",
            "penalty_amount": "penalty_amount",
            "created_at": "created_at",
            "company": "company",
        }
        sort_field = sort_fields.get(sort_by, "penalty_date")
        sort_dir = "DESC" if sort_order.lower() == "desc" else "ASC"

        params.append(limit)

        sql = f"""
            SELECT id, case_no, external_penalty_no, company, regulator, business_line, tags,
                   penalty_date, penalty_amount, result_summary,
                   facts, defense_content, rectification_report,
                   reference_script, created_at
            FROM penalties
            WHERE {where_clause}
            ORDER BY {sort_field} {sort_dir}, created_at DESC
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

                if extract_snippets and keywords:
                    item["snippets"] = self._extract_snippets(
                        item, keywords, max_snippets=3, snippet_length=80
                    )
                else:
                    item["snippets"] = []

                results.append(item)
            return results

    def _extract_snippets(self, case_data: Dict, keywords: List[str],
                          max_snippets: int = 3, snippet_length: int = 80) -> List[Dict]:
        """从案例文本中提取关键词命中片段"""
        import re

        search_fields = [
            ("违法事实", case_data.get("facts", "")),
            ("处理结果", case_data.get("result_summary", "")),
            ("申辩意见", case_data.get("defense_content", "")),
            ("整改报告", case_data.get("rectification_report", "")),
            ("可借鉴话术", case_data.get("reference_script", "")),
        ]

        snippets = []
        seen_positions = set()

        for field_name, content in search_fields:
            if not content:
                continue

            for kw in keywords:
                if not kw:
                    continue
                pattern = re.compile(re.escape(kw), re.IGNORECASE)
                for match in pattern.finditer(content):
                    start = max(0, match.start() - snippet_length // 2)
                    end = min(len(content), match.end() + snippet_length // 2)

                    snippet_key = (field_name, start // 20)
                    if snippet_key in seen_positions:
                        continue
                    seen_positions.add(snippet_key)

                    prefix = "..." if start > 0 else ""
                    suffix = "..." if end < len(content) else ""

                    snippet_text = prefix + content[start:end] + suffix
                    snippet_text = re.sub(r"\s+", " ", snippet_text).strip()

                    highlighted = snippet_text
                    for k in keywords:
                        highlighted = re.sub(
                            re.escape(k),
                            lambda m: f"『{m.group()}』",
                            highlighted,
                            flags=re.IGNORECASE
                        )

                    snippets.append({
                        "field": field_name,
                        "text": snippet_text,
                        "highlighted": highlighted,
                        "keyword": kw,
                    })

                    if len(snippets) >= max_snippets:
                        return snippets

        return snippets

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
            SELECT id, case_no, external_penalty_no, company, regulator, business_line, tags,
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
                SELECT id, case_no, external_penalty_no, company, regulator, business_line, tags,
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

    # ========== 保存的检索条件 ==========

    def save_search(self, name: str, description: str = "",
                    keywords: Optional[List[str]] = None,
                    company: Optional[str] = None,
                    regulator: Optional[str] = None,
                    business_line: Optional[str] = None,
                    tags: Optional[List[str]] = None,
                    min_amount: Optional[float] = None,
                    max_amount: Optional[float] = None,
                    from_date: Optional[str] = None,
                    to_date: Optional[str] = None,
                    sort_by: str = "penalty_date",
                    sort_order: str = "desc") -> Tuple[bool, str]:
        """保存检索条件"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        keywords_json = json.dumps(keywords or [], ensure_ascii=False)
        tags_json = json.dumps(tags or [], ensure_ascii=False)

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO saved_searches
                    (name, description, keywords, company, regulator, business_line,
                     tags, min_amount, max_amount, from_date, to_date,
                     sort_by, sort_order, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (name, description, keywords_json, company, regulator,
                      business_line, tags_json, min_amount, max_amount,
                      from_date, to_date, sort_by, sort_order, now))
                conn.commit()
                return True, f"检索条件 '{name}' 已保存"
        except Exception as e:
            return False, f"保存失败: {e}"

    def load_search(self, name: str) -> Optional[Dict]:
        """按名称加载保存的检索条件"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM saved_searches WHERE name = ?", (name,))
            row = cursor.fetchone()
            if not row:
                return None
            data = dict(row)
            for field in ["keywords", "tags"]:
                if data.get(field):
                    try:
                        data[field] = json.loads(data[field])
                    except:
                        data[field] = []
            return data

    def list_saved_searches(self) -> List[Dict]:
        """列出所有保存的检索条件"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM saved_searches ORDER BY created_at DESC")
            rows = cursor.fetchall()
            results = []
            for row in rows:
                data = dict(row)
                for field in ["keywords", "tags"]:
                    if data.get(field):
                        try:
                            data[field] = json.loads(data[field])
                        except:
                            data[field] = []
                results.append(data)
            return results

    def delete_saved_search(self, name: str) -> bool:
        """删除保存的检索条件"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM saved_searches WHERE name = ?", (name,))
                conn.commit()
                return cursor.rowcount > 0
        except:
            return False

    # ========== 相似案例查找 ==========

    def find_similar_cases(self, case_id: int, limit: int = 10) -> List[Dict]:
        """
        查找与目标案例相似的其他案例

        评分维度：
        - 标签重叠分：Jaccard 相似度（0-3分，若目标无标签则跳过）
        - 监管部门匹配：完全相同 +3 分，部分包含 +1 分
        - 金额相似度：1 - |a-b|/max(|a|,|b|,1)，取 0-3 分
        - 事实关键词重叠：facts 中文2字以上词的 Jaccard，取 0-3 分

        Returns:
            按总分倒序的案例列表，每项包含：id, case_no, company, regulator,
            penalty_amount, score, reasons
            只返回 score > 0 且 reasons 非空的案例。
        """
        import re

        target = self.get_case_by_id(case_id)
        if not target:
            return []

        target_tags = set(target.get("tags") or [])
        target_regulator = (target.get("regulator") or "").strip()
        target_amount = float(target.get("penalty_amount") or 0)
        target_facts = target.get("facts") or ""

        def _fmt_amount_wan(amount: float) -> str:
            return f"{amount / 10000:.1f}"

        def _extract_chinese_words(text: str) -> set:
            if not text:
                return set()
            return set(re.findall(r"[\u4e00-\u9fa5]{2,}", text))

        target_fact_words = _extract_chinese_words(target_facts)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, case_no, company, regulator, tags, penalty_amount, facts
                FROM penalties
                WHERE id != ?
            """, (case_id,))
            rows = cursor.fetchall()

        scored = []
        for row in rows:
            item = dict(row)
            case_tags = set()
            if item.get("tags"):
                try:
                    case_tags = set(json.loads(item["tags"]))
                except:
                    pass
            case_regulator = (item.get("regulator") or "").strip()
            case_amount = float(item.get("penalty_amount") or 0)
            case_facts = item.get("facts") or ""
            case_fact_words = _extract_chinese_words(case_facts)

            total_score = 0.0
            reasons = []

            if target_tags:
                tag_inter = target_tags & case_tags
                tag_union = target_tags | case_tags
                if tag_union:
                    tag_jaccard = len(tag_inter) / len(tag_union)
                    tag_score = tag_jaccard * 3
                    total_score += tag_score
                    if tag_score > 0:
                        similar_tags = ", ".join(sorted(tag_inter)[:3])
                        reasons.append(f"[标签] 相似标签：{similar_tags}，得分 +{tag_score:.1f}")

            if target_regulator and case_regulator:
                if target_regulator == case_regulator:
                    total_score += 3
                    reasons.append("[部门] 相同监管部门，得分 +3")
                elif target_regulator in case_regulator or case_regulator in target_regulator:
                    total_score += 1
                    reasons.append("[部门] 相关监管部门，得分 +1")

            denom = max(abs(target_amount), abs(case_amount), 1)
            amount_sim = 1 - abs(target_amount - case_amount) / denom
            amount_sim = max(0.0, min(1.0, amount_sim))
            amount_score = amount_sim * 3
            total_score += amount_score
            if amount_score > 0.5:
                reasons.append(
                    f"[金额] 金额相近（目标{_fmt_amount_wan(target_amount)}万 vs "
                    f"当前{_fmt_amount_wan(case_amount)}万），得分 +{amount_score:.1f}"
                )

            if target_fact_words and case_fact_words:
                word_inter = target_fact_words & case_fact_words
                word_union = target_fact_words | case_fact_words
                if word_union:
                    word_jaccard = len(word_inter) / len(word_union)
                    word_score = word_jaccard * 3
                    total_score += word_score
                    if word_score > 0:
                        keywords = ", ".join(sorted(word_inter)[:3])
                        reasons.append(f"[事实] 关键词重叠：{keywords}，得分 +{word_score:.1f}")

            has_non_amount_reason = any(
                r.startswith(("[标签]", "[部门]", "[事实]")) for r in reasons
            )
            both_amount_negligible = target_amount <= 1 and case_amount <= 1
            if both_amount_negligible and not has_non_amount_reason:
                continue

            if total_score >= 1.5 and len(reasons) >= 1:
                scored.append({
                    "id": item["id"],
                    "case_no": item.get("case_no", ""),
                    "company": item.get("company", ""),
                    "regulator": case_regulator,
                    "penalty_amount": case_amount,
                    "score": round(total_score, 2),
                    "reasons": reasons,
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    # ========== 批量从CSV更新 ==========

    def batch_update_from_csv(self, csv_path: str):
        """
        读取CSV，根据 case_no 查找案例，对每行非空的 *_new 列更新对应字段

        映射关系：
          penalty_date_new   -> penalty_date
          penalty_amount_new -> penalty_amount
          facts_new          -> facts
          tags_new           -> tags（逗号分隔）

        Returns:
            dict: {
                "updated": [{"case_no": ..., "updated_fields": ["penalty_date", ...]}],
                "skipped": [{"row_num": ..., "case_no": ..., "reason": ...}],
                "updated_count": N,
                "skipped_count": M,
                "errors": [str]
            }
            同时支持 tuple 解包：(updated_count, errors) 以兼容旧代码
        """
        import csv

        result = {
            "updated": [],
            "skipped": [],
            "updated_count": 0,
            "skipped_count": 0,
            "errors": [],
        }

        if not os.path.exists(csv_path):
            result["errors"].append(f"CSV 文件不存在: {csv_path}")
            return _BackwardCompatDict(result, (result["updated_count"], result["errors"]))

        field_mapping = {
            "penalty_date_new": "penalty_date",
            "penalty_amount_new": "penalty_amount",
            "facts_new": "facts",
            "tags_new": "tags",
        }

        field_label = {
            "penalty_date": "处罚日期",
            "penalty_amount": "处罚金额",
            "facts": "事实正文",
            "tags": "标签",
        }

        try:
            with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row_num, row in enumerate(reader, start=2):
                    case_no = (row.get("case_no") or "").strip()
                    if not case_no:
                        result["skipped"].append({
                            "row_num": row_num,
                            "case_no": "",
                            "reason": "case_no 为空",
                        })
                        result["skipped_count"] += 1
                        continue

                    case = self.get_case_by_no(case_no)
                    if not case:
                        result["skipped"].append({
                            "row_num": row_num,
                            "case_no": case_no,
                            "reason": "未找到案例",
                        })
                        result["skipped_count"] += 1
                        continue

                    updates = {}
                    updated_fields_display = []
                    for csv_col, db_field in field_mapping.items():
                        val = row.get(csv_col)
                        if val is None:
                            continue
                        val = str(val).strip()
                        if not val:
                            continue
                        if db_field == "penalty_amount":
                            try:
                                val_clean = val.replace(",", "").replace("元", "")
                                if val_clean.endswith("万"):
                                    updates[db_field] = float(val_clean[:-1]) * 10000
                                else:
                                    updates[db_field] = float(val_clean)
                                updated_fields_display.append(field_label.get(db_field, db_field))
                            except ValueError:
                                result["errors"].append(f"第 {row_num} 行 ({case_no}): 金额格式错误 '{val}'，跳过该字段")
                                continue
                        elif db_field == "tags":
                            updates[db_field] = [t.strip() for t in val.replace("，", ",").split(",") if t.strip()]
                            updated_fields_display.append(field_label.get(db_field, db_field))
                        else:
                            updates[db_field] = val
                            updated_fields_display.append(field_label.get(db_field, db_field))

                    if updates:
                        self._update_case_fields_internal(case["id"], updates)
                        result["updated"].append({
                            "case_no": case_no,
                            "updated_fields": updated_fields_display,
                        })
                        result["updated_count"] += 1
                    else:
                        result["skipped"].append({
                            "row_num": row_num,
                            "case_no": case_no,
                            "reason": "未填写任何更新字段",
                        })
                        result["skipped_count"] += 1
        except Exception as e:
            result["errors"].append(f"读取 CSV 失败: {e}")

        return _BackwardCompatDict(result, (result["updated_count"], result["errors"]))

    def _update_case_fields_internal(self, case_id: int, updates: dict):
        """内部方法：更新案例字段（与 main.py 中 _update_case_fields 类似）"""
        import json as json_mod
        from datetime import datetime

        set_parts = []
        params = []

        for field, value in updates.items():
            if field == "tags":
                if isinstance(value, list):
                    tags_json = json_mod.dumps(value, ensure_ascii=False)
                    set_parts.append("tags = ?")
                    params.append(tags_json)
                    with self._get_connection() as conn:
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
        params.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        params.append(case_id)

        sql = f"UPDATE penalties SET {', '.join(set_parts)} WHERE id = ?"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()

    # ========== 资料库健康检查 ==========

    def health_check(self) -> Dict:
        """检查资料库中数据完整性，返回缺失字段统计"""
        issues = {
            "missing_date": [],
            "missing_amount": [],
            "missing_facts": [],
            "missing_tags": [],
            "summary": {},
        }

        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, case_no, company, regulator FROM penalties
                WHERE penalty_date IS NULL OR penalty_date = ''
            """)
            for row in cursor.fetchall():
                issues["missing_date"].append(dict(row))

            cursor.execute("""
                SELECT id, case_no, company, regulator FROM penalties
                WHERE penalty_amount IS NULL OR penalty_amount = 0
            """)
            for row in cursor.fetchall():
                issues["missing_amount"].append(dict(row))

            cursor.execute("""
                SELECT id, case_no, company, regulator FROM penalties
                WHERE facts IS NULL OR facts = ''
            """)
            for row in cursor.fetchall():
                issues["missing_facts"].append(dict(row))

            cursor.execute("""
                SELECT id, case_no, company, regulator FROM penalties
                WHERE tags IS NULL OR tags = '' OR tags = '[]'
            """)
            for row in cursor.fetchall():
                issues["missing_tags"].append(dict(row))

            cursor.execute("SELECT COUNT(*) as total FROM penalties")
            total = cursor.fetchone()["total"]

        issues["summary"] = {
            "total_cases": total,
            "missing_date_count": len(issues["missing_date"]),
            "missing_amount_count": len(issues["missing_amount"]),
            "missing_facts_count": len(issues["missing_facts"]),
            "missing_tags_count": len(issues["missing_tags"]),
        }

        return issues
