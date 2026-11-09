"""MF Analysis: the page's data, built from the imported factsheets (mf.py). Under /mf, which auth maps to the
holdings module. Factsheets are imported with `/mf-factsheets` in Claude Code and `python spendlens/import_mf.py`,
not through the API."""
import re

from fastapi import APIRouter, Depends, HTTPException, Response

import mf
from db.engine import get_session

router = APIRouter(prefix="/spendlens/api", tags=["mf"])


@router.get("/mf/analysis")
def mf_analysis(session=Depends(get_session)):
    return mf.analysis(session)


@router.get("/mf/reports/{report_id}/pdf")
def mf_report_pdf(report_id: int, session=Depends(get_session)):
    """The stored Morningstar report PDF, shown inline on MF Analysis › Morningstar check. Scoped to the user."""
    got = mf.report_pdf(session, report_id)
    if got is None:
        raise HTTPException(404, "No stored PDF for that report")
    name, data = got
    safe = re.sub(r"[^\w.\-]", "_", name)
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{safe}"'})
