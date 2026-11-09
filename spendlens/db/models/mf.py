"""Mutual-fund factsheet data for MF Analysis: what was read from each AMC file, one row per fund per month, and the
fund's portfolio holdings that month. Filled by `import_mf.py` from the JSON the mf-factsheet-analyst agent writes
(see mf.py for the format); the factsheet files themselves are not kept."""
from typing import Optional

from sqlalchemy import ForeignKey, Index, LargeBinary, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, utc_now_text


class MfSource(Base):
    """One imported file (factsheet or portfolio disclosure) for one month."""
    __tablename__ = "mf_sources"
    __table_args__ = (UniqueConstraint("user_id", "month", "file_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(default=1)
    month: Mapped[str]                       # YYYY-MM the factsheet is "as on"
    as_on: Mapped[str] = mapped_column(default="")              # the exact date printed, YYYY-MM-DD
    file_name: Mapped[str]
    sha256: Mapped[str] = mapped_column(default="")
    kind: Mapped[str] = mapped_column(default="factsheet")   # factsheet / portfolio
    amc: Mapped[str] = mapped_column(default="")
    funds: Mapped[int] = mapped_column(default=0)
    notes: Mapped[str] = mapped_column(default="")
    imported_at: Mapped[str] = mapped_column(default=utc_now_text)


class MfFundMonth(Base):
    """A fund's numbers as one month's factsheet printed them. Missing figures stay NULL; nothing is guessed."""
    __tablename__ = "mf_fund_months"
    __table_args__ = (UniqueConstraint("user_id", "scheme_key", "month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(default=1)
    month: Mapped[str]                       # one row per fund per month: (user, scheme_key, month) is unique
    as_on: Mapped[str] = mapped_column(default="")              # the exact date printed, YYYY-MM-DD
    scheme_key: Mapped[str]                  # normalised scheme + plan, the identity across months
    scheme: Mapped[str]
    plan: Mapped[str] = mapped_column(default="")             # Direct / Regular
    amc: Mapped[str] = mapped_column(default="")
    amfi_code: Mapped[str] = mapped_column(default="")
    category: Mapped[str] = mapped_column(default="")
    benchmark: Mapped[str] = mapped_column(default="")
    aum_cr: Mapped[Optional[float]] = mapped_column(nullable=True)
    ter_pct: Mapped[Optional[float]] = mapped_column(nullable=True)
    std_dev: Mapped[Optional[float]] = mapped_column(nullable=True)
    beta: Mapped[Optional[float]] = mapped_column(nullable=True)
    sharpe: Mapped[Optional[float]] = mapped_column(nullable=True)
    alpha: Mapped[Optional[float]] = mapped_column(nullable=True)
    treynor: Mapped[Optional[float]] = mapped_column(nullable=True)
    turnover_pct: Mapped[Optional[float]] = mapped_column(nullable=True)
    top10_pct: Mapped[Optional[float]] = mapped_column(nullable=True)
    cash_pct: Mapped[Optional[float]] = mapped_column(nullable=True)
    cap_large: Mapped[Optional[float]] = mapped_column(nullable=True)
    cap_mid: Mapped[Optional[float]] = mapped_column(nullable=True)
    cap_small: Mapped[Optional[float]] = mapped_column(nullable=True)
    ret_1y: Mapped[Optional[float]] = mapped_column(nullable=True)
    ret_3y: Mapped[Optional[float]] = mapped_column(nullable=True)
    ret_5y: Mapped[Optional[float]] = mapped_column(nullable=True)
    bench_1y: Mapped[Optional[float]] = mapped_column(nullable=True)
    bench_3y: Mapped[Optional[float]] = mapped_column(nullable=True)
    bench_5y: Mapped[Optional[float]] = mapped_column(nullable=True)
    ytm: Mapped[Optional[float]] = mapped_column(nullable=True)
    mod_duration: Mapped[Optional[float]] = mapped_column(nullable=True)
    avg_maturity: Mapped[Optional[float]] = mapped_column(nullable=True)
    macaulay: Mapped[Optional[float]] = mapped_column(nullable=True)
    credit_aaa_sov_pct: Mapped[Optional[float]] = mapped_column(nullable=True)
    fund_manager: Mapped[str] = mapped_column(default="")     # the manager names, "A, B"
    managers: Mapped[str] = mapped_column(default="")         # JSON [{name, since}]: names with "managing since" dates
    notes: Mapped[str] = mapped_column(default="")
    source_id: Mapped[Optional[int]] = mapped_column(nullable=True)


class MfHolding(Base):
    """One line of a fund's portfolio that month."""
    __tablename__ = "mf_holdings"
    __table_args__ = (Index("ix_mf_holdings_fund_month", "fund_month_id"), Index("ix_mf_holdings_user", "user_id"))

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(default=1)
    fund_month_id: Mapped[int] = mapped_column(ForeignKey("mf_fund_months.id", ondelete="CASCADE"))
    name: Mapped[str]
    isin: Mapped[str] = mapped_column(default="")
    pct: Mapped[float] = mapped_column(default=0)
    sector: Mapped[str] = mapped_column(default="")
    rating: Mapped[str] = mapped_column(default="")
    qty: Mapped[Optional[float]] = mapped_column(nullable=True)   # shares, when the portfolio disclosure prints them


class MfReport(Base):
    """A third-party fund report (a Morningstar fund report), kept to cross-check the AMC's own figures. One row per
    fund per report date; `data` is the JSON parse_morningstar returns. Its portfolio is as of `month`."""
    __tablename__ = "mf_reports"
    __table_args__ = (UniqueConstraint("user_id", "source", "scheme_key", "report_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(default=1)
    source: Mapped[str] = mapped_column(default="morningstar")
    scheme_key: Mapped[str]
    scheme: Mapped[str]                      # the fund name as the report prints it
    isin: Mapped[str] = mapped_column(default="")
    report_date: Mapped[str]                 # YYYY-MM-DD the report was generated
    month: Mapped[str] = mapped_column(default="")             # YYYY-MM of its portfolio date
    data: Mapped[str] = mapped_column(Text, default="")        # JSON
    file_name: Mapped[str] = mapped_column(default="")
    sha256: Mapped[str] = mapped_column(default="")
    imported_at: Mapped[str] = mapped_column(default=utc_now_text)
    pdf: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)  # the report itself (~80 KB), shown in the UI
