"""Build the V6 second-round auditable SFT release from frozen local evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "auditable-sft/6.0-second-round"
RELEASE_VERSION = "6.0.0-second-round"
CLOSED_ROLES = {
    "evidence_confirmation",
    "evidence_boundary",
    "bounded_impact",
    "cross_chain_synthesis",
}


def jline(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def read_json(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"{path}: expected JSON array")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(jline(row) + "\n" for row in rows), encoding="utf-8")


def message(record: dict[str, Any], role: str) -> dict[str, Any]:
    return next(row for row in record["messages"] if row["role"] == role)


def snapshot_record(
    root: Path, digest: str, suffix: str, retrieved_at: str
) -> dict[str, str]:
    rel = Path("exports/v6-second-round/acquisition/snapshots") / f"{digest}{suffix}"
    path = root / rel
    if not path.exists():
        raise FileNotFoundError(path)
    return {
        "snapshot_path": rel.as_posix(),
        "snapshot_sha256": digest,
        "retrieved_at": retrieved_at,
    }


def verbatim_excerpt(root: Path, digest: str, suffix: str, locator: str, hint: str) -> str:
    extracted = root / "exports/v6-second-round/acquisition/snapshots" / f"{digest}{suffix}.txt"
    text = extracted.read_text(encoding="utf-8")
    pattern = re.compile(r"^\[([^\]]+)\]\r?\n(.*?)(?=\r?\n\r?\n\[|\Z)", re.M | re.S)
    blocks = {key: re.sub(r"\s+", " ", value).strip() for key, value in pattern.findall(text)}
    if locator not in blocks:
        raise ValueError(f"{digest}: locator not found: {locator}")
    block = blocks[locator]
    at = block.find(hint)
    if at < 0:
        raise ValueError(f"{digest} {locator}: hint not found: {hint}")
    start = max(0, at - 120)
    end = min(len(block), at + len(hint) + 330)
    return block[start:end].strip()


def evidence_specs(root: Path) -> list[dict[str, Any]]:
    acq = read_jsonl(root / "exports/v6-second-round/acquisition/acquisition_records.jsonl")
    acq += read_jsonl(root / "exports/v6-second-round/acquisition/expansion_acquisition_records.jsonl")
    retrieved: dict[str, str] = {}
    for row in acq:
        if row.get("acquisition_status") == "ACQUIRED" and row.get("snapshot_sha256"):
            retrieved.setdefault(row["snapshot_sha256"], row["retrieved_at"])

    sources = {
        "ZHAOWEI": ("SRC-V6R2-ZHAOWEI-CSRC", "https://www.csrc.gov.cn/csrc/c101928/c1042604/content.shtml", "中国证券监督管理委员会", "2018-04-11T00:00:00+08:00", "T1", "496278120f5b7d6cf944e37eedbc64f5ffd644ed845716029db9c9fdc5bbb8a1", ".html"),
        "ZHANGZIDAO": ("SRC-V6R2-ZHANGZIDAO-CSRC", "https://www.csrc.gov.cn/csrc/c100028/c1000756/content.shtml", "中国证券监督管理委员会", "2020-06-24T00:00:00+08:00", "T1", "fd8ffa683315449ac55e8c936390ec81e23c73fac6b916179b95d375dede4b34", ".html"),
        "KANGDE": ("SRC-V6R2-KANGDE-CSRC", "https://www.csrc.gov.cn/csrc/c101928/c1042302/content.shtml", "中国证券监督管理委员会", "2020-09-24T00:00:00+08:00", "T1", "4fae13599f4f0d5bd016ea058cd1c96dae1c3a3bdd70b2eeb16e92c46709a7c5", ".html"),
        "SILVER": ("SRC-V6R2-SILVER-CFTC", "https://www.cftc.gov/PressRoom/SpeechesTestimony/proposedrule011410_berkovitz", "U.S. Commodity Futures Trading Commission", "2010-01-14T00:00:00-05:00", "T1", "c291181cae7d99b86719f530ada700b413ac6b1f2a7fa014e9256f35468e8935", ".html"),
        "LEHUA_CRASH": ("SRC-V6R2-LEHUA-CRASH-HKEX", "https://www1.hkexnews.hk/listedco/listconews/sehk/2024/0116/2024011600602.pdf", "YH Entertainment Group / HKEXnews", "2024-01-16T00:00:00+08:00", "T2", "f38d19cb24e5da3fd55d81350b69300c37082d1b650dd6f3c74c52ea72ee3114", ".pdf"),
        "LEHUA_PROSPECTUS": ("SRC-V6R2-LEHUA-PROSPECTUS-HKEX", "https://www1.hkexnews.hk/listedco/listconews/sehk/2022/0824/2022082400017.pdf", "YH Entertainment Group / HKEXnews", "2022-08-24T00:00:00+08:00", "T2", "ed2bb75449cf7daff1cab0e91230649df0ff40861bccc18353f631ea2969ab58", ".pdf"),
        "LEHUA_INTERIM": ("SRC-V6R2-LEHUA-INTERIM-HKEX", "https://www.hkexnews.hk/listedco/listconews/sehk/2023/0830/2023083002666.pdf", "YH Entertainment Group / HKEXnews", "2023-08-30T00:00:00+08:00", "T2", "66af891246a169f43995618c07bfadd9f965f05075a896d9c47e667553bb2e07", ".pdf"),
        "XIAOMI": ("SRC-V6R2-XIAOMI-AR2018", "https://ir.mi.com/system/files-encrypted/nasdaq_kms/assets/2021/07/27/4-59-41/2018%20AR.pdf", "Xiaomi Corporation", "2019-03-19T00:00:00+08:00", "T2", "fc14972b130b23ff0cbfa10de174c2435b9bdec2242eed6470758364866f9744", ".pdf"),
        "PORSCHE": ("SRC-V6R2-PORSCHE-2024", "https://newsroom.porsche.com/en/2025/company/porsche-deliveries-2024-38358.html", "Porsche AG", "2025-01-13T00:00:00+01:00", "T2", "c3d7b3f74984e696e231557e1490566df1a563a8af4c139a8c2688943a4ff1f0", ".html"),
        "SSE": ("SRC-V6R2-SSE-STAR-7Y", "https://www.sse.com.cn/cpc/cpctheme/4th20thcpc/4th20thcpcgcxx/c/c_20251110_10797697.shtml", "上海证券交易所", "2025-11-05T00:00:00+08:00", "T1", "543d31baef0c984170fcf6d3b3a1a963942063b78f99a9c63ef3e6f274921d43", ".html"),
        "BAILI": ("SRC-V6R2-BAILITIANHENG-AR2024", "http://static.cninfo.com.cn/finalpage/2025-03-29/1222948012.PDF", "四川百利天恒药业股份有限公司 / 巨潮资讯", "2025-03-29T00:00:00+08:00", "T2", "a8073ca9f8a7c971946fd1887ea1b3c3ddf912198d4786a87c983b2c49911f38", ".pdf"),
    }

    raw = [
        ("EV-V6R2-ZHAOWEI-01", "CASE-V5-ZHAOWEI", "ZHAOWEI", "html_block:17", "2016年12月23日，万家集团与龙薇传媒签订股份转让协议，拟转让18,500万股，占万家文化已发行股份的29.135%，股份转让价款合计305,990万元，收购资金全部来源于龙薇传媒自有或自筹资金。", ["NODE-V5-ZHAOWEI-W1"]),
        ("EV-V6R2-ZHAOWEI-02", "CASE-V5-ZHAOWEI", "ZHAOWEI", "html_block:28", "龙薇传媒在自身境内资金准备不足，相关金融机构融资尚待审批、存在极大不确定性的情况下，以空壳公司收购上市公司并贸然公告，对市场和投资者产生严重误导。", ["NODE-V5-ZHAOWEI-W2"]),
        ("EV-V6R2-ZHAOWEI-03", "CASE-V5-ZHAOWEI", "ZHAOWEI", "html_block:52", "2016年12月23日至2017年4月1日，控股权转让事项由控股权转让变更为5%股权转让，后又完全终止，且双方不追究任何违约责任。", ["NODE-V5-ZHAOWEI-W3"]),
        ("EV-V6R2-FRAUD-01", "CASE-V5-FRAUD-ANTHOLOGY", "ZHANGZIDAO", "html_block:7", "獐子岛公司2016年通过少记录成本、营业外支出的方法将利润由亏损披露为盈利，2017年将以前年度已采捕海域列入核销或减值海域，夸大亏损幅度。", ["NODE-V5-FRAUD-ANTHOLOGY-W1"]),
        ("EV-V6R2-FRAUD-02", "CASE-V5-FRAUD-ANTHOLOGY", "ZHANGZIDAO", "html_block:8", "证监会借助卫星定位数据，对公司27条采捕船只数百万条海上航行定位数据进行分析，委托两家第三方专业机构还原真实航行轨迹，并据此认定成本、营业外支出、利润等存在虚假。", ["NODE-V5-FRAUD-ANTHOLOGY-W1"]),
        ("EV-V6R2-FRAUD-03", "CASE-V5-FRAUD-ANTHOLOGY", "KANGDE", "html_block:24", "康得新2015年至2018年年度报告虚增利润总额分别为2,242,745,642.37元、2,943,420,778.01元、3,908,205,906.90元、2,436,193,525.40元。", ["NODE-V5-FRAUD-ANTHOLOGY-W2"]),
        ("EV-V6R2-FRAUD-04", "CASE-V5-FRAUD-ANTHOLOGY", "KANGDE", "html_block:25", "康得新及三家子公司相关账户资金被实时、全额归集到康得集团账户，康得新账户组各年末实际余额为0。", ["NODE-V5-FRAUD-ANTHOLOGY-W2"]),
        ("EV-V6R2-FRAUD-05", "CASE-V5-FRAUD-ANTHOLOGY", "KANGDE", "html_block:31", "2018年7月至12月，康得新将募集资金以支付设备采购款名义转出，经过多道流转后主要资金最终回流至康得新，用于归还银行贷款、配合虚增利润等方面。", ["NODE-V5-FRAUD-ANTHOLOGY-W2"]),
        ("EV-V6R2-SILVER-01", "CASE-V5-SILVER", "SILVER", "html_block:76", "In the aftermath of the manipulation of the silver market by the Hunt brothers, the CFTC issued a proposed rule to require the exchanges to establish position limits.", ["NODE-V5-SILVER-W1"]),
        ("EV-V6R2-SILVER-02", "CASE-V5-SILVER", "SILVER", "html_block:77", "The Commission believes that a trader's net position has a continued effect on price and, if sufficiently large, can become a perceptible market factor; limits diminish the possibility of accentuating price swings if large positions must be liquidated sharply.", ["NODE-V5-SILVER-W2"]),
        ("EV-V6R2-SILVER-03", "CASE-V5-SILVER", "SILVER", "html_block:83", "The Commission adopted Rule 1.61, which required exchanges to have position limits for all commodities that did not have Commission-set limits.", ["NODE-V5-SILVER-W2"]),
        ("EV-V6R2-LEHUA-CRASH-01", "CASE-V5-LEHUA-CRASH", "LEHUA_CRASH", "pdf_page:1:paragraph:1", "The Board confirms that it is not aware of any reasons for the fluctuations; the Company is operating normally; and none of the Directors with an interest in the Shares has sold or otherwise disposed of their interests.", ["NODE-V5-LEHUA-CRASH-W1"]),
        ("EV-V6R2-LEHUA-CRASH-02", "CASE-V5-LEHUA-CRASH", "LEHUA_CRASH", "pdf_page:2:paragraph:1", "Shares issued prior to listing and shares held by cornerstone investors were subject to a 12-month lock-up period from January 19, 2023. Such lock-up period will expire on January 18, 2024.", ["NODE-V5-LEHUA-CRASH-W2"]),
        ("EV-V6R2-LEHUA-PLATFORM-01", "CASE-V5-LEHUA-PLATFORM", "LEHUA_PROSPECTUS", "pdf_page:14:paragraph:1", "Revenue attributable to our top one artist accounted for 16.8%, 36.7%, 49.5% and 56.8% of total revenue for 2019, 2020, 2021 and the four months ended April 30, 2022; revenue growth attributable to such artist accounted for over 80% of overall revenue growth in 2020, 2021 and the four months ended April 30, 2022.", ["NODE-V5-LEHUA-PLATFORM-W1"]),
        ("EV-V6R2-LEHUA-PLATFORM-02", "CASE-V5-LEHUA-PLATFORM", "LEHUA_PROSPECTUS", "pdf_page:196:paragraph:1", "Supplier B was controlled by one managed artist; purchases from Supplier B accounted for 9.2%, 31.1%, 43.9% and 48.6% of cost of revenue in 2019, 2020, 2021 and the four months ended April 30, 2022.", ["NODE-V5-LEHUA-PLATFORM-W1"]),
        ("EV-V6R2-LEHUA-PLATFORM-03", "CASE-V5-LEHUA-PLATFORM", "LEHUA_INTERIM", "pdf_page:3:paragraph:1", "For the six months ended June 30, 2023, artist management revenue was RMB319,437 thousand, representing 87.6% of total revenue.", ["NODE-V5-LEHUA-PLATFORM-W2"]),
        ("EV-V6R2-XIAOMI-01", "CASE-V5-XIAOMI", "XIAOMI", "pdf_page:6:paragraph:1", "In 2018, Xiaomi achieved RMB174.9 billion in revenue, an increase of 53% over the previous year, and began reorganizing the company after its IPO.", ["NODE-V5-XIAOMI-W1"]),
        ("EV-V6R2-XIAOMI-02", "CASE-V5-XIAOMI", "XIAOMI", "pdf_page:14:paragraph:1", "For the year ended December 31, 2018, Xiaomi recorded RMB174.9 billion in revenue, representing a year-on-year increase of 52.6%, and adjusted net profit grew 59.5% to RMB8.6 billion.", ["NODE-V5-XIAOMI-W2"]),
        ("EV-V6R2-XIAOMI-03", "CASE-V5-XIAOMI", "XIAOMI", "pdf_page:100:paragraph:1", "Xiaomi's shares were listed on the Stock Exchange on July 9, 2018, and net proceeds from the Global Offering were approximately HK$27,561.0 million.", ["NODE-V5-XIAOMI-W2"]),
        ("EV-V6R2-AUTO-01", "CASE-V5-AUTO", "PORSCHE", "html_block:43", "In China, 56,887 cars were handed over to customers (-28 per cent). The decline is mainly due to the continuing challenging economic situation in this region.", ["NODE-V5-AUTO-W2"]),
        ("EV-V6R2-TECH-01", "CASE-V5-TECH", "SSE", "html_block:11", "七年来，科创板坚守“硬科技”定位，持续深化各项制度机制创新，不断放大改革效应。", ["NODE-V5-TECH-W1"]),
        ("EV-V6R2-TECH-02", "CASE-V5-TECH", "SSE", "html_block:21", "科创板集成电路上市公司已超120家，涵盖芯片设计、制造、封测、设备、材料、软件等产业链各环节。", ["NODE-V5-TECH-W2"]),
        ("EV-V6R2-TECH-03", "CASE-V5-TECH", "BAILI", "pdf_page:12:paragraph:2", "公司与BMS就BL-B01D1达成了总额84亿美元、首付8亿美元的全球战略许可及合作交易。", ["NODE-V5-TECH-W2"]),
    ]

    hints = {
        "EV-V6R2-ZHAOWEI-01": "18,500万股",
        "EV-V6R2-ZHAOWEI-02": "融资尚待审批",
        "EV-V6R2-ZHAOWEI-03": "短时间内",
        "EV-V6R2-FRAUD-01": "2016年通过少记录成本",
        "EV-V6R2-FRAUD-02": "27条采捕船只",
        "EV-V6R2-FRAUD-03": "2015 年 1 月至 2018 年 12 月",
        "EV-V6R2-FRAUD-04": "资金被实时、全额归集",
        "EV-V6R2-FRAUD-05": "2018年7月至12月期间",
        "EV-V6R2-SILVER-01": "aftermath of the manipulation",
        "EV-V6R2-SILVER-02": "trader’s net position",
        "EV-V6R2-SILVER-03": "adopted Rule 1.61",
        "EV-V6R2-LEHUA-CRASH-01": "Having made reasonable inquiries",
        "EV-V6R2-LEHUA-CRASH-02": "Shares in issue prior",
        "EV-V6R2-LEHUA-PLATFORM-01": "revenue attributable to our top one artist",
        "EV-V6R2-LEHUA-PLATFORM-02": "During the Track Record Period",
        "EV-V6R2-LEHUA-PLATFORM-03": "Artist management 319,437",
        "EV-V6R2-XIAOMI-01": "Xiaomi achieved RMB174.9 billion",
        "EV-V6R2-XIAOMI-02": "We recorded RMB174.9 billion",
        "EV-V6R2-XIAOMI-03": "listed on the Stock Exchange on July 9, 2018",
        "EV-V6R2-AUTO-01": "In China, 56,887",
        "EV-V6R2-TECH-01": "科创板坚守“硬科技”定位",
        "EV-V6R2-TECH-02": "集成电路上市公司已超120家",
        "EV-V6R2-TECH-03": "总额 84 亿美元",
    }

    rows = []
    for evidence_id, case_id, source_key, locator, quote, supports in raw:
        source_id, url, publisher, published_at, tier, digest, suffix = sources[source_key]
        quote = verbatim_excerpt(root, digest, suffix, locator, hints[evidence_id])
        snapshot = snapshot_record(root, digest, suffix, retrieved[digest])
        context_id = evidence_id.replace("EV-", "CTX-")
        link_id = evidence_id.replace("EV-", "EL-")
        rows.append({
            "evidence_id": evidence_id,
            "case_id": case_id,
            "source_id": source_id,
            "context_id": context_id,
            "evidence_link_id": link_id,
            "source_url": url,
            "publisher": publisher,
            "published_at": published_at,
            **snapshot,
            "original_quote": quote,
            "locator": locator,
            "source_tier": tier,
            "temporal_role": "POST_EVENT_VALIDATION",
            "content_sha256": sha_bytes(quote.encode("utf-8")),
            "supports_node_ids": supports,
            "acceptance_status": "ACCEPTED",
            "acceptance_reason": "GATES_PASSED",
            "visual_review_status": "PASSED" if suffix == ".pdf" else "NOT_APPLICABLE",
        })
    return rows


CASE_PROFILES: dict[str, dict[str, Any]] = {
    "CASE-V5-ZHAOWEI": {"ids": ["EV-V6R2-ZHAOWEI-01", "EV-V6R2-ZHAOWEI-02", "EV-V6R2-ZHAOWEI-03"], "fact": "证监会决定书确认了拟收购比例、交易价款、融资尚待审批及方案缩减后终止的公开事件序列。", "boundary": "可确认披露与交易方案变化，不能据此推定所有参与方的未公开动机或把股价变化归因于单一机制。", "gaps": ["MOTIVE_NOT_ESTABLISHED", "CAUSAL_IDENTIFICATION_NOT_MET"]},
    "CASE-V5-FRAUD-ANTHOLOGY": {"ids": ["EV-V6R2-FRAUD-01", "EV-V6R2-FRAUD-02", "EV-V6R2-FRAUD-03", "EV-V6R2-FRAUD-04", "EV-V6R2-FRAUD-05"], "fact": "证监会原文确认了獐子岛财务失真及卫星航迹核验方法，也确认了康得新虚增利润、资金归集和募集资金回流事实。", "boundary": "这些材料支持具体违法事实和调查方法，不自动支持作者对所有财务造假公司的统一动机或普遍机制归纳。", "gaps": ["GENERALIZATION_NOT_ESTABLISHED", "CAUSAL_IDENTIFICATION_NOT_MET"]},
    "CASE-V5-SILVER": {"ids": ["EV-V6R2-SILVER-01", "EV-V6R2-SILVER-02", "EV-V6R2-SILVER-03"], "fact": "CFTC材料确认亨特兄弟操纵白银事件是持仓限额规则的重要监管背景，并解释了大头寸及集中平仓放大价格波动的机制。", "boundary": "该材料不能替代法院原文，也未核验视频中的完整头寸、资金和逐日交易序列。", "gaps": ["COURT_RECORD_NOT_ACQUIRED", "POSITION_TIMELINE_NOT_CLOSED"]},
    "CASE-V5-LEHUA-CRASH": {"ids": ["EV-V6R2-LEHUA-CRASH-01", "EV-V6R2-LEHUA-CRASH-02"], "fact": "港交所公告确认公司称经营正常、不知悉异常波动原因、持股董事未出售权益，并确认相关12个月禁售期于2024年1月18日届满。", "boundary": "公告只能确认公司声明和解禁时点，不能从时间接近推定解禁导致股价异动。", "gaps": ["TRADING_ACCOUNT_DATA_MISSING", "CAUSAL_IDENTIFICATION_NOT_MET"]},
    "CASE-V5-LEHUA-PLATFORM": {"ids": ["EV-V6R2-LEHUA-PLATFORM-01", "EV-V6R2-LEHUA-PLATFORM-02", "EV-V6R2-LEHUA-PLATFORM-03"], "fact": "招股书确认匿名头部艺人的收入贡献和Supplier B集中度，中报确认艺人管理业务占总收入87.6%。", "boundary": "法定披露没有指明匿名艺人身份，不能据此确认王一博个人收入占比、实际控制或治理主导权。", "gaps": ["ANONYMOUS_SUBJECT_IDENTITY_UNRESOLVED", "GOVERNANCE_CONTROL_NOT_ESTABLISHED"]},
    "CASE-V5-XIAOMI": {"ids": ["EV-V6R2-XIAOMI-01", "EV-V6R2-XIAOMI-02", "EV-V6R2-XIAOMI-03"], "fact": "小米2018年报确认上市日期、约275.61亿港元净募资、2018年收入及IPO后组织调整。", "boundary": "年报不包含首日收盘价，也不能单独证明募资与后来各项业务表现之间的因果关系。", "gaps": ["IPO_FIRST_CLOSE_MARKET_DATA_MISSING", "CAUSAL_IDENTIFICATION_NOT_MET"]},
    "CASE-V5-AUTO": {"ids": ["EV-V6R2-AUTO-01"], "fact": "保时捷官方材料确认2024年中国交付56,887辆，同比下降28%。", "boundary": "单一品牌年度交付数据不能代表全部豪华车或合资品牌，也不能识别下降由新能源竞争单独造成。", "gaps": ["MARKET_PANEL_INCOMPLETE", "CAUSAL_IDENTIFICATION_NOT_MET"]},
    "CASE-V5-TECH": {"ids": ["EV-V6R2-TECH-01", "EV-V6R2-TECH-02", "EV-V6R2-TECH-03"], "fact": "上交所材料确认科创板硬科技定位及集成电路产业链覆盖，百利天恒年报确认84亿美元交易总额和8亿美元首付款。", "boundary": "个案与板块统计可说明融资和产业集聚事实，不能证明科创板制度对企业创新结果的净因果效应。", "gaps": ["COUNTERFACTUAL_NOT_AVAILABLE", "CAUSAL_IDENTIFICATION_NOT_MET"]},
}


def legacy_evidence(root: Path, source_rows: list[dict[str, Any]], first_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cited: set[str] = set()
    for record in first_rows:
        if record["metadata"]["release_partition"] != "candidate":
            continue
        payload = json.loads(message(record, "assistant")["content"])
        cited.update(c["evidence_id"] for c in payload.get("citations", []))
    index: dict[str, dict[str, Any]] = {}
    for record in source_rows:
        for evidence in record["metadata"]["ui_audit_context"].get("claim_level_evidence", []):
            if evidence.get("evidence_id") in cited:
                index[evidence["evidence_id"]] = evidence

    dates = {
        "SRC-MOA-SOY-200810": ("农业农村部", "2010-06-12T00:00:00+08:00"),
        "SRC-NDRC-PRICE-REFORM-2017": ("国家发展和改革委员会", "2017-10-23T00:00:00+08:00"),
        "SRC-NBS-HOUSING-INTERPRETATION": ("国家统计局", "2025-12-15T00:00:00+08:00"),
        "SRC-EXT-HOUSING": ("国家统计局", "2025-12-15T00:00:00+08:00"),
        "SRC-VANKE-2016-ANNUAL": ("万科企业股份有限公司 / 巨潮资讯", "2017-03-27T00:00:00+08:00"),
        "SRC-VANKE-HKEX-20160712": ("万科企业股份有限公司 / HKEXnews", "2016-07-12T00:00:00+08:00"),
    }
    rows = []
    for evidence_id in sorted(cited):
        evidence = index[evidence_id]
        digest = evidence["snapshot_sha256"]
        meta_path = root / ".worktrees/evidence-chain/data/curation/v4.1/source_snapshots" / f"{digest}.metadata.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        snapshot_path = root / ".worktrees/evidence-chain" / Path(meta["snapshot_path"])
        publisher, published_at = dates[evidence["source_id"]]
        rows.append({
            **evidence,
            "context_id": f"CTX-V6R2-LEGACY-{evidence_id}",
            "evidence_link_id": f"EL-V6R2-LEGACY-{evidence_id}",
            "publisher": publisher,
            "published_at": published_at,
            "retrieved_at": meta["retrieved_at"],
            "snapshot_path": snapshot_path.relative_to(root).as_posix(),
            "supports_node_ids": [evidence["target_ref"]],
            "visual_review_status": "PASSED_IN_V4_1" if snapshot_path.suffix.lower() == ".pdf" else "NOT_APPLICABLE",
        })
    return rows


def registries(evidence: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    sources: dict[str, dict[str, Any]] = {}
    contexts = []
    links = []
    for row in evidence:
        source = {
            key: row[key]
            for key in ("source_id", "source_url", "publisher", "published_at", "retrieved_at", "source_tier", "snapshot_path", "snapshot_sha256")
        }
        previous = sources.setdefault(row["source_id"], source)
        if previous != source:
            raise ValueError(f"conflicting source {row['source_id']}")
        contexts.append({
            "context_id": row["context_id"],
            "case_id": row["case_id"],
            "source_id": row["source_id"],
            "text": row["original_quote"],
            "locator": row["locator"],
            "content_sha256": row["content_sha256"],
            "snapshot_sha256": row["snapshot_sha256"],
            "temporal_role": row["temporal_role"],
        })
        links.append({
            "evidence_link_id": row["evidence_link_id"],
            "evidence_id": row["evidence_id"],
            "case_id": row["case_id"],
            "source_id": row["source_id"],
            "context_id": row["context_id"],
            "supports_node_ids": row["supports_node_ids"],
            "stance": row.get("stance", "supports"),
            "coverage": row.get("coverage", "partial"),
            "acceptance_status": row["acceptance_status"],
        })
    return [sources[k] for k in sorted(sources)], sorted(contexts, key=lambda x: x["context_id"]), sorted(links, key=lambda x: x["evidence_link_id"])


def citation(e: dict[str, Any]) -> dict[str, Any]:
    return {key: e[key] for key in (
        "evidence_id", "source_id", "context_id", "evidence_link_id", "source_url",
        "publisher", "locator", "source_tier", "temporal_role", "content_sha256", "snapshot_sha256",
    )}


def question_from_user(text: str) -> str:
    match = re.search(r"\n问题：(.*?)\n\n严格逻辑要求：", text, re.S)
    return match.group(1).strip() if match else text.strip()


def task_name(role: str) -> str:
    return {
        "evidence_confirmation": "外部证据确认",
        "evidence_boundary": "证据边界判断",
        "bounded_impact": "有边界现实影响判断",
        "cross_chain_synthesis": "跨链综合判断",
        "causal_refusal": "因果归因评估",
        "alternative_explanation": "替代解释比较",
    }.get(role, role)


def build_user(record: dict[str, Any], contexts: list[dict[str, Any]], question: str) -> str:
    material = "\n".join(f"[{c['context_id']}] {c['text']}（{c['locator']}）" for c in contexts)
    return (
        f"分析对象：{record['metadata']['case_id']}\n"
        f"推理任务：{task_name(record['metadata']['question_role'])}\n"
        "真值范围：world_evidence\n\n材料：\n"
        f"{material}\n\n问题：{question}\n\n"
        "严格逻辑要求：只使用给定材料；区分直接事实、证据边界与因果归因。"
        "时间先后不自动构成因果；证据不足时必须限定回答或拒答。"
    )


def closed_payload(record: dict[str, Any], profile: dict[str, Any], evs: list[dict[str, Any]]) -> dict[str, Any]:
    role = record["metadata"]["question_role"]
    refs = [e["evidence_id"] for e in evs]
    node = evs[0]["supports_node_ids"][0]
    final_node = f"NODE-V6R2-{record['id']}-FINAL"
    steps = [{
        "step_no": 1, "step_kind": "evidence", "input_refs": refs, "relation": "supports_bounded_facts",
        "output_ref": node, "conclusion": profile["fact"], "explanation": "仅汇总通过T1/T2、原文定位、快照和哈希门禁的事实。",
        "evidence_refs": refs, "support_status": {"author_fidelity": "not_applicable", "world_validity": "confirmed"},
    }]
    if role == "cross_chain_synthesis":
        steps.append({
            "step_no": 2, "step_kind": "comparison", "input_refs": [node], "relation": "compares_author_claim_with_world_evidence",
            "output_ref": f"{final_node}-BOUNDARY", "conclusion": profile["boundary"], "explanation": "将作者解释与外证实际覆盖范围分开。",
            "evidence_refs": refs, "support_status": {"author_fidelity": "not_applicable", "world_validity": "partially_supported"},
        })
        input_ref = f"{final_node}-BOUNDARY"
        step_no = 3
    else:
        input_ref = node
        step_no = 2
    steps.append({
        "step_no": step_no, "step_kind": "boundary", "input_refs": [input_ref], "relation": "bounds_conclusion",
        "output_ref": final_node, "conclusion": profile["boundary"], "explanation": "未通过因果或主体识别门禁的部分不升级为确定结论。",
        "evidence_refs": refs, "support_status": {"author_fidelity": "not_applicable", "world_validity": "partially_supported"},
    })
    if role == "evidence_confirmation":
        direct = f"{profile['fact']} {profile['boundary']}"
    elif role == "evidence_boundary":
        direct = f"证据已闭合到以下范围：{profile['fact']} 边界是：{profile['boundary']}"
    elif role == "bounded_impact":
        direct = f"有边界的现实判断是：{profile['fact']} {profile['boundary']}"
    else:
        direct = f"作者结论应限定为：{profile['boundary']} 可确认的现实基础是：{profile['fact']}"
    return {
        "answerability": "partially_answerable",
        "direct_answer": direct,
        "local_reasoning_path": steps,
        "verification": profile["fact"],
        "uncertainty_note": profile["boundary"],
        "missing_evidence": profile["gaps"],
        "citations": [citation(e) for e in evs],
    }


def project_records(
    first_rows: list[dict[str, Any]], evidence: list[dict[str, Any]], contexts: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_evidence = {e["evidence_id"]: e for e in evidence}
    by_context = {c["context_id"]: c for c in contexts}
    projected = []
    closed = []
    for source in first_rows:
        record = json.loads(json.dumps(source, ensure_ascii=False))
        meta = record["metadata"]
        role = meta["question_role"]
        case_id = meta["case_id"]
        existing_payload = json.loads(message(record, "assistant")["content"])
        existing_payload["citations"] = [
            citation(by_evidence[row["evidence_id"]])
            for row in existing_payload.get("citations", [])
            if row.get("evidence_id") in by_evidence
        ]
        record["messages"][2]["content"] = jline(existing_payload)
        original_partition = meta["release_partition"]
        partition = "answer_sft" if original_partition == "candidate" else "evidence_pending"
        if meta["answerability"] == "unanswerable":
            partition = "abstention_sft"
        if original_partition == "audit_only" and case_id in CASE_PROFILES and role in CLOSED_ROLES:
            profile = CASE_PROFILES[case_id]
            evs = [by_evidence[eid] for eid in profile["ids"]]
            payload = closed_payload(record, profile, evs)
            question = question_from_user(message(record, "user")["content"])
            record["messages"][1]["content"] = build_user(record, [by_context[e["context_id"]] for e in evs], question)
            record["messages"][2]["content"] = jline(payload)
            meta["answerability"] = payload["answerability"]
            meta["citation_count"] = len(evs)
            partition = "answer_sft"
            closed.append({
                "qa_id": record["id"], "case_id": case_id, "question_role": role,
                "previous_partition": "evidence_pending", "new_partition": partition,
                "answerability": payload["answerability"], "evidence_ids": profile["ids"],
                "closure_status": "CLOSED_WITH_BOUNDED_ANSWER",
            })
        elif partition == "abstention_sft" and case_id in CASE_PROFILES:
            profile = CASE_PROFILES[case_id]
            evs = [by_evidence[eid] for eid in profile["ids"]]
            question = question_from_user(message(record, "user")["content"])
            record["messages"][1]["content"] = build_user(record, [by_context[e["context_id"]] for e in evs], question)
            premise_node = evs[0]["supports_node_ids"][0]
            refs = [e["evidence_id"] for e in evs]
            payload = {
                "answerability": "unanswerable",
                "direct_answer": "ABSTAIN",
                "local_reasoning_path": [
                    {
                        "step_no": 1, "step_kind": "evidence", "input_refs": refs,
                        "relation": "supports_descriptive_facts", "output_ref": premise_node,
                        "conclusion": profile["fact"], "explanation": "外证只闭合描述性事实。",
                        "evidence_refs": refs,
                        "support_status": {"author_fidelity": "not_applicable", "world_validity": "confirmed"},
                    },
                    {
                        "step_no": 2, "step_kind": "causal_boundary", "input_refs": [premise_node],
                        "relation": "fails_causal_identification_gate", "output_ref": f"NODE-V6R2-{record['id']}-ABSTAIN",
                        "conclusion": "缺少比较组、前趋势、混杂控制和稳健性检验，不能作确定因果归因。",
                        "explanation": "描述性对应和时间先后不能替代因果识别。", "evidence_refs": [],
                        "support_status": {"author_fidelity": "not_applicable", "world_validity": "unsupported"},
                    },
                ],
                "verification": profile["fact"],
                "uncertainty_note": profile["boundary"],
                "missing_evidence": sorted(set(profile["gaps"] + ["COMPARISON_GROUP_MISSING", "ROBUSTNESS_TESTS_MISSING"])),
                "citations": [citation(e) for e in evs],
            }
            record["messages"][2]["content"] = jline(payload)
            meta["citation_count"] = len(evs)
        meta["schema_version"] = SCHEMA_VERSION
        meta["release_partition"] = partition
        meta["previous_release_partition"] = original_partition
        if partition == "evidence_pending":
            if case_id in {"CASE-V5-XUXIANG", "CASE-V5-YUANYE"}:
                gaps = ["NO_REVIEWABLE_T1_T2_PRIMARY_TEXT"]
            elif role == "alternative_explanation":
                gaps = ["ALTERNATIVE_EXPLANATIONS_NOT_EVIDENCE_BACKED"]
            else:
                gaps = meta.get("audit_only_reasons") or ["WORLD_EVIDENCE_CHAIN_NOT_CLOSED"]
            meta["stable_gap_codes"] = gaps
        else:
            meta["stable_gap_codes"] = []
        projected.append(record)
    return sorted(projected, key=lambda x: x["id"]), sorted(closed, key=lambda x: x["qa_id"])


def search_audit(root: Path, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = read_jsonl(root / "exports/v6-second-round/acquisition/acquisition_records.jsonl")
    rows += read_jsonl(root / "exports/v6-second-round/acquisition/expansion_acquisition_records.jsonl")
    accepted_by_snapshot: dict[str, list[str]] = {}
    for row in evidence:
        accepted_by_snapshot.setdefault(row["snapshot_sha256"], []).append(row["evidence_id"])
    output = []
    for index, row in enumerate(rows, 1):
        output.append({
            "search_audit_id": f"SEARCH-V6R2-{index:04d}",
            "case_id": row.get("case_id"), "query": row.get("search_query"),
            "discovery_method": row.get("discovery_method", "REGISTERED_URL"),
            "rank": row.get("search_rank"), "candidate_url": row.get("source_url"),
            "final_url": row.get("final_url"), "retrieved_at": row.get("retrieved_at"),
            "acquisition_status": row.get("acquisition_status"), "http_status": row.get("http_status"),
            "snapshot_sha256": row.get("snapshot_sha256"),
            "matched_accepted_evidence_ids": sorted(accepted_by_snapshot.get(row.get("snapshot_sha256"), [])),
            "evidence_use": "ACCEPTED" if row.get("snapshot_sha256") in accepted_by_snapshot else "CANDIDATE_DISCOVERY_ONLY",
        })
    return output


def validate(root: Path, records: list[dict[str, Any]], evidence: list[dict[str, Any]], sources: list[dict[str, Any]], contexts: list[dict[str, Any]], links: list[dict[str, Any]], closed: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if len(records) != 180 or len({r["id"] for r in records}) != 180:
        errors.append("expected 180 unique QA records")
    partitions = Counter(r["metadata"]["release_partition"] for r in records)
    if sum(partitions.values()) != 180:
        errors.append("partition total mismatch")
    source_ids = {r["source_id"] for r in sources}
    context_ids = {r["context_id"] for r in contexts}
    link_ids = {r["evidence_link_id"] for r in links}
    evidence_ids = {r["evidence_id"] for r in evidence}
    for e in evidence:
        for field in ("evidence_id", "source_id", "context_id", "evidence_link_id", "source_url", "publisher", "published_at", "retrieved_at", "original_quote", "locator", "source_tier", "temporal_role", "snapshot_path", "snapshot_sha256", "content_sha256"):
            if not e.get(field): errors.append(f"{e.get('evidence_id')}: missing {field}")
        if e["source_tier"] not in {"T1", "T2"}: errors.append(f"{e['evidence_id']}: ineligible tier")
        path = root / e["snapshot_path"]
        if not path.exists() or sha_file(path) != e["snapshot_sha256"]: errors.append(f"{e['evidence_id']}: snapshot mismatch")
        if sha_bytes(e["original_quote"].encode("utf-8")) != e["content_sha256"]: errors.append(f"{e['evidence_id']}: content hash mismatch")
    for record in records:
        payload = json.loads(message(record, "assistant")["content"])
        part = record["metadata"]["release_partition"]
        if part == "abstention_sft" and payload["direct_answer"] != "ABSTAIN": errors.append(f"{record['id']}: abstention leakage")
        for c in payload.get("citations", []):
            if c.get("evidence_id") not in evidence_ids or c.get("source_id") not in source_ids or c.get("context_id") not in context_ids or c.get("evidence_link_id") not in link_ids:
                errors.append(f"{record['id']}: unresolved citation")
        text = jline(record)
        if "\ufffd" in text: errors.append(f"{record['id']}: Unicode replacement character")
        if "audit_context" in " ".join(m["content"] for m in record["messages"]): errors.append(f"{record['id']}: audit context leaked")
    if len(closed) != 32: errors.append(f"expected 32 closed records, got {len(closed)}")
    return {"schema_version": SCHEMA_VERSION, "errors": errors, "warnings": warnings, "counts": {"qa_records": len(records), "accepted_evidence": len(evidence), "sources": len(sources), "contexts": len(contexts), "evidence_links": len(links), "closed_from_pending": len(closed), "release_partition": dict(sorted(partitions.items()))}, "status": "PASS" if not errors and not warnings else "FAIL"}


def build(root: Path, source: Path, first_dir: Path, out: Path) -> dict[str, Any]:
    source_rows = read_json(source)
    first_rows = read_jsonl(first_dir / "qa_records.jsonl")
    new_evidence = evidence_specs(root)
    evidence = legacy_evidence(root, source_rows, first_rows) + new_evidence
    evidence.sort(key=lambda x: x["evidence_id"])
    sources, contexts, links = registries(evidence)
    records, closed = project_records(first_rows, evidence, contexts)
    audit_contexts = read_jsonl(first_dir / "case_audit_contexts.jsonl")
    by_case = {e["case_id"]: [] for e in new_evidence}
    for e in new_evidence: by_case[e["case_id"]].append(e["evidence_id"])
    for row in audit_contexts:
        row["schema_version"] = "case-audit-context/6.0-second-round"
        row["second_round_evidence_ids"] = sorted(by_case.get(row["case_id"], []))
        row["training_visibility"] = "excluded_from_messages"
    audit_contexts.sort(key=lambda x: x["audit_context_id"])
    report = validate(root, records, evidence, sources, contexts, links, closed)
    if report["errors"] or report["warnings"]:
        raise ValueError(jline(report))
    out.mkdir(parents=True, exist_ok=True)
    files = {
        "sources.jsonl": sources,
        "contexts.jsonl": contexts,
        "evidence_links.jsonl": links,
        "accepted_evidence.jsonl": evidence,
        "search_audit.jsonl": search_audit(root, evidence),
        "qa_records.jsonl": records,
        "answer_sft.jsonl": [r for r in records if r["metadata"]["release_partition"] == "answer_sft"],
        "abstention_sft.jsonl": [r for r in records if r["metadata"]["release_partition"] == "abstention_sft"],
        "evidence_pending.jsonl": [r for r in records if r["metadata"]["release_partition"] == "evidence_pending"],
        "closed_from_pending.jsonl": closed,
        "case_audit_contexts.jsonl": audit_contexts,
    }
    for name, rows in files.items(): write_jsonl(out / name, rows)
    (out / "validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    first_hashes = {p.name: sha_file(p) for p in sorted(first_dir.iterdir()) if p.is_file()}
    card = (
        "# V6 第二轮可审计 SFT 数据集\n\n"
        "本轮把 V5 已取得的一手材料登记为 `source -> context -> evidence-link -> hash` 完整链，并逐题重投影第一轮待补证样本。\n\n"
        f"- `answer_sft`: {report['counts']['release_partition']['answer_sft']} 条，可用于回答训练，其中部分样本保留有边界的 `partially_answerable`。\n"
        f"- `abstention_sft`: {report['counts']['release_partition']['abstention_sft']} 条，因果识别门禁未通过，必须输出 `ABSTAIN`。\n"
        f"- `evidence_pending`: {report['counts']['release_partition']['evidence_pending']} 条，仍缺少可复核原文或命题级闭环。\n"
        f"- 原 89 条待补证样本中闭合 {len(closed)} 条，剩余 {report['counts']['release_partition']['evidence_pending']} 条。\n\n"
        "重要边界：乐华招股书未披露匿名艺人身份；CFTC材料不替代法院交易序列；小米年报不含首日收盘价；保时捷单品牌数据不代表整个汽车市场；无直接反证不标记 contradicted。所有记录仍为 `NEEDS_HUMAN_REVIEW`，不得自动视为正式发布。\n"
    )
    (out / "DATASET_CARD.md").write_text(card, encoding="utf-8")
    tracked = sorted(list(files) + ["validation_report.json", "DATASET_CARD.md"])
    manifest = {
        "dataset_version": RELEASE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "derived_from": {"source_path": source.relative_to(root).as_posix(), "source_sha256": sha_file(source), "first_round_path": first_dir.relative_to(root).as_posix(), "first_round_hashes": first_hashes},
        "formal_ready": False,
        "review_status": "NEEDS_HUMAN_REVIEW",
        "counts": report["counts"],
        "files": {name: {"sha256": sha_file(out / name), "bytes": (out / name).stat().st_size} for name in tracked},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path, default=Path("exports/sft_v41_v5_ui_audit_180.json"))
    parser.add_argument("--first-round", type=Path, default=Path("exports/v6-first-round"))
    parser.add_argument("--out", type=Path, default=Path("exports/v6-second-round/release"))
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = build(root, root / args.source, root / args.first_round, root / args.out)
    print(json.dumps(manifest["counts"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
