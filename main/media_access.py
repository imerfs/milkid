"""Who may read a file under /media/ (nginx asks Django through ``auth_request`` before serving it).

Signed-in is not enough for the folders that hold people's papers: request documents, inspection and technical-report files, letters, violation photos and
AutoCAD files are readable only by their owner (and the parties of the record) or by municipal staff of the same village; admins read everything. Folders
that are public by design (property ads, served without the check) or hold no personal data keep the plain signed-in rule. A path under a protected folder
that matches no record is refused.
"""
from main.models import AutoCADFile, InspectionDocument, LetterAttachment, RequestDocument, TechnicalReport, ViolationReport
from main.request_scope import in_scope
from main.roles import ADMIN_ROLES, MUNICIPAL_STAFF_ROLES

PROTECTED = ('request_documents/', 'inspection_documents/', 'technical_reports/', 'letters/', 'violation_photos/', 'autocad_files/', 'dxf_files/')


def _role(user):
    profile = getattr(user, 'profile', None)
    return profile.role if profile is not None else ''


def _may_see_request(user, sr):
    if sr.user_id == user.id:
        return True
    return _role(user) in MUNICIPAL_STAFF_ROLES and in_scope(user, sr)


def relative_path(original_uri):
    """``/media/letters/2026/10/a.pdf?x=1`` -> ``letters/2026/10/a.pdf`` (None when it does not point into /media/ or tries to leave it)."""
    path = (original_uri or '').split('?', 1)[0]
    if not path.startswith('/media/'):
        return None
    rel = path[len('/media/'):]
    if '..' in rel.split('/') or '\\' in rel or '\x00' in rel:
        return None
    return rel


def can_read(user, rel):
    if not user.is_authenticated:
        return False
    if user.is_superuser or _role(user) in ADMIN_ROLES:
        return True
    if not rel.startswith(PROTECTED):
        return True
    if rel.startswith('request_documents/'):
        doc = RequestDocument.objects.filter(document=rel).select_related('request__user__profile').first()
        return doc is not None and _may_see_request(user, doc.request)
    if rel.startswith('inspection_documents/'):
        doc = InspectionDocument.objects.filter(document=rel).select_related('inspection__request__user__profile').first()
        return doc is not None and _may_see_request(user, doc.inspection.request)
    if rel.startswith('technical_reports/'):
        report = TechnicalReport.objects.filter(document=rel).select_related('request__user__profile').first()
        return report is not None and _may_see_request(user, report.request)
    if rel.startswith('letters/'):
        att = LetterAttachment.objects.filter(file=rel).select_related('letter').first()
        if att is None:
            return False
        return att.letter.sender_id == user.id or att.letter.recipients.filter(user=user).exists()
    if rel.startswith('violation_photos/'):
        violation = ViolationReport.objects.filter(photo=rel).first()
        return violation is not None and (violation.reporter_id == user.id or _role(user) in MUNICIPAL_STAFF_ROLES)
    cad = AutoCADFile.objects.filter(original_file=rel).first() or AutoCADFile.objects.filter(converted_file=rel).first()
    return cad is not None and (cad.user_id == user.id or _role(user) in MUNICIPAL_STAFF_ROLES)
