"""Conservative per-user CSS invoice mail attribution.

An invoice attachment found in a shared mailbox proves only that a document was
observed, not that it belongs to the individual sales representative.
"""
from email.utils import getaddresses

PERSONAL_EMAIL = "taehoon.kim@novogene.com"
CSS_SENDER = "css@novogene-amea.com"

def addresses(*values):
    return {email.lower().strip() for _, email in getaddresses([str(x or "") for x in values]) if email}

def classify_mail(from_email, to, cc, reply_to="", user_email=PERSONAL_EMAIL):
    sender = addresses(from_email)
    recipients = addresses(to, cc)  # Reply-To is NOT recipient evidence.
    user = user_email.lower().strip()
    is_css = CSS_SENDER in sender
    directly_addressed = user in recipients
    if is_css and directly_addressed:
        return "CSS_DIRECT_RECEIPT"
    if directly_addressed:
        return "DIRECT_NON_CSS_REVIEW"
    if is_css:
        return "CSS_OTHER_RECIPIENT"
    return "SHARED_OR_OTHER_PERSON_MAIL"

def classify_invoice(from_email, to, cc, known_owner=False, user_email=PERSONAL_EMAIL):
    mail_state = classify_mail(from_email, to, cc, user_email=user_email)
    if known_owner:
        return "OWNER_VERIFIED", mail_state
    if mail_state == "CSS_DIRECT_RECEIPT":
        # Mail evidence alone is insufficient to assign sales ownership.
        return "DIRECT_CSS_PENDING_OWNER_MATCH", mail_state
    if mail_state == "DIRECT_NON_CSS_REVIEW":
        return "DIRECT_NON_CSS_PENDING_OWNER_MATCH", mail_state
    return "EXCLUDE_FROM_PERSONAL_REVENUE_UNLESS_OWNER_VERIFIED", mail_state
