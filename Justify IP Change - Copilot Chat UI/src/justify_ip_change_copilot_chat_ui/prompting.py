from __future__ import annotations

from .models import AttachmentPlan, CaseRecord


def build_case_prompt(base_message: str, record: CaseRecord, plan: AttachmentPlan) -> str:
    fields = "\n".join(f"{name}: {value if value else '[blank]'}" for name, value in record.values.items())
    originals = "\n".join(f"- {name}" for name in plan.source_document_names)
    merged = "\n".join(f"- {name}" for name in plan.merged_pdf_names)
    return (
        base_message.rstrip()
        + "\n\nSINGLE CASE EXECUTION\n"
        + "Analyze this case independently. Do not use information from any earlier case or chat.\n"
        + f"change_id: {record.change_id}\nInterestedPartyId: {record.interested_party_id}\n\n"
        + "MERGED PDF PARTS (analyze in numeric order)\n"
        + merged
        + "\n\nORIGINAL DOCUMENT MANIFEST\n"
        + originals
        + "\n\nCASE DATA\n"
        + fields
        + "\n\nMANDATORY FINAL PLAIN-TEXT AUDIT RESULT\n"
        + "Finish with exactly these two lines, after any required downloadable workbook link:\n"
        + "All files for all cases were exposed: Yes|No\n"
        + f"Case result: {record.change_id} | successful|failed\n"
        + "No text may follow the Case result line."
    )
