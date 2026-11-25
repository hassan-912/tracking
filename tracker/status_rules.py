"""Turn the long text a portal shows into one short category for the report.

Categories used by the report colours: "Approved", "Refused",
"Action needed", "In progress", "Unknown".
"""
from __future__ import annotations


def classify_status(portal: str, status_text: str) -> str:
    """Return one category for what the portal says.

    portal      : "gckey" (IRCC: Canada Tourism / Study / FEE) or "wes"
    status_text : the status exactly as the portal shows it, e.g.
                  "Submitted", "In progress", "Decision made",
                  "Documents received", "Evaluation complete".
    """
    text = status_text.lower()
    # TODO(human): map the wording your team sees on IRCC and WES to a category.
    return "Unknown"
