"""Compare user-supplied observations; does not access or scrape Amazon."""

import argparse
import csv
import hashlib
import io
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


class SnapshotError(ValueError):
    pass


KEY = ("marketplace", "asin", "variant", "delivery_region")
REQUIRED = (*KEY, "currency", "price_basis", "observed_at", "url", "source_type")
SOURCE_TYPES = {"observed_public", "user_provided", "third_party_estimate", "synthetic"}


def numeric(value, field):
    if value == "":
        return None
    try:
        result = Decimal(value)
        if not result.is_finite() or result < 0:
            raise InvalidOperation
        if field in ("review_count", "bsr") and result != result.to_integral_value():
            raise InvalidOperation
        if field == "rating" and result > 5:
            raise InvalidOperation
        return result
    except InvalidOperation as exc:
        raise SnapshotError(f"{field} 数值无法识别：{value}") from exc


def load(path):
    content = path.read_bytes()
    if len(content) > 20 * 1024 * 1024:
        raise SnapshotError("快照超过 20 MB，请缩小范围。")
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    if not set(REQUIRED).issubset(reader.fieldnames or []):
        raise SnapshotError("缺少快照必填列，请使用 assets/competitor-snapshot.csv 模板。")
    rows = {}
    for row in reader:
        if None in row or any(v is None for v in row.values()):
            raise SnapshotError("CSV 列数不一致，请核对逗号和引号。")
        row = {k: v.strip() for k, v in row.items()}
        if any(not row[k] for k in REQUIRED):
            raise SnapshotError("快照关键字段有空白，不能猜测变体、地区、观察时间或来源。")
        if not re.fullmatch(r"[A-Z0-9]{10}", row["asin"]):
            raise SnapshotError(f"ASIN 格式不正确：{row['asin']}")
        if not re.fullmatch(r"[A-Z]{3}", row["currency"]):
            raise SnapshotError("币种须为三个大写字母。")
        if row["source_type"] not in SOURCE_TYPES:
            raise SnapshotError("source_type 无法识别。")
        if not row["url"].startswith(("https://", "http://")):
            raise SnapshotError("来源须为 HTTP/HTTPS 链接。")
        try:
            stamp = datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00"))
            if stamp.utcoffset() is None:
                raise ValueError("missing timezone")
        except ValueError as exc:
            raise SnapshotError("观察时间须为带时区的 ISO 时间。") from exc
        row["_time"] = stamp
        for field in ("price", "rating", "review_count", "bsr"):
            row[field] = numeric(row.get(field, ""), field)
        key = tuple(row[k] for k in KEY)
        if key in rows:
            raise SnapshotError("同一快照有重复站点/ASIN/变体/地区，请先确定单次观察记录。")
        rows[key] = row
    if not rows:
        raise SnapshotError("快照只有表头，没有观察记录。")
    return rows, hashlib.sha256(content).hexdigest()


def compare(before, after):
    events = []
    for key in sorted(before.keys() | after.keys()):
        identity = dict(zip(KEY, key, strict=True))
        old, new = before.get(key), after.get(key)
        if old is None or new is None:
            record = new or old
            events.append({**identity, "status": "新增观察对象" if old is None else "未复查到", "changes": [],
                           "observed_at": record["observed_at"], "url": record["url"],
                           "source_type": record["source_type"], "note": "不代表新品上市、下架或售罄"})
            continue
        if new["_time"] <= old["_time"]:
            raise SnapshotError("后快照观察时间必须晚于前快照。")
        changes = []
        same_price = old["currency"] == new["currency"] and old["price_basis"] == new["price_basis"]
        same_bsr = bool(old.get("bsr_category")) and old.get("bsr_category") == new.get("bsr_category")
        for field in ("price", "availability", "title", "main_image_url", "rating", "review_count", "bsr", "coupon_text"):
            previous, current = old.get(field), new.get(field)
            if field == "price" and not same_price:
                changes.append({"field": "price", "status": "不可比：币种或价格口径不同"})
            elif field == "bsr" and not same_bsr and (previous is not None or current is not None):
                changes.append({"field": "bsr", "status": "不可比：类目缺失或不同"})
            elif current in (None, "") or previous in (None, ""):
                if current != previous:
                    changes.append({"field": field, "status": "信息缺失，不能确认变化"})
            elif previous != current:
                change = {"field": field, "before": str(previous), "after": str(current), "status": "记录变化"}
                if field == "price":
                    change["difference"] = str(current - previous)
                changes.append(change)
        events.append({**identity, "status": "存在变化或可比性问题" if changes else "已提供字段未见变化", "changes": changes,
                       "before_observed_at": old["observed_at"], "after_observed_at": new["observed_at"],
                       "before_url": old["url"], "after_url": new["url"],
                       "before_source_type": old["source_type"], "after_source_type": new["source_type"]})
    return events


def main(argv=None):
    parser = argparse.ArgumentParser(description="比较已提供的竞品快照，不抓取网页、不估算销量")
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output_dir.exists():
        parser.error("输出目录已存在，请换新目录。")
    try:
        before, old_hash = load(args.before)
        after, new_hash = load(args.after)
        result = {"sources": [{"file": args.before.name, "sha256": old_hash},
                              {"file": args.after.name, "sha256": new_hash}],
                  "scope": "仅比较用户提供记录；来源和真实性未由脚本认证", "events": compare(before, after)}
        args.output_dir.mkdir(parents=True, exist_ok=False)
        output = args.output_dir / "changes.json"
        with output.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
        print(json.dumps({"status": "ok", "output": str(output.resolve())}, ensure_ascii=False))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"未生成完整结果：{exc}\n")


if __name__ == "__main__":
    main()
